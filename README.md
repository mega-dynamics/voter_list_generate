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

## Adding a new ward/part PDF — two ways

### Option A: the upload dashboard (recommended, no git needed at all)

Once Pages is live, visit `https://<your-username>.github.io/<repo-name>/`
— you'll see a list of dashboards plus an **"➕ नया PDF अपलोड करें"**
button. Click it, and on that page:

1. First time only: open **"⚙️ GitHub Repo सेटिंग्स"** and enter your repo
   owner/name plus a **fine-grained GitHub Personal Access Token** scoped
   to just this one repo with **Contents: Read & write** and **Actions: Read-only**
   (create the token at github.com → Settings → Developer
   settings → Fine-grained tokens → Generate new). The token stays only
   in your browser tab and is never sent anywhere except directly to
   GitHub's own API.
2. Choose your PDF, optionally fill in a title/meta, click **"अपलोड करें
   और Process शुरू करें"**.
3. Watch live progress (upload → config update → workflow triggered →
   OCR running → published) right on the page.
4. When done, click the green **"डाउनलोड / देखें"** button — opens your
   new dashboard directly.

Page range is auto-detected from the PDF itself, so you don't need to
know or enter it.

### Option B: manually via git/GitHub web UI

1. Drop the PDF into `pdfs/`.
2. Add an entry to `config.yml` (see the comments in that file —
   `start_page`/`end_page` are optional, auto-detected if omitted).
3. Commit and push.
4. Watch the **Actions** tab — the workflow runs (~15-25 sec/page, so a
   45-page roll takes roughly 15-20 minutes), then your dashboard appears
   at `https://<your-username>.github.io/<repo-name>/<output-filename>`.

## Re-processing a PDF (e.g. you fixed a config typo)

The pipeline only re-runs the slow OCR step when the PDF itself changes,
or `start_page`/`end_page` changes. Editing `title`/`meta`/anything else
in `config.yml` only re-runs the cheap ~1-second HTML rebuild step. So
day-to-day config edits are fast and safe to push freely.

## Editing the OCR/build scripts themselves

Pushing changes to `scripts/*.py` does **not** automatically trigger a
run — editing a script and then having it silently kick off a 15-20
minute run against your full production PDF (with no easy way to test a
fix cheaply first) was exactly the problem this section fixes.

Instead, after editing a script, test it deliberately:

1. Go to the repo's **Actions** tab → select "Process voter roll PDFs" →
   **Run workflow**.
2. Set **`max_pages`** to something small, e.g. `2` — this caps every
   entry to just its first 2 pages for a quick check. Output goes to
   `docs/_test/` and is **never committed** — your real dashboards are
   completely untouched no matter what happens in a test run.
3. Set **`force_ocr`** to `true` if you're testing a change to
   `voter_roll_ocr.py` specifically (test mode always re-runs OCR anyway,
   so this mainly matters if you leave `max_pages` blank).
4. Check the run's logs, or download `docs/_test/*.html` from the run's
   artifact / a temporary branch if you want to actually view it.
5. Once you're happy with the script change, either push a small config
   edit (e.g. touch a `meta` field) to trigger a real run, or use
   **Run workflow** again with `max_pages` blank and `force_ocr: true`
   to force the full production re-run.

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
