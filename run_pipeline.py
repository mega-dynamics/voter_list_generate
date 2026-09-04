#!/usr/bin/env python3
"""
run_pipeline.py — Reads config.yml and processes each entry with TWO
independent cache checks, so small edits stay fast:

  1. OCR (expensive, ~20 sec/page): only re-runs if the PDF's size OR
     start_page/end_page changed since last run. A ".sig" sidecar file
     next to each JSON output records what the OCR was run with.

  2. HTML build (cheap, ~1 sec): re-runs whenever the JSON is newer than
     the HTML, OR the JSON doesn't have a matching HTML yet. Since this
     is cheap, we don't bother fine-grained-caching title/meta changes —
     editing config.yml just rebuilds HTML for every entry, but never
     triggers OCR unless start_page/end_page/the PDF itself changed.

This means: fixing a typo in `title`, `meta`, or even `output` only costs
~1 second per entry. Only touching `pdf`, `start_page`, or `end_page` (or
replacing the PDF file itself) triggers a real OCR re-run.

Use --force-ocr to bypass the OCR cache entirely (e.g. after upgrading
voter_roll_ocr.py itself, since script changes aren't tracked in the sig).
"""

import subprocess
import sys
import os
import glob
import hashlib
import yaml

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
FORCE_OCR = "--force-ocr" in sys.argv

MAX_PAGES = None
if "--max-pages" in sys.argv:
    MAX_PAGES = int(sys.argv[sys.argv.index("--max-pages") + 1])
    print(f"*** TEST MODE: capping every entry to {MAX_PAGES} page(s). "
          f"Output goes to docs/_test/ and will NOT touch your real "
          f"dashboards or OCR cache. ***", file=sys.stderr)


def effective_entry(entry):
    """In test mode (--max-pages), return a modified copy that reads a
    truncated page range and writes to an isolated docs/_test/ location,
    so a quick test run can never overwrite a real cached dashboard or
    its OCR cache."""
    if MAX_PAGES is None:
        return entry
    e = dict(entry)
    e["end_page"] = min(entry["end_page"], entry["start_page"] + MAX_PAGES - 1)
    base = os.path.basename(entry["output"])
    e["output"] = os.path.join("docs", "_test", base)
    e["title"] = f"[TEST] {entry.get('title','')}"
    return e


def json_path_for(entry):
    return os.path.join(REPO_ROOT, entry["output"]).replace(".html", ".json")


def sig_path_for(entry):
    return json_path_for(entry) + ".sig"


def meta_sig_path_for(entry):
    return os.path.join(REPO_ROOT, entry["output"]) + ".meta.sig"


def resolve_page_range(entry):
    """Fill in start_page/end_page via auto-detection if the config entry
    doesn't specify them. Mutates and returns entry."""
    if entry.get("start_page") and entry.get("end_page"):
        return entry
    pdf = os.path.join(REPO_ROOT, entry["pdf"])
    print(f"==> [detect] {entry['pdf']} has no start_page/end_page in config.yml, auto-detecting ...")
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "voter_roll_ocr.py"), pdf, "--detect-range"],
        check=True, capture_output=True, text=True,
    )
    start, end = result.stdout.strip().split(",")
    entry["start_page"], entry["end_page"] = int(start), int(end)
    print(f"    -> detected pages {entry['start_page']}-{entry['end_page']}")
    return entry


