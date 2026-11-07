"""Claims versus evidence. No scores: every claim goes through the same 10 yes-or-no conditions.

The Evidence Evaluator agent answers the conditions for a document. Code overrides what it can check itself,
counts the conditions met, and gives the result. 8 or more is Good, 6 or 7 is Medium, 5 or fewer is Low.
Good and Medium pass. Three conditions are gates: miss one and the result is Low, whatever the count.

Rule zero: no evidence means Low and Fail. An agent can never pass a claim that has no document or record behind it.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import data, db

CONDITIONS = [
    ("issuer_named", "Issuer named", "It names who issued it: a company, lab or certifier."),
    ("qualified_source", "Maker or independent source", "It comes from the manufacturer or an independent lab or certifier, not a trader acting for an unnamed party."),
    ("right_sku", "Right SKU", "It covers the SKU line we asked about."),
    ("relevant", "Answers our question", "It is the kind of proof we asked for."),
    ("supports_claim", "Supports the claim", "Its values agree with what the vendor claimed."),
    ("enough_data", "Enough data", "It has batch-level results for the key tests, or a long enough time period."),
    ("complete", "Complete", "It has the batch or reference, dates, methods, limits and a sign-off."),
    ("in_date", "In date", "It is current for our need-by date."),
    ("dates_consistent", "Dates make sense", "Its dates are possible and in the right order."),
    ("looks_genuine", "Looks genuine", "Nothing suggests it was made up: real variation, no marketing language, no generic batch number."),
]
KEYS = [c[0] for c in CONDITIONS]
NAME = {c[0]: c[1] for c in CONDITIONS}
GATES = ("supports_claim", "dates_consistent", "looks_genuine")
GOOD_AT, MEDIUM_AT = 8, 6
TODAY = date(2026, 11, 14)      # end of the response window in this scenario
NEED_BY = date(2026, 12, 20)
MIN_PO_LINES = 6                # fewer than this is too little history to judge a claim
_memo = {}


def level(checks):
    """Good, Medium or Low from the conditions. This is the whole rule."""
    met = sum(1 for k in KEYS if checks[k]["met"])
    if any(not checks[g]["met"] for g in GATES):
        return "Low"
    return "Good" if met >= GOOD_AT else "Medium" if met >= MEDIUM_AT else "Low"


def _d(v):
    try:
        return pd.to_datetime(v).date() if v else None
    except (ValueError, TypeError):
        return None


def date_flags(coa):
    """Checks a document's dates in code, so an impossible document can't talk its way through."""
    m, i, r = _d(coa.get("mfg_date")), _d(coa.get("issue_date")), _d(coa.get("retest_date"))
    out = []
    if m and m > TODAY:
        out.append(f"Manufacture date {m} is in the future")
    if m and i and i < m:
        out.append(f"Issued {i}, before the batch was made on {m}")
    if m and r and r <= m:
        out.append("Retest date is not after manufacture")
    return out


def _attached(v):
    return {Path(a).name for m in db.thread(v) if m["direction"] == "in" for a in m["attachments"]}


def _none(why):
    return {k: {"met": False, "note": why, "by": "Rule"} for k in KEYS}


def _coded(checks, coa, line):
    """Code replaces the agent's answer wherever code can check the fact itself."""
    out = {k: dict(v) for k, v in checks.items()}
    if not coa:
        return out
    flags = date_flags(coa)
    out["dates_consistent"] = {"met": not flags, "note": "; ".join(flags), "by": "Code"}
    retest, issued = _d(coa.get("retest_date")), _d(coa.get("issue_date"))
    late = bool(retest and retest < NEED_BY)
    old = bool(issued and (TODAY - issued).days > 183)
    note = f"Retest date {retest} is before our need-by date." if late else "COA is over 6 months old." if old else ""
    out["in_date"] = {"met": not (late or old), "note": note, "by": "Code"}
    cv, sv = coa.get("strength_value"), (line or {}).get("strength_value")
    if cv and sv and (coa.get("strength_unit") or "") == ((line or {}).get("strength_unit") or "") and abs(cv - sv) / sv > 0.05:
        out["supports_claim"] = {"met": False, "note": f"COA shows {cv:g}, but the quote says {sv:g}.", "by": "Code"}
    return out


def _row(item, code, attribute, claim_type, claim, evidence, why, checks):
    lvl = level(checks)
    return {"Item": item, "rm_code": code, "Attribute": attribute, "Claim type": claim_type, "Claim": claim, "Evidence provided": evidence, "How it was checked": why,
            "Conditions met": sum(1 for k in KEYS if checks[k]["met"]), "Evidence": lvl, "Result": "Pass" if lvl != "Low" else "Fail", "checks": checks}


def _misses(checks):
    return "; ".join(NAME[k] for k in KEYS if not checks[k]["met"])


def _spec_row(line, rec, docs, files, mat):
    code = line["rm_code"]
    sv = line.get("strength_value")
    claim = f"{sv:g}{line.get('strength_unit') or ''} {line.get('strength_marker') or ''}".strip() if sv is not None else "Meets our specification"
    coa = next((c for c in rec["coas"] if c.get("rm_code") == code), None)
    args = (mat[code], code, "Quality", "Specification", claim)
    if not coa:
        return _row(*args, "None", "No COA provided, so this fails.", _none("No document"))
    f = coa.get("file")
    if f not in files:
        return _row(*args, "Stated in an email", "Details were typed in a message. No document was provided.", _none("No document"))
    d = docs.get(f)
    if not d:
        return _row(*args, f, "The document hasn't been checked yet.", _none("Not checked"))
    checks = _coded(d["checks"], coa, line)
    return _row(*args, f, d["reason"] or "COA checked against the quote.", checks)


