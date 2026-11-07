"""Extraction eval. Scores the agents' stored records against the known truth of the generated vendor replies.

Run after the first replies have been processed (test_runtime.py does this). Reports precision, recall and F1 per field.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from proto import db  # noqa: E402

# vendor -> rm_code -> expected values. None means the value must stay empty (not stated by the vendor).
G = {
    "V01": {"RM-001": dict(price=338, currency="INR", price_unit="l", density_g_ml=1.05, moq_value=200, lead_time_days=12, shelf_life_months=24),
            "RM-002": dict(price=142, currency="INR", price_unit="l", density_g_ml=None, moq_value=200, lead_time_days=12, shelf_life_months=24),
            "RM-003": dict(price=1220, currency="INR", price_unit="kg", moq_value=25, lead_time_days=15, shelf_life_months=36),
            "RM-004": dict(price=2050, currency="INR", price_unit="kg", strength_value=98, moq_value=25, lead_time_days=15, shelf_life_months=24),
            "RM-006": dict(price=965, currency="INR", price_unit="kg", moq_value=50, lead_time_days=12, shelf_life_months=24),
            "RM-007": dict(price=27000, currency="INR", price_unit="bag", net_kg_per_unit=25, lead_time_days=15, shelf_life_months=36)},
    "V02": {"RM-001": dict(price=62000, currency="INR", price_unit="drum", net_kg_per_unit=None, moq_value=2, lead_time_days=18, remaining_shelf_months=18),
            "RM-003": dict(price=1180, currency="INR", price_unit="kg", moq_value=25, lead_time_days=18),
            "RM-004": dict(price=1520, currency="INR", price_unit="kg", strength_value=75, moq_value=25, lead_time_days=18),
            "RM-005": dict(price=1760, currency="INR", price_unit="kg", moq_value=25, lead_time_days=18),
            "RM-006": dict(price=990, currency="INR", price_unit="kg", moq_value=50, lead_time_days=18),
            "RM-009": dict(price=24500, currency="INR", price_unit="kg", strength_value=1000, moq_value=20, lead_time_days=30, remaining_shelf_months=8),
            "RM-010": dict(price=14800, currency="INR", price_unit="kg", strength_value=500, moq_value=20, lead_time_days=30, remaining_shelf_months=8)},
    "V03": {"RM-002": dict(price=112, currency="INR", price_unit="kg", moq_value=500, lead_time_days=10, shelf_life_months=24, remaining_shelf_months=20),
            "RM-008": dict(price=4000, currency="INR", price_unit="kg", strength_value=10, moq_value=25, lead_time_days=21, shelf_life_months=24, remaining_shelf_months=18)},
    "V04": {"RM-009": dict(price=240, currency="USD", price_unit="kg", strength_value=1000, moq_value=100, lead_time_days=70, shelf_life_months=12, remaining_shelf_months=10),
            "RM-010": dict(price=148, currency="USD", price_unit="kg", strength_value=500, moq_value=200, lead_time_days=70, shelf_life_months=12, remaining_shelf_months=10),
            "RM-008": dict(price=78, currency="USD", price_unit="kg", strength_value=20, moq_value=10, lead_time_days=56, shelf_life_months=24, remaining_shelf_months=20)},
    "V05": {"RM-002": dict(price=118, price_unit="kg", shelf_life_months=None, moq_value=None),
            "RM-005": dict(price=1650, price_unit="kg", moq_value=None),
            "RM-008": dict(price=7000, price_unit="kg", strength_value=20, moq_value=100, shelf_life_months=12, lead_time_days=21)},
}
CHECKS = {"V02_discount_found": lambda: any(d.get("pct") == 4 for d in db.record("V02")["discounts"]),
          "V02_discount_lines": lambda: [sorted(d["applies_to"]) for d in db.record("V02")["discounts"]] == [["RM-001", "RM-003", "RM-004", "RM-005", "RM-006"]],
          "V02_RM007_not_quoted": lambda: any(n["rm_code"] == "RM-007" for n in db.record("V02")["not_quoted"]),
          "V02_records_refused": lambda: db.record("V02")["claims"].get("records_sharing") == "refused",
          "V04_marker_is_carnosic": lambda: "carnosic" in str(next(l for l in db.record("V04")["lines"] if l["rm_code"] == "RM-008").get("strength_marker")).lower(),
          "V04_coa_812": lambda: any(c.get("strength_value") == 812 for c in db.record("V04")["coas"]),
          "V03_coa_retest": lambda: any(str(c.get("retest_date")).startswith("2026-11-30") for c in db.record("V03")["coas"]),
          "V05_coa_after_order": lambda: db.record("V05")["claims"].get("coa_policy") == "after_order_only",
          "V05_lot_captured": lambda: "lot" in str(next(l for l in db.record("V05")["lines"] if l["rm_code"] == "RM-005").get("moq_text")).lower()}


def same(a, b):
    if isinstance(b, str):
        a, b = str(a).lower().rstrip("s"), b.lower()
        return a == b or a.startswith(b) or (b == "l" and a in ("litre", "liter"))
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return False


tp = fp = fn = 0
miss = []
per = {}
for v, lines in G.items():
    got = {l["rm_code"]: l for l in db.record(v)["lines"]}
    for code, exp in lines.items():
        line = got.get(code, {})
        for f, want in exp.items():
            have = line.get(f)
            s = per.setdefault(f, [0, 0])
            s[1] += 1
            if want is None:
                if have is None:
                    tp += 1
                    s[0] += 1
                else:
                    fp += 1
                    miss.append((v, code, f, "should be empty", have))
            elif have is None:
                fn += 1
                miss.append((v, code, f, want, "missing"))
            elif same(have, want):
                tp += 1
                s[0] += 1
            else:
                fp += 1
                fn += 1
                miss.append((v, code, f, want, have))
p, r = tp / (tp + fp), tp / (tp + fn)
print(f"Fields checked: {sum(b for _, b in per.values())} | precision {p:.1%} | recall {r:.1%} | F1 {2 * p * r / (p + r):.1%}")
print("Per field:", {k: f"{a}/{b}" for k, (a, b) in per.items()})
print("Misses:", miss)
res = {k: bool(f()) for k, f in CHECKS.items()}
print("Trap checks:", sum(res.values()), "of", len(res), res)
out = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4), "traps_passed": sum(res.values()), "traps_total": len(res), "misses": miss}
(Path(__file__).resolve().parents[1] / "runtime" / "eval_result.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
