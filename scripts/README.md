# Voter Roll OCR Pipeline — README

Scripts to turn a Bharatpur-style Rajasthan Nagar Nigam voter-roll PDF into
a searchable HTML tool **without using an LLM at all** — pure OpenCV (grid
detection) + Tesseract OCR. This means no per-page token cost and no vision
API calls; it just runs as a normal script.

## Why this exists

These PDFs' embedded text layer is corrupted (broken font encoding — even
`pdftotext`/PyMuPDF produce garbage). The only way to read them is visually.
This pipeline replaces manual/LLM-vision transcription with template-based
OCR, since every page follows the exact same 3-column × 9-row grid layout
with fixed field labels (नाम, पिता/पति/माता का नाम, मकान संख्या, आयु, लिंग).

## Setup (one-time)

```bash
# 1. poppler-utils for PDF rasterization (pdftoppm)
apt-get install -y poppler-utils   # if not already present

# 2. Python deps
pip install opencv-python numpy --break-system-packages

# 3. Tesseract + BEST (LSTM) Hindi + English models — accuracy matters a lot
#    here; the default "fast" models are noticeably worse.
apt-get install -y tesseract-ocr
mkdir -p /path/to/tessdata
curl -sL -o /path/to/tessdata/hin.traineddata \
  https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/hin.traineddata
curl -sL -o /path/to/tessdata/eng.traineddata \
  https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata
export TESSDATA_PREFIX=/path/to/tessdata
```

## Usage

### Step 1 — OCR extraction (PDF → JSON)

```bash
python3 voter_roll_ocr.py INPUT.pdf records.json --start 3 --end 48
```

- `--start` / `--end`: PDF page numbers of the **main roll grid pages**
  (skip the cover page and the ward-map page — those are usually pages 1-2).
  Find the true range by opening the PDF and checking the "पृष्ठ संख्या : X / Y"
  footer on the first and last grid pages.
- `--start-sno` (optional): the serial number the first extracted entry
  should start at. Defaults to 1. Use this if you're processing a page
  range that doesn't start at entry 1 (e.g. resuming, or testing a
  middle chunk) so the sequential-serial-number logic stays correct.
- Runs at roughly **20–25 seconds per page** on this environment (no
  network calls, no LLM — just local OCR).

### Step 2 — Build the HTML search tool (JSON → HTML)

```bash
python3 build_voter_html.py records.json output.html \
  --title "भरतपुर वार्ड 28 भाग 3" \
  --meta "राज्य निर्वाचन आयोग, राजस्थान | वार्ड 28 भाग 3 | मतदान केंद्र: 85 - ..."
```

Produces a single self-contained HTML file — same UI as the manually-built
tools (search box, सक्रिय/विलोपित filters, पुरुष/स्त्री filters, area
dropdown, sortable columns, deleted rows struck through in red).

## Accuracy (measured against manually-verified ground truth, pages 3-10 = 216 entries)

| Field | Accuracy |
|---|---|
| Deletion status (सक्रिय/विलोपित) | **100%** (24/24 deleted entries correctly caught) |
| Gender | **100%** |
| Name | ~89% exact match (occasional 1-2 char OCR noise) |
| Relation name | ~85% exact match |
| House number | ~85-90% exact match |
| Age | ~89% exact match |
| EPIC/ID code | ~90-93% exact match (occasional single-digit slip) |

The deletion-status accuracy is the most important number — it's derived
from **grid position** (always sequential) plus an isolated single-character
OCR read of just the S/E/R/O letter, which is far more reliable than reading
the whole box-number-and-serial string together (this document uses a
decorative old-style-figures font where digits like 8/9 are easily confused
with stray letters if read in one pass).

## Known limitations / not yet handled

- **Supplement pages** (the addition/deletion/modification list format,
  single-column large boxes) use a different layout than the main grid —
  this script only handles the main roll pages. Would need a second,
  similarly-built extractor for that layout (structurally simpler, since
  it's one column and mostly already-known serial numbers from the
  deletion list format `S 131`, `E 44`, etc.)
- Mid-page locality-header changes are detected and handled (tested and
  working — see page 9 in the test data, which correctly splits between
  "पिक्चर पैलेस..." and "कमला रोड बड़ा मौहल्ला...").
- For entries marked deleted, the "DELETED" diagonal watermark sometimes
  degrades OCR of the name/relation/house/age text underneath it (status
  itself is unaffected, since that's read from a separate crop, but the
  other fields on that row are noisier). Fine for search/reference use;
  worth a manual spot-check for critical use cases.
- Recommend spot-checking ~5% of any new PDF's output against the source
  images before treating it as final, especially first-time on a new
  ward/part (font/scan quality can vary slightly).

## Files

- `voter_roll_ocr.py` — PDF → JSON extractor (the core OCR pipeline)
- `build_voter_html.py` — JSON → searchable HTML generator
- `pipeline_test.html` — example output from this test run (pages 3-10, 216 records)