def compute_sig(entry):
    """Fingerprint of everything that affects OCR OUTPUT (not display
    metadata). Changing this forces a re-OCR; changing anything else
    (title/meta/output filename) does not. Uses a real content hash
    (not just file size) so two different PDFs that happen to be the
    same size can't be mistaken for an unchanged file."""
    pdf = os.path.join(REPO_ROOT, entry["pdf"])
    if not os.path.exists(pdf):
        return None
    h = hashlib.sha256()
    with open(pdf, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256={h.hexdigest()};start={entry['start_page']};end={entry['end_page']}"


def needs_ocr(entry):
    sig = compute_sig(entry)
    if sig is None:
        print(f"  ! PDF not found, skipping: {entry['pdf']}", file=sys.stderr)
        return False
    if FORCE_OCR:
        return True
    jpath, spath = json_path_for(entry), sig_path_for(entry)
    if not os.path.exists(jpath) or not os.path.exists(spath):
        return True
    with open(spath, encoding="utf-8") as f:
        stored_sig = f.read().strip()
    return stored_sig != sig


def compute_meta_sig(entry):
    """Fingerprint of DISPLAY-only fields. Changing these triggers a cheap
    HTML rebuild but never OCR."""
    return f"title={entry.get('title','')};meta={entry.get('meta','')}"


def needs_html(entry):
    jpath = json_path_for(entry)
    out = os.path.join(REPO_ROOT, entry["output"])
    if not os.path.exists(jpath):
        return False  # nothing to build from yet
    if not os.path.exists(out):
        return True
    if os.path.getmtime(jpath) >= os.path.getmtime(out):
        return True
    mspath = meta_sig_path_for(entry)
    if not os.path.exists(mspath):
        return True
    with open(mspath, encoding="utf-8") as f:
        stored = f.read().strip()
    return stored != compute_meta_sig(entry)


def run_ocr(entry):
    pdf = os.path.join(REPO_ROOT, entry["pdf"])
    jpath = json_path_for(entry)
    os.makedirs(os.path.dirname(jpath), exist_ok=True)
    print(f"==> [OCR] {entry['pdf']} (pages {entry['start_page']}-{entry['end_page']}) — this is the slow step")
    subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS, "voter_roll_ocr.py"),
            pdf, jpath,
            "--start", str(entry["start_page"]),
            "--end", str(entry["end_page"]),
        ],
        check=True,
    )
    sig = compute_sig(entry)
    with open(sig_path_for(entry), "w", encoding="utf-8") as f:
        f.write(sig)


def run_html_build(entry):
    jpath = json_path_for(entry)
    out = os.path.join(REPO_ROOT, entry["output"])
    print(f"==> [HTML] {entry['output']}")
    subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS, "build_voter_html.py"),
            jpath, out,
            "--title", entry.get("title", "मतदाता सूची"),
            "--meta", entry.get("meta", ""),
        ],
        check=True,
    )
    with open(meta_sig_path_for(entry), "w", encoding="utf-8") as f:
        f.write(compute_meta_sig(entry))


def rebuild_index():
    docs_dir = os.path.join(REPO_ROOT, "docs")
    htmls = sorted(
        f for f in glob.glob(os.path.join(docs_dir, "*.html"))
        if not f.endswith("index.html") and not f.endswith("upload.html")
    )
    items = "\n".join(
        f'<li><a href="{os.path.basename(h)}">{os.path.basename(h).replace(".html","")}</a></li>'
        for h in htmls
    )
    index_html = f"""<!DOCTYPE html>
<html lang="hi"><head><meta charset="UTF-8">
<title>मतदाता सूची डैशबोर्ड</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; }}
h1 {{ font-size: 20px; }}
li {{ margin: 8px 0; font-size: 15px; }}
a {{ color: #2c7be5; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.uploadBtn {{ display:inline-block; margin:14px 0 24px 0; padding:10px 20px; background:#2c7be5; color:#fff !important; border-radius:7px; font-weight:600; }}
</style></head>
<body>
<h1>मतदाता सूची डैशबोर्ड — सभी वार्ड</h1>
<a class="uploadBtn" href="upload.html">➕ नया PDF अपलोड करें</a>
<ul>
{items}
</ul>
</body></html>
"""
    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"==> Rebuilt docs/index.html with {len(htmls)} dashboard(s)")


def main():
    with open(os.path.join(REPO_ROOT, "config.yml"), encoding="utf-8") as f:
        raw_entries = yaml.safe_load(f) or []

    ocr_runs = html_runs = 0
    for raw_entry in raw_entries:
        if not os.path.exists(os.path.join(REPO_ROOT, raw_entry["pdf"])):
            continue
        resolve_page_range(raw_entry)
        entry = effective_entry(raw_entry)
        force_this = FORCE_OCR or MAX_PAGES is not None  # test runs always OCR fresh
        if force_this or needs_ocr(entry):
            run_ocr(entry)
            ocr_runs += 1
        else:
            print(f"==> [OCR] skipped, unchanged: {entry['output']}")

        if force_this or needs_html(entry):
            run_html_build(entry)
            html_runs += 1
        else:
            print(f"==> [HTML] skipped, up to date: {entry['output']}")

    if MAX_PAGES is None:
        rebuild_index()
    print(f"\nDone. OCR ran for {ocr_runs} entr{'y' if ocr_runs==1 else 'ies'}, "
          f"HTML rebuilt for {html_runs} of {len(raw_entries)} entries."
          + ("\n*** This was a TEST run (--max-pages) -- nothing under docs/_test/ "
             "gets committed by the workflow, and your real dashboards were untouched. ***"
             if MAX_PAGES is not None else ""))


if __name__ == "__main__":
    main()
