"""Summarize retained ALNS observations; produce CSV, JSON and geometry SVGs."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from scripts.alns_research import material_signature

EVIDENCE = ROOT/"docs/evidence/alns-study"


def compare(left, right):
    keys = final_system_sort_keys([left["snapshot"], right["snapshot"]])
    return "better" if keys[1] < keys[0] else "worse" if keys[1] > keys[0] else "equal"


def summarize():
    all_rows, groups = [], {}
    for folder in ("matrix", "followup"):
        directory = EVIDENCE/folder
        if not (directory/"index.json").exists():
            continue
        index = json.loads((directory/"index.json").read_text(encoding="utf-8"))
        observations = {}
        for row in index["records"]:
            payload = (directory/row["file"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise ValueError("Evidence file changed: " + row["file"])
            observations[(row["case"], row["phase"], row["arm"], row["repeat"])] = json.loads(payload)
        for row in index["records"]:
            result = observations[(row["case"], row["phase"], row["arm"], row["repeat"])]
            if result["status"] != "completed":
                all_rows.append(dict(version=folder, **row))
                continue
            reference = observations[(row["case"], row["phase"], "baseline", row["repeat"])]
            trace = result.get("trace") or {}
            operators = trace.get("operators") or {}
            rejects = Counter()
            for stat in operators.values():
                rejects.update(stat["rejects"])
            final = result["final"]
            record = dict(version=folder, case=row["case"], phase=row["phase"], arm=row["arm"],
                repeat=row["repeat"], status=result["status"], comparison=compare(reference, result),
                valid=result["valid"], boards=final["boards"], pieces=final["pieces"], unplaced=final["unplaced"],
                remnant_m2=final["reusable_m2"], cut_mm=final["cutter_profile"][0],
                segments=final["cutter_profile"][1], alignment_ratio=final["alignment_ratio"],
                family_splits=final["family_splits"], elapsed=result["elapsed"], cpu=result["cpu"],
                rss_kib=result["peak_rss_kib"], attempts=trace.get("attempts", 0),
                valid_proposals=sum(s["valid"] for s in operators.values()),
                raw_improvements=sum(s["improvements"] for s in operators.values()),
                strict_pass=sum(s["passed"] is True for s in result["strict"]),
                strict_fail=sum(s["passed"] is False for s in result["strict"]),
                gallery=len(result["gallery"]),
                final_geometry=material_signature(result["snapshot"]),
                rejects=json.dumps(rejects, sort_keys=True))
            all_rows.append(record)
            key = (folder, row["case"], row["phase"], row["arm"])
            groups.setdefault(key, []).append(record)
    fields = list(dict.fromkeys(k for row in all_rows for k in row))
    with (EVIDENCE/"observations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    group_summary = []
    for key, rows in groups.items():
        group_summary.append(dict(version=key[0], case=key[1], phase=key[2], arm=key[3],
            comparisons=dict(Counter(r["comparison"] for r in rows)),
            boards=sorted({r["boards"] for r in rows}),
            remnants=sorted({r["remnant_m2"] for r in rows}),
            cut_mm=sorted({r["cut_mm"] for r in rows}),
            attempts=[r["attempts"] for r in rows],
            elapsed_min=min(r["elapsed"] for r in rows), elapsed_max=max(r["elapsed"] for r in rows)))
    summary = dict(observations=len(all_rows), valid=sum(bool(r.get("valid")) for r in all_rows),
        strict_pass=sum(r.get("strict_pass", 0) for r in all_rows), strict_fail=sum(r.get("strict_fail", 0) for r in all_rows),
        comparisons=dict(Counter(r.get("comparison") for r in all_rows)), groups=group_summary)
    (EVIDENCE/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "groups"}, indent=2))


def render(case):
    data = json.loads((EVIDENCE/f"input-{case}.json").read_text(encoding="utf-8"))
    candidates = []
    for folder in ("matrix", "followup"):
        directory = EVIDENCE/folder
        for path in directory.glob(f"{case}-*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("status") == "completed" and value.get("valid"):
                candidates.append((path, value))
    ranked = sorted(candidates, key=lambda item: final_system_sort_keys([item[1]["snapshot"]])[0])
    path, best = ranked[0]
    views = [("Supplied SYSTEM", data["system"]["layout"], data["system"]["measured"]),
             ("Supplied designer", data["designer"]["layout"], data["designer"]["measured"]),
             ("Best measured study winner", best["snapshot"], best["final"])]
    height = 130+((max(len(plan["sheets"]) for _, plan, _ in views)+1)//2)*225
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">',
           '<style>text{font-family:Arial,sans-serif;fill:#183044}.title{font-size:22px;font-weight:bold}.sub{font-size:12px}.piece{stroke:#34495e;stroke-width:.35}</style>',
           f'<rect width="1100" height="{height}" fill="#f3f6f9"/>',
           f'<text class="title" x="20" y="30">Order {case}: equal piece inventory, Kerf 5 mm</text>',
           '<text class="sub" x="20" y="52">Study geometry only; no NC certification. Colors identify equal-size families. Each panel uses its own board order.</text>']
    for column, (label, plan, measured) in enumerate(views):
        x0 = 20+column*365
        svg.append(f'<text x="{x0}" y="82" font-size="16" font-weight="bold">{label}</text>')
        profile = measured["cutter_profile"]
        svg.append(f'<text class="sub" x="{x0}" y="101">{len(plan["sheets"])} boards | remnant {measured["reusable_m2"]:.3f} m2 | cutters {profile[0]/1000:.3f} m</text>')
        for i, sheet in enumerate(plan["sheets"]):
            ox, oy = x0+(i%2)*165, 125+(i//2)*225
            scale = .78
            svg.append(f'<rect x="{ox}" y="{oy}" width="{sheet["w"]*scale}" height="{sheet["h"]*scale}" fill="white" stroke="#40576a"/>')
            for p in sheet["pieces"]:
                fam = tuple(sorted((round(p["w"], 3), round(p["h"], 3))))
                hue = int(hashlib.sha256(str(fam).encode()).hexdigest()[:6], 16)%360
                tooltip = html.escape(f'{p["w"]*10:g} x {p["h"]*10:g} mm')
                svg.append(f'<rect class="piece" x="{ox+p["x"]*scale}" y="{oy+p["y"]*scale}" width="{p["w"]*scale}" height="{p["h"]*scale}" fill="hsl({hue},55%,75%)"><title>{tooltip}</title></rect>')
            svg.append(f'<text class="sub" x="{ox}" y="{oy+sheet["h"]*scale+17}">Board {i+1}: {len(sheet["pieces"])} pieces</text>')
    svg.append('</svg>')
    (EVIDENCE/f"comparison-{case}.svg").write_text("\n".join(svg), encoding="utf-8")
    print(case, "best source", path.relative_to(ROOT))


if __name__ == "__main__":
    summarize()
    render("263")
    render("298")
