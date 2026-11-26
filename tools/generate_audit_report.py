import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

with open(PROJECT_ROOT / "exports" / "hindi_to_english_10sections_translated.json", encoding="utf-8") as f:
    data = json.load(f)

audit_report = {
    "document": "Technology_Science_Everyday_Life_Hindi_10p.pdf",
    "total_sections": len(data["sections"]),
    "flagged_issues": [],
    "pronoun_changes": []
}

for s in data["sections"]:
    p_num = s["page_number"]
    for item in s.get("literal_audit", []):
        audit_report["flagged_issues"].append({
            "section": p_num,
            "matched_phrase": item["matched_phrase"],
            "sentence": item["sentence_text"],
            "review_note": item["suggested_fix"]
        })
    for p_item in s.get("changed_pronouns", []):
        audit_report["pronoun_changes"].append({
            "section": p_num,
            "preceding_subject": p_item["preceding_subject"],
            "matched_pronoun": p_item["matched_pronoun"],
            "replacement": p_item["replacement"],
            "original_sentence": p_item["original_sentence"],
            "changed_sentence": p_item["changed_sentence"]
        })

out_json = PROJECT_ROOT / "exports" / "audit_report.json"
out_md = PROJECT_ROOT / "exports" / "audit_report.md"

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(audit_report, f, ensure_ascii=False, indent=2)

lines = []
lines.append("# Literal Translation & Pronoun Audit Report\n")
lines.append(f"- **Source Document:** `Technology_Science_Everyday_Life_Hindi_10p.pdf`")
lines.append(f"- **Total Sections Audited:** {len(data['sections'])}")
lines.append(f"- **Total Flagged Sentences for Review:** {len(audit_report['flagged_issues'])}")
lines.append(f"- **Total Context-Aware Pronoun Changes:** {len(audit_report['pronoun_changes'])}\n")
lines.append("## 1. Flagged Sentences for Review (Condition 1: Ambiguous 'बस')\n")

for issue in audit_report["flagged_issues"]:
    sec = issue["section"]
    mp = issue["matched_phrase"]
    st = issue["sentence"]
    rn = issue["review_note"]
    lines.append(f"### Section {sec}")
    lines.append(f"- **Matched Phrase:** `{mp}`")
    lines.append(f"- **Sentence:** \"{st}\"")
    lines.append(f"- **Review Note:** {rn}\n")

lines.append("## 2. Context-Aware Pronoun Changes (Condition 2: App / Device / Software Subjects)\n")
for pc in audit_report["pronoun_changes"]:
    sec = pc["section"]
    ps = pc["preceding_subject"]
    mp = pc["matched_pronoun"]
    rep = pc["replacement"]
    orig = pc["original_sentence"]
    chg = pc["changed_sentence"]
    lines.append(f"### Section {sec}")
    lines.append(f"- **Preceding Subject:** `{ps}`")
    lines.append(f"- **Change:** `{mp}` -> `{rep}`")
    lines.append(f"- **Original Sentence:** \"{orig}\"")
    lines.append(f"- **Updated Sentence:** \"{chg}\"\n")

with open(out_md, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"✅ Saved audit reports to {out_json} and {out_md}")
