"""Audit and summarize fixed-count ALNS evidence without changing observations."""
import argparse
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import material_signature

EVIDENCE = ROOT/"docs/evidence/alns-fixed-boards"
COHORTS = ("replay", "replay-v2", "operational", "with-alignment", "continuation")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohorts",nargs="+",default=list(COHORTS))
    parser.add_argument("--output",default=str(EVIDENCE))
    args=parser.parse_args()
    output=ROOT/args.output
    output.mkdir(parents=True,exist_ok=True)
    records, views = [], {}
    for cohort in args.cohorts:
        directory = EVIDENCE/cohort
        if not (directory/"index.json").exists():
            continue
        index = json.loads((directory/"index.json").read_text())
        observations = {}
        for row in index["records"]:
            payload = (directory/row["file"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise ValueError("Changed evidence: "+row["file"])
            observations[(row["case"], row["arm"], row["repeat"])] = json.loads(payload)
        for row in index["records"]:
            p = observations[(row["case"], row["arm"], row["repeat"])]
            if p["status"] != "completed":
                records.append(dict(cohort=cohort, **row))
                continue
            baseline = observations[(row["case"], "baseline", row["repeat"])]
            keys = final_system_sort_keys([baseline["snapshot"], p["snapshot"]])
            comparison = "better" if keys[1] < keys[0] else "worse" if keys[1] > keys[0] else "equal"
            identical_material = material_signature(baseline["snapshot"]) == material_signature(p["snapshot"])
            if identical_material:
                comparison = "equal"
            trace = p.get("trace") or {}
            rejects = Counter()
            for stat in trace.get("operators", {}).values():
                rejects.update(stat.get("rejects") or {})
            f = p["final"]
            record = dict(cohort=cohort, case=row["case"], arm=row["arm"], repeat=row["repeat"],
                status=p["status"], valid=p["valid"], comparison=comparison,
                metadata_only_rank_change=identical_material and keys[1] != keys[0],
                boards=f["boards"], pieces=f["pieces"], unplaced=f["unplaced"],
                remnant=f["reusable_m2"], cutter_mm=f["cutter_profile"][0], segments=f["cutter_profile"][1],
                alignment=f["alignment_ratio"], family_splits=f["family_splits"],
                wall=p["wall"], cpu=p["cpu"], rss_kib=p["peak_rss_kib"],
                attempts=trace.get("attempts",0), gallery=len(p["gallery"]), physical_gallery=p["physical_gallery"],
                strict_pass=sum(v["passed"] is True for v in p["strict"]),
                strict_fail=sum(v["passed"] is False for v in p["strict"]), rejects=json.dumps(rejects),
                geometry=f["signature"], source_file=f"{cohort}/{row['file']}")
            records.append(record)
            views.setdefault(row["case"], []).append((cohort, row["arm"], p))
    fields = list(dict.fromkeys(key for r in records for key in r))
    with (output/"observations.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    groups = {}
    for r in records:
        if r.get("status") == "completed":
            groups.setdefault((r["cohort"],r["case"],r["arm"]),[]).append(r)
    summary = dict(observations=len(records), valid=sum(bool(r.get("valid")) for r in records),
        strict_pass=sum(r.get("strict_pass",0) for r in records), strict_fail=sum(r.get("strict_fail",0) for r in records),
        comparisons=dict(Counter(r.get("comparison") for r in records)),
        groups=[dict(cohort=k[0],case=k[1],arm=k[2],comparisons=dict(Counter(r["comparison"] for r in rs)),
            remnants=sorted({r["remnant"] for r in rs}),cut_mm=sorted({r["cutter_mm"] for r in rs}),
            segments=sorted({r["segments"] for r in rs}),wall=[r["wall"] for r in rs],attempts=[r["attempts"] for r in rs])
            for k,rs in groups.items()])
    (output/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="groups"},indent=2))
    for case, values in views.items():
        best = min(values,key=lambda v:final_system_sort_keys([v[2]["snapshot"]])[0])
        baseline = next(v for v in values if v[1]=="baseline")
        render(case, baseline[2]["snapshot"], best[2]["snapshot"],output)
        print(case,"best",best[0],best[1],best[2]["final"])


def render(case,before,after,output):
    columns=[("Previous research incumbent",before),("Best measured new result",after)]
    height=100+((len(before["sheets"])+1)//2)*225
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}">',
        '<rect width="100%" height="100%" fill="#f4f7fa"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17324b;font-size:12px}</style>',
        f'<text x="20" y="24" style="font-size:20px">Order {case}: fixed boards, protected reusable remnant</text>']
    for j,(name,plan) in enumerate(columns):
        ox=20+j*375
        svg.append(f'<text x="{ox}" y="52" style="font-size:15px">{name}</text>')
        for i,sheet in enumerate(plan["sheets"]):
            x,y=ox+(i%2)*160,80+(i//2)*225
            scale=.78
            svg.append(f'<rect x="{x}" y="{y}" width="{sheet["w"]*scale}" height="{sheet["h"]*scale}" fill="white" stroke="#18374c"/>')
            for p in sheet["pieces"]:
                size=tuple(sorted((round(p["w"],3),round(p["h"],3))))
                hue=int(hashlib.sha256(str(size).encode()).hexdigest()[:6],16)%360
                svg.append(f'<rect x="{x+p["x"]*scale}" y="{y+p["y"]*scale}" width="{p["w"]*scale}" height="{p["h"]*scale}" fill="hsl({hue},55%,75%)" stroke="#435e6a" stroke-width=".35"><title>{html.escape(str(size))} cm</title></rect>')
            svg.append(f'<text x="{x}" y="{y+sheet["h"]*scale+17}">Board {i+1}: {len(sheet["pieces"])} pieces</text>')
    svg.append('</svg>')
    target=output/f"comparison-{case}.svg"
    target.write_text("\n".join(svg),encoding="utf-8")
    ET.parse(target)


if __name__=="__main__":
    main()
