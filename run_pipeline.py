#!/usr/bin/env python3
"""
run_pipeline.py — Reads config.yml, and for every entry whose output HTML
doesn't exist yet (or is older than the source PDF / config), runs:
    voter_roll_ocr.py  ->  build_voter_html.py
Then regenerates docs/index.html listing all dashboards.

This is what the GitHub Actions workflow calls on every push. You can also
run it locally the same way.
"""

import subprocess
import sys
import os
import glob
import yaml

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")


def needs_processing(entry):
    out = os.path.join(REPO_ROOT, entry["output"])
    pdf = os.path.join(REPO_ROOT, entry["pdf"])
    cfg = os.path.join(REPO_ROOT, "config.yml")
    if not os.path.exists(pdf):
        print(f"  ! PDF not found, skipping: {entry['pdf']}", file=sys.stderr)
        return False
    if not os.path.exists(out):
        return True
    out_mtime = os.path.getmtime(out)
    return os.path.getmtime(pdf) > out_mtime or os.path.getmtime(cfg) > out_mtime


def process_entry(entry):
    pdf = os.path.join(REPO_ROOT, entry["pdf"])
    out = os.path.join(REPO_ROOT, entry["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    records_json = out.replace(".html", ".json")

    print(f"==> OCR extracting {entry['pdf']} (pages {entry['start_page']}-{entry['end_page']})")
    subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS, "voter_roll_ocr.py"),
            pdf, records_json,
            "--start", str(entry["start_page"]),
            "--end", str(entry["end_page"]),
        ],
        check=True,
    )

    print(f"==> Building dashboard {entry['output']}")
    subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS, "build_voter_html.py"),
            records_json, out,
            "--title", entry.get("title", "मतदाता सूची"),
            "--meta", entry.get("meta", ""),
        ],
        check=True,
    )


def rebuild_index():
    docs_dir = os.path.join(REPO_ROOT, "docs")
    htmls = sorted(f for f in glob.glob(os.path.join(docs_dir, "*.html")) if not f.endswith("index.html"))
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
</style></head>
<body>
<h1>मतदाता सूची डैशबोर्ड — सभी वार्ड</h1>
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
        entries = yaml.safe_load(f) or []

    processed = 0
    for entry in entries:
        if needs_processing(entry):
            process_entry(entry)
            processed += 1
        else:
            print(f"==> Skipping (up to date): {entry['output']}")

    rebuild_index()
    print(f"\nDone. Processed {processed} of {len(entries)} entries.")


if __name__ == "__main__":
    main()
