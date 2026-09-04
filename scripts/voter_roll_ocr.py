#!/usr/bin/env python3
"""
voter_roll_ocr.py — Template-based OCR extractor for Rajasthan Nagar Nigam
voter roll PDFs (Bharatpur-style format).

Works WITHOUT any LLM vision calls — pure OpenCV grid detection + Tesseract
OCR. Designed for the standard 3-column x 9-row grid layout used across
these documents (base roll pages) plus the single-column supplement pages
(additions/deletions/modifications).

Usage:
    python3 voter_roll_ocr.py <input.pdf> <output.json> [--start N] [--end N]

Requires:
    - poppler-utils (pdftoppm)
    - tesseract-ocr with hin.traineddata + eng.traineddata (best/LSTM models)
    - opencv-python, numpy, pillow
"""

import cv2
import numpy as np
import subprocess
import re
import json
import os
import sys
import glob

TESSDATA_PREFIX = os.environ.get("TESSDATA_PREFIX", "/home/claude/tessdata")
os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX

DPI = 400
MIN_GRID_GAP = 300  # px; separates header-table lines from grid row lines at 400dpi


def group_consecutive(arr, gap=5):
    """Collapse a sorted array of pixel-row indices into single line centers."""
    groups = []
    if len(arr) == 0:
        return groups
    start = arr[0]
    prev = arr[0]
    for x in arr[1:]:
        if x - prev > gap:
            groups.append((start + prev) // 2)
            start = x
        prev = x
    groups.append((start + prev) // 2)
    return groups


def detect_lines(img):
    """Return (h_lines, v_lines) — sorted lists of pixel coordinates for
    horizontal and vertical ruling lines detected via morphology."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1))
    h_img = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=2)
    row_sums = h_img.sum(axis=1)
    thresh = row_sums.max() * 0.3
    h_lines = group_consecutive(np.where(row_sums > thresh)[0])

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60))
    v_img = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=2)
    col_sums = v_img.sum(axis=0)
    thresh_v = col_sums.max() * 0.3
    v_lines = group_consecutive(np.where(col_sums > thresh_v)[0])

    return h_lines, v_lines


def find_grid_rows(h_lines):
    """From all detected horizontal lines, find the ones belonging to the
    voter grid (large, consistent gaps) as opposed to the small header
    info-table lines at the top of the page. Also filters out spurious
    thin lines that appear when a locality-header text line is inserted
    mid-table (splitting what would otherwise be a single ~401px row gap
    into a small stray line + an oversized combined gap)."""
    if len(h_lines) < 2:
        return []
    gaps = [h_lines[i + 1] - h_lines[i] for i in range(len(h_lines) - 1)]
    start_idx = None
    for i, g in enumerate(gaps):
        if g >= MIN_GRID_GAP:
            start_idx = i
            break
    if start_idx is None:
        return []
    candidates = h_lines[start_idx:]
    # keep only lines spaced >= MIN_GRID_GAP from the last KEPT line
    kept = [candidates[0]]
    for y in candidates[1:]:
        if y - kept[-1] >= MIN_GRID_GAP:
            kept.append(y)
    return kept


def ocr_text(img, lang, psm, whitelist=None):
    """Run tesseract on an in-memory image, return stripped text."""
    tmp = "/tmp/_ocr_tmp.png"
    cv2.imwrite(tmp, img)
    cmd = ["tesseract", tmp, "stdout", "-l", lang, "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


ALNUM_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/"


def detect_status_prefix(cell, h, w):
    """OCR just the narrow left slice of the box-number rectangle, where an
    S/E/R/O deletion-reason letter would appear if present. Returns '' if
    no letter (active entry) — this is far more reliable than reading the
    whole box-number+digit string at once, because decorative serif digits
    in this font (esp. 8/9) are frequently misread as stray letters."""
    letter_crop = cell[0:int(h * 0.22), 0:int(w * 0.065)]
    letter_crop = cv2.resize(letter_crop, (letter_crop.shape[1] * 3, letter_crop.shape[0] * 3))
    text = ocr_text(letter_crop, "eng", 10, "SERO").strip().upper()
    if text in ("S", "E", "R", "O"):
        return text
    return ""


def extract_cell(img, top, bottom, left, right, expected_sno):
    """OCR one grid cell and return a parsed record dict (or None).
    `expected_sno` is the serial number predicted from grid position —
    used as the authoritative serial (see module docstring) since OCR of
    the decorative box-number digits is unreliable for certain glyphs."""
    cell = img[top:bottom, left:right]
    h, w = cell.shape[:2]
    if h < 10 or w < 10:
        return None

    reason = detect_status_prefix(cell, h, w)
    status = "D" if reason else "A"
    sno = expected_sno

    # --- ID code ---
    id_crop = cell[0:int(h * 0.22), int(w * 0.20):w]
    id_crop = cv2.resize(id_crop, (id_crop.shape[1] * 2, id_crop.shape[0] * 2))
    id_text = ocr_text(id_crop, "eng", 7, ALNUM_WHITELIST)
    id_text = clean_id(id_text.strip())

    # --- rest of cell: name / relation / house / age / gender ---
    rest_crop = cell[int(h * 0.19):h, 0:int(w * 0.60)]
    rest_text = ocr_text(rest_crop, "hin", 6)

    name, rel_type, rel_name, house, age, gender = parse_rest_text(rest_text)

    return {
        "sno": sno,
        "status": status,
        "reason": reason,
        "id": id_text,
        "name": name,
        "rel_type": rel_type,
        "rel_name": rel_name,
        "house": house,
        "age": age,
        "gender": gender,
    }


NAME_RE = re.compile(r"नाम[:：]?\s*(.+)")
REL_RE = re.compile(r"(पिता|पति|माता|अन्य)\s*का\s*नाम[:：]?\s*(.+)")
HOUSE_RE = re.compile(r"मकान\s*संख्या[:：]?\s*(\S*)")
AGE_GENDER_RE = re.compile(r"आयु[:：]?\s*(\d+)\D+लिंग[:：]?\s*(\S+)")


def normalize_gender(g):
    if "पुर" in g:
        return "पुरुष"
    if "स्त्र" in g or "स्ती" in g:
        return "स्त्री"
    return g


def clean_id(raw):
    """Normalize common OCR confusions in EPIC/ID codes."""
    s = raw.strip().upper().replace(" ", "").replace("|", "")
    s = re.sub(r"^R[UOJ]I?/?0?9?/?", "RJ/09/", s) if s.startswith(("RU", "RJ", "RO")) else s
    return s


def parse_rest_text(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name = rel_type = rel_name = house = gender = ""
    age = None
    name_line_used = False
    for i, line in enumerate(lines):
        m = REL_RE.search(line)
        if m:
            rel_type, rel_name = m.group(1), m.group(2).strip()
            continue
        m = HOUSE_RE.search(line)
        if m:
            house = m.group(1).strip()
            continue
        m = AGE_GENDER_RE.search(line)
        if m:
            age = int(m.group(1))
            gender = normalize_gender(m.group(2).strip())
            continue
        # otherwise: treat as the name line (only the first such line).
        # The "नाम:" label consistently OCRs as unrelated noise in this
        # font, so instead of regex-matching the literal label, we drop
        # the first whitespace token (the noise) and keep the rest.
        if not name_line_used:
            name_line_used = True
            m = NAME_RE.search(line)
            if m:
                name = m.group(1).strip()
            else:
                tokens = line.split()
                name = " ".join(tokens[1:]) if len(tokens) > 1 else line
    if not name and lines:
        name = lines[0]
    return name, rel_type, rel_name, house, age, gender


def process_page(img_path, start_sno, locality_default=""):
    img = cv2.imread(img_path)
    h_lines, v_lines = detect_lines(img)
    grid_rows = find_grid_rows(h_lines)

    if len(grid_rows) < 2 or len(v_lines) < 2:
        return [], locality_default

    # locality header: text between last non-grid h_line and grid top
    non_grid = [y for y in h_lines if y < grid_rows[0]]
    locality = locality_default
    if non_grid:
        top = non_grid[-1]
        bottom = grid_rows[0]
        band = img[top:bottom, 0:img.shape[1]]
        if band.shape[0] > 5:
            loc_text = ocr_text(band, "hin", 6).strip()
            if loc_text:
                locality = loc_text.replace("\n", " ")

    # detect rows that are taller than normal -- these have a mid-table
    # locality-header text line inserted above the actual cell content
    # (see find_grid_rows docstring). Trim the top of such rows down to
    # the standard row height, and OCR the trimmed-off band to pick up
    # the new locality text for subsequent rows.
    row_heights = [grid_rows[i + 1] - grid_rows[i] for i in range(len(grid_rows) - 1)]
    median_h = sorted(row_heights)[len(row_heights) // 2]
    row_tops = []
    for i in range(len(grid_rows) - 1):
        top, bottom = grid_rows[i], grid_rows[i + 1]
        if bottom - top > median_h * 1.15:
            new_top = bottom - median_h
            band = img[top:new_top, 0:img.shape[1]]
            loc_text = ocr_text(band, "hin", 6).strip()
            row_tops.append((new_top, bottom, loc_text.replace("\n", " ") if loc_text else None))
        else:
            row_tops.append((top, bottom, None))

    records = []
    n_cols = len(v_lines) - 1
    for r, (top, bottom, new_locality) in enumerate(row_tops):
        if new_locality:
            locality = new_locality
        for c in range(n_cols):
            left, right = v_lines[c], v_lines[c + 1]
            expected_sno = start_sno + r * n_cols + c
            rec = extract_cell(img, top, bottom, left, right, expected_sno)
            if rec:
                rec["area"] = locality
                records.append(rec)
    return records, locality


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pdf_path = sys.argv[1]
    out_path = sys.argv[2]
    start = 3
    end = None
    if "--start" in sys.argv:
        start = int(sys.argv[sys.argv.index("--start") + 1])
    if "--end" in sys.argv:
        end = int(sys.argv[sys.argv.index("--end") + 1])
    if end is None:
        end = start

    work_dir = "/tmp/voter_ocr_work"
    if os.path.isdir(work_dir):
        for f in glob.glob(os.path.join(work_dir, "*")):
            os.remove(f)
    os.makedirs(work_dir, exist_ok=True)
    prefix = os.path.join(work_dir, "pg")
    subprocess.run(
        ["pdftoppm", "-jpeg", "-r", str(DPI), "-f", str(start), "-l", str(end), pdf_path, prefix],
        check=True,
    )

    all_records = []
    locality = ""
    next_sno = 1
    if "--start-sno" in sys.argv:
        next_sno = int(sys.argv[sys.argv.index("--start-sno") + 1])
    for page_img in sorted(glob.glob(prefix + "-*.jpg")):
        print(f"Processing {page_img} (starting sno {next_sno}) ...", file=sys.stderr)
        records, locality = process_page(page_img, next_sno, locality)
        all_records.extend(records)
        if records:
            next_sno = max(r["sno"] for r in records) + 1
        print(f"  -> {len(records)} cells extracted", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=1)
    print(f"Wrote {len(all_records)} records to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
