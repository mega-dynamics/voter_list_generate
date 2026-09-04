#!/usr/bin/env python3
"""
build_voter_html.py — Convert voter_roll_ocr.py's JSON output into the
searchable HTML tool (same UI as the Ward-28-Part-1 reference tool).

Usage:
    python3 build_voter_html.py records.json output.html \
        --title "भरतपुर वार्ड 28 भाग 3" \
        --meta "वार्ड संख्या: 28 | भाग संख्या: 3 | मतदान केंद्र: 85 - ..."

If --title/--meta are omitted, generic placeholders are used — edit the
generated HTML's header block by hand, or pass them in.
"""

import json
import sys
import argparse

REASON_TEXT = {"S": "स्थानांतरण", "E": "मृत्यु", "R": "पुनरावृत्ति", "O": "अन्य", "": ""}

HEAD_TEMPLATE = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>मतदाता सूची खोज - {title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Noto Sans Devanagari', Arial, sans-serif; background:#f4f4f4; margin:0; padding:18px; }}
  h1 {{ text-align:center; color:#1a1a1a; font-size:22px; margin:0 0 8px 0; }}
  .meta {{ text-align:center; color:#555; font-size:13px; line-height:1.7; }}
  .meta .highlight {{ font-weight:700; color:#1a1a1a; background:#fff8d5; display:inline-block; padding:4px 12px; border-radius:6px; margin-top:4px; }}
  #searchBox {{ display:block; width:100%; max-width:680px; margin:16px auto 12px auto; padding:12px 16px; font-size:15px; border:2px solid #999; border-radius:10px; }}
  #searchBox:focus {{ outline:none; border-color:#2c7be5; }}
  .btnrow {{ display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
  .btnrow button {{ padding:7px 16px; font-size:13px; border:1px solid #bbb; background:#fff; border-radius:20px; cursor:pointer; color:#333; }}
  .btnrow button:hover {{ background:#eef3fb; }}
  .btnrow button.active {{ background:#2c3e50; color:#fff; border-color:#2c3e50; }}
  .btnrow select {{ padding:7px 14px; font-size:13px; border-radius:20px; border:1px solid #bbb; background:#fff; }}
  .statline {{ text-align:center; margin:10px 0 14px 0; font-size:14px; color:#333; }}
  .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; }}
  .dot-green {{ background:#1eae5c; }}
  .dot-red {{ background:#d63333; }}
  .statline span.stat {{ margin:0 14px; font-weight:600; }}
  .table-wrap {{ max-height:72vh; overflow:auto; border-radius:8px; box-shadow:0 1px 6px rgba(0,0,0,0.15); background:#fff; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ border:1px solid #e2e2e2; padding:7px 9px; text-align:left; font-size:12.5px; white-space:nowrap; }}
  th {{ background:#2c3e50; color:#fff; position:sticky; top:0; cursor:pointer; user-select:none; z-index:2; }}
  th:hover {{ background:#3b4f66; }}
  tbody tr:nth-child(even) {{ background:#fafafa; }}
  tbody tr:hover {{ background:#eaf3ff; }}
  tr.deleted {{ background:#fde3e3 !important; }}
  tr.deleted td {{ color:#8a1414; }}
  tr.deleted td.strike {{ text-decoration:line-through; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:700; white-space:nowrap; }}
  .badge-active {{ background:#d4f4dd; color:#0f6b34; }}
  .badge-deleted {{ background:#f6c6c6; color:#8a1414; }}
  .no-result {{ text-align:center; padding:30px; color:#777; background:#fff; border-radius:8px; }}
  footer {{ text-align:center; margin-top:14px; color:#999; font-size:11px; }}
</style>
</head>
<body>

<h1>मतदाता सूची खोज</h1>
<div class="meta">
  {meta}<br>
  <span class="highlight">कुल सक्रिय मतदाता: {active_count}</span>
</div>

<input type="text" id="searchBox" placeholder="नाम, पिता/पति/माता का नाम, EPIC नंबर, मकान संख्या, या क्षेत्र से खोजें...">

<div class="btnrow">
  <button data-status="" class="statusBtn active">सभी</button>
  <button data-status="सक्रिय" class="statusBtn">केवल सक्रिय</button>
  <button data-status="विलोपित" class="statusBtn">केवल विलोपित</button>
  <button data-gender="पुरुष" class="genderBtn">पुरुष</button>
  <button data-gender="स्त्री" class="genderBtn">स्त्री</button>
  <select id="areaFilter"><option value="">-- क्षेत्र चुनें --</option></select>
</div>

<div class="statline" id="statLine"></div>

<div class="table-wrap">
<table id="voterTable">
  <thead>
    <tr>
      <th data-key="sno">क्र.सं.</th>
      <th data-key="id">EPIC/ID नंबर</th>
      <th data-key="name">नाम</th>
      <th data-key="rel">पिता/पति/माता का नाम</th>
      <th data-key="house">मकान संख्या</th>
      <th data-key="age">आयु</th>
      <th data-key="gender">लिंग</th>
      <th data-key="status">स्थिति</th>
      <th data-key="area">क्षेत्र</th>
      <th data-key="page">पृष्ठ</th>
    </tr>
  </thead>
  <tbody id="tableBody"></tbody>
</table>
</div>

<div class="no-result" id="noResult" style="display:none;">कोई मतदाता नहीं मिला।</div>
<footer>{title} — voter_roll_ocr.py generated (no LLM vision used)</footer>

<script>
const voters = """

TAIL_TEMPLATE = """;

const areaFilter = document.getElementById('areaFilter');
const areas = [...new Set(voters.map(v => v.area).filter(Boolean))].sort();
areas.forEach(a => {
  const opt = document.createElement('option');
  opt.value = a; opt.textContent = a;
  areaFilter.appendChild(opt);
});

let state = { q: "", status: "", gender: "", area: "" };
let sortKey = null, sortAsc = true;

function renderTable(list) {
  const body = document.getElementById('tableBody');
  const noResult = document.getElementById('noResult');
  body.innerHTML = "";
  noResult.style.display = list.length === 0 ? "block" : "none";
  const frag = document.createDocumentFragment();
  list.forEach(v => {
    const tr = document.createElement('tr');
    const isDeleted = v.status === "विलोपित";
    if (isDeleted) tr.classList.add('deleted');
    const badgeClass = isDeleted ? "badge-deleted" : "badge-active";
    const statusText = isDeleted ? (v.reason ? `विलोपित (${v.reason})` : "विलोपित") : "सक्रिय";
    const strike = isDeleted ? 'class="strike"' : '';
    tr.innerHTML = `
      <td ${strike}>${v.sno}</td>
      <td ${strike}>${v.id}</td>
      <td ${strike}>${v.name}</td>
      <td ${strike}>${v.rel}</td>
      <td>${v.house}</td>
      <td>${v.age ?? ''}</td>
      <td>${v.gender}</td>
      <td><span class="badge ${badgeClass}">${statusText}</span></td>
      <td>${v.area}</td>
      <td>${v.page ?? ''}</td>
    `;
    frag.appendChild(tr);
  });
  body.appendChild(frag);
}

function applyFilters() {
  let filtered = voters.filter(v => {
    if (state.status && v.status !== state.status) return false;
    if (state.gender && v.gender !== state.gender) return false;
    if (state.area && v.area !== state.area) return false;
    if (!state.q) return true;
    const q = state.q;
    return (
      (v.name||'').toLowerCase().includes(q) ||
      (v.rel||'').toLowerCase().includes(q) ||
      (v.id||'').toLowerCase().includes(q) ||
      (v.house||'').toLowerCase().includes(q) ||
      (v.area||'').toLowerCase().includes(q) ||
      String(v.sno).toLowerCase().includes(q)
    );
  });
  if (sortKey) {
    filtered.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (sortKey === 'age' || sortKey === 'sno') { av = parseInt(av) || 0; bv = parseInt(bv) || 0; }
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
  }
  renderTable(filtered);
  const totalActive = filtered.filter(v => v.status === "सक्रिय").length;
  const totalDeleted = filtered.filter(v => v.status === "विलोपित").length;
  document.getElementById('statLine').innerHTML =
    `<span class="stat"><span class="dot dot-green"></span>सक्रिय: ${totalActive}</span>` +
    `<span class="stat"><span class="dot dot-red"></span>विलोपित: ${totalDeleted}</span>` +
    `<span class="stat">दिखाए जा रहे: ${filtered.length}</span>`;
}

document.getElementById('searchBox').addEventListener('input', function() {
  state.q = this.value.trim().toLowerCase();
  applyFilters();
});
document.querySelectorAll('.statusBtn').forEach(btn => {
  btn.addEventListener('click', function() {
    document.querySelectorAll('.statusBtn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    state.status = this.getAttribute('data-status');
    applyFilters();
  });
});
document.querySelectorAll('.genderBtn').forEach(btn => {
  btn.addEventListener('click', function() {
    const g = this.getAttribute('data-gender');
    if (state.gender === g) { state.gender = ""; this.classList.remove('active'); }
    else {
      document.querySelectorAll('.genderBtn').forEach(b => b.classList.remove('active'));
      state.gender = g; this.classList.add('active');
    }
    applyFilters();
  });
});
areaFilter.addEventListener('change', function() { state.area = this.value; applyFilters(); });
document.querySelectorAll('#voterTable th').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.getAttribute('data-key');
    if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = true; }
    applyFilters();
  });
});
applyFilters();
</script>
</body>
</html>
"""


def convert_record(r):
    """Map voter_roll_ocr.py's raw field names to the HTML tool's schema."""
    status = "विलोपित" if r.get("status") == "D" else "सक्रिय"
    reason = REASON_TEXT.get(r.get("reason", ""), "")
    rel = f"{r.get('rel_type','')} {r.get('rel_name','')}".strip()
    return {
        "sno": r.get("sno"),
        "id": r.get("id", ""),
        "name": r.get("name", ""),
        "rel": rel,
        "house": r.get("house", ""),
        "age": r.get("age"),
        "gender": r.get("gender", ""),
        "status": status,
        "reason": reason,
        "area": r.get("area", ""),
        "page": r.get("page"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("records_json")
    ap.add_argument("output_html")
    ap.add_argument("--title", default="मतदाता सूची")
    ap.add_argument("--meta", default="")
    args = ap.parse_args()

    with open(args.records_json, encoding="utf-8") as f:
        raw = json.load(f)

    records = [convert_record(r) for r in raw]
    active_count = sum(1 for r in records if r["status"] == "सक्रिय")

    head = HEAD_TEMPLATE.format(title=args.title, meta=args.meta or args.title, active_count=active_count)
    data_js = json.dumps(records, ensure_ascii=False)

    with open(args.output_html, "w", encoding="utf-8") as f:
        f.write(head)
        f.write(data_js)
        f.write(TAIL_TEMPLATE)

    print(f"Wrote {len(records)} records ({active_count} active) to {args.output_html}", file=sys.stderr)


if __name__ == "__main__":
    main()