def _record_row(item, code, attribute, kind, claimed, actual, h, tol, share):
    args = (item, code, attribute, kind, f"{kind} {claimed:g}%")
    if actual is None:
        why = "Vendor refuses to share records." if share == "refused" else "No records from the vendor and no history with us."
        return _row(*args, "None", why + " This fails.", _none("No records"))
    line_level = h["level"] == "Line history"
    agrees = abs(claimed / 100 - actual) <= tol
    enough = line_level and h["po_lines"] >= MIN_PO_LINES
    c = {k: {"met": True, "note": "", "by": "Code"} for k in KEYS}
    c["right_sku"] = {"met": line_level, "note": "" if line_level else "Our records are for its other items.", "by": "Code"}
    c["enough_data"] = {"met": enough, "note": "" if enough else f"{h['po_lines']} PO lines, none or too few on this item.", "by": "Code"}
    c["complete"] = {"met": line_level, "note": "" if line_level else "No line-level record for this item.", "by": "Code"}
    c["supports_claim"] = {"met": agrees, "note": "" if agrees else f"Our records show {actual:.1%}.", "by": "Code"}
    src = "Our records for this line" if line_level else "Our records for its other items"
    why = "Compared with our own POs, receipts and inspections. It matches." if agrees else "Compared with our own records. The claim is contradicted."
    return _row(*args, f"{src}: {actual:.1%}", why, c)


def _vendor_row(kind, attribute, claim, docs, doc_kind):
    d = next((x for x in docs.values() if x["document_type"] == doc_kind), None)
    args = ("All lines", None, attribute, kind, claim)
    if d:
        return _row(*args, d["file"], d["reason"], d["checks"])
    return _row(*args, "Statement only", "No supporting document was provided, so this fails.", _none("No document"))


def claims(v):
    """Every claim this vendor has made, with its evidence and result. Recomputed only when the data changes."""
    from . import engine   # engine imports this module
    rec = db.record(v)
    checked = db.doc_checks(v)
    key = json.dumps([rec, checked], sort_keys=True, default=str)
    if _memo.get(v, (None,))[0] == key:
        return _memo[v][1].copy()
    docs, files = {d["file"]: d for d in checked}, _attached(v)
    mat = data.rm_table().set_index("RM code")["Material"].to_dict()
    c = rec.get("claims") or {}
    share = c.get("records_sharing")
    rows = []
    for line in rec["lines"]:
        code = line["rm_code"]
        rows.append(_spec_row(line, rec, docs, files, mat))
        h = engine.history(v, code)
        if c.get("otif_pct") is not None:
            rows.append(_record_row(mat[code], code, "Delivery", "OTIF", float(c["otif_pct"]), h["otif"], h, 0.05, share))
        if c.get("defect_pct") is not None:
            rows.append(_record_row(mat[code], code, "Quality", "Defect rate", float(c["defect_pct"]), h["defect"], h, 0.01, share))
    for cert in c.get("certifications") or []:
        rows.append(_vendor_row("Certification", "Quality", f"{cert.get('name')}" + (f", valid to {cert['valid_to']}" if cert.get("valid_to") else ""), docs, "certificate"))
    if c.get("regulatory_ok"):
        rows.append(_vendor_row("Regulatory", "Compliance", "Suitable for leave-on cosmetic use", docs, "declaration"))
    if c.get("cold_chain") in ("validated_logger", "insulated_no_logger") and {l["rm_code"] for l in rec["lines"]} & {"RM-009", "RM-010"}:
        rows.append(_vendor_row("Cold chain", "Compliance", "Validated 2-8 °C with logger" if c["cold_chain"] == "validated_logger" else "Insulated boxes with gel packs", docs, "temperature_log"))
    df = pd.DataFrame(rows, columns=["Item", "rm_code", "Attribute", "Claim type", "Claim", "Evidence provided", "How it was checked", "Conditions met", "Evidence", "Result", "checks"])
    _memo[v] = (key, df)
    return df.copy()


def _rollup(results):
    """Good, Medium or Low for a set of claims, from the share that pass."""
    n = len(results)
    share = (results == "Pass").sum() / n if n else 0
    return "Good" if share >= 0.8 else "Medium" if share >= 0.6 else "Low"


def item_claims(v, code):
    c = claims(v)
    return c[c["rm_code"] == code]


def item_level(v, code):
    """Evidence level for one vendor on one item, from that item's own claims. Vendor-wide claims count only in the vendor's overall level, so one missing certificate doesn't mark down every item."""
    return _rollup(item_claims(v, code)["Result"])


def summary(v):
    c = claims(v)
    return {"claims": len(c), "passed": int((c["Result"] == "Pass").sum()), "failed": int((c["Result"] == "Fail").sum()), "good": int((c["Evidence"] == "Good").sum()),
            "medium": int((c["Evidence"] == "Medium").sum()), "low": int((c["Evidence"] == "Low").sum()), "level": _rollup(c["Result"])}


def verdict(vendor, file, checks):
    """What the evaluator's answers come to for one document, after code has had its say."""
    rec = db.record(vendor)
    coa = next((c for c in rec["coas"] if c.get("file") == file), None)
    line = next((l for l in rec["lines"] if coa and l["rm_code"] == coa.get("rm_code")), None)
    final = _coded(checks, coa, line)
    return f"{level(final)}, {sum(1 for k in KEYS if final[k]['met'])} of 10 conditions met"
