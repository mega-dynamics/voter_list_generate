# मतदाता सूची OCR डैशबोर्ड — Voter Roll OCR Dashboard

Push a Rajasthan Nagar Nigam voter-roll PDF (Bharatpur-style format) to this
repo, and GitHub Actions automatically OCRs it and publishes a searchable
HTML dashboard via GitHub Pages — no manual steps, no LLM calls, runs on
GitHub's free compute.

## How it works

```
pdfs/your_file.pdf  +  config.yml entry
        │
        ▼   (GitHub Actions, on push)
scripts/voter_roll_ocr.py    → OpenCV grid-detection + Tesseract OCR → JSON
scripts/build_voter_html.py  → JSON → searchable HTML
        │
        ▼
docs/your_dashboard.html  (auto-committed + published on GitHub Pages)
```

## One-time setup

1. **Create a new GitHub repo** and push this folder's contents to it.

2. **Enable GitHub Pages**: repo Settings → Pages → Source → "GitHub Actions".
   (Don't pick a branch/folder here — the workflow handles deployment.)

3. That's it. No local install needed — everything runs inside the
   Actions runner. (If you *also* want to run the pipeline locally, see
   the `README.md` inside `scripts/` for the local setup steps.)

## Adding a new ward/part PDF

1. Drop the PDF into `pdfs/`.
2. Add an entry to `config.yml` — you need to know:
   - `start_page` / `end_page`: the PDF page numbers of the **main roll
     grid only** (skip the cover page and ward-map page). Open the PDF
     and check the "पृष्ठ संख्या : X / Y" footer on the first and last
     grid pages.
   - `title` / `meta`: whatever you want shown in the dashboard header
     (ward number, booth address, etc. — copy from the PDF's cover page).
   - `output`: where to write the HTML, e.g. `docs/ward29_part1.html`.
3. Commit and push.
4. Watch the "Actions" tab — the workflow runs (~15-25 sec/page, so a
   45-page roll takes roughly 15-20 minutes), then your dashboard appears
   at `https://<your-username>.github.io/<repo-name>/<output-filename>`.
   The full list of all dashboards you've added lives at
   `https://<your-username>.github.io/<repo-name>/`.

## Re-processing a PDF (e.g. you fixed a config typo)

The pipeline skips PDFs whose output already exists and is up to date.
To force a re-run: either delete the corresponding file in `docs/`, or
just touch/edit `config.yml` (any change to that file makes every entry
re-check its freshness).

## Running locally instead of / in addition to Actions

```bash
pip install -r requirements.txt
sudo apt-get install -y poppler-utils tesseract-ocr
mkdir -p tessdata
curl -sL -o tessdata/hin.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/hin.traineddata
curl -sL -o tessdata/eng.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata
export TESSDATA_PREFIX=$PWD/tessdata

python3 run_pipeline.py
```

## Accuracy & limitations

See `scripts/README.md` for full details (measured accuracy per field,
known limitations like supplement-page format not yet supported, etc.).
Deletion-status detection (सक्रिय/विलोपित) tested at 100%; name/relation/
house/age/ID fields at 85-93%. Worth a manual spot-check on a new
ward/part's first run before treating it as authoritative.
