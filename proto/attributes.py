"""The evaluation model: questionnaire -> attributes -> evidence -> decision. All deterministic.

Every questionnaire question feeds exactly one attribute, so the buyer can see why an attribute exists,
how much of it each vendor answered, and how much of that is backed by evidence.
"""
import json

import pandas as pd

from . import data, db

# The questionnaire sent to vendors: ten questions, at least one per attribute. Knockouts are minimum requirements.
QUESTIONS = [
    ("Q1", "Price", "State the price per selling unit, currency, Incoterm, freight, payment terms and any discount.", "Annexure A", False, "All"),
    ("Q2", "Units and strength", "State your selling unit, its net weight in kg, density for liquids, and the strength with the marker it is measured against.", "Annexure A or TDS", False, "All"),
    ("Q3", "Lead time", "State the lead time to our Hosur plant. Can you meet the need-by date? If not, give your earliest date.", "Annexure A", False, "All"),
    ("Q4", "OTIF", "State your on-time-in-full (OTIF) rate over the last 12 months.", "Delivery records", False, "All"),
    ("Q5", "COA", "Provide a Certificate of Analysis (COA) from a recent batch for each line, showing batch number, manufacturing date and retest date.", "Batch COA", True, "All"),
    ("Q6", "Rejections and certificates", "State your rejection rate over the last 12 months, and the certifications you hold with their expiry dates.", "Rejection records and certificates", False, "All"),
    ("Q7", "MOQ and shelf life", "State the minimum order quantity in kg, total shelf life, and the remaining shelf life you guarantee at delivery.", "Annexure A", False, "All"),
    ("Q8", "Source and continuity", "Are you the manufacturer or a trader? Name the manufacturer and site, any second source, and whether you will share delivery and rejection records.", "Authorisation letter or continuity plan", False, "All"),
    ("Q9", "SDS and regulation", "Provide the Safety Data Sheet and confirm each material is suitable for leave-on scalp use under India's Cosmetics Rules, 2020.", "SDS and regulatory declaration", True, "All"),
    ("Q10", "Cold chain", "Can you deliver with an unbroken 2-8 C cold chain? Describe packaging and temperature logging.", "Temperature log sample", True, "Cold-chain lines (RM-009, 010)"),
]
ATTRIBUTES = [
    {"key": "Cost", "name": "Landed cost", "why": "What the material really costs us per kg of spec-equivalent strength.", "measure": "Rs per spec kg after discount, duty, freight, FX and strength", "questions": ["Q1", "Q2"]},
    {"key": "Delivery", "name": "Delivery reliability", "why": "A late ingredient stops production. Protects OTIF.", "measure": "OTIF from our records, plus lead time against need-by", "questions": ["Q3", "Q4"]},
    {"key": "Quality", "name": "Quality", "why": "A failed batch means rejection and rework. Protects defect rate.", "measure": "Defect rate from our records, COA status, certifications", "questions": ["Q5", "Q6"]},
    {"key": "Inventory", "name": "Inventory and storage fit", "why": "Limited space and shelf life. Protects inventory cost.", "measure": "6-month holding cost, MOQ against use, shelf life, pallets", "questions": ["Q7"]},
    {"key": "Supply risk", "name": "Supply risk", "why": "Single sources and traders can break supply without warning.", "measure": "Rating of the vendor's answer on source and continuity", "questions": ["Q8"]},
    {"key": "Compliance", "name": "Compliance and spec fit", "why": "Leave-on scalp use, so it has to be right, safe and legal.", "measure": "Rating of the vendor's answers on safety, regulation and cold chain", "questions": ["Q9", "Q10"]},
]
KEYS = [a["key"] for a in ATTRIBUTES]
BY_KEY = {a["key"]: a for a in ATTRIBUTES}
Q_TO_ATTR = {q: a["key"] for a in ATTRIBUTES for q in a["questions"]}
RATING = {"good": 100, "ok": 60, "weak": 20}
# Answers that already sit in the quote. Code fills these in, so nobody is asked twice for a price they gave.
FROM_QUOTE = {"Q1": ["price"], "Q2": ["price_unit"], "Q3": ["lead_time_days"], "Q7": ["moq_value", "moq_text", "shelf_life_months", "remaining_shelf_months"]}
SERIOUS = {"LATE", "SPACE_CLASH", "COA_CONFLICT", "COA_STALE", "MOQ_SHELF", "MOQ_COVER", "CLAIM_CONTRADICTED", "WITHHELD", "STRENGTH_ADJUSTED"}
FLAG_TEXT = {"LATE": "arrives after need-by", "SPACE_CLASH": "MOQ needs more space than is free", "COA_CONFLICT": "COA disagrees with the quote", "COA_STALE": "COA is out of date", "MOQ_SHELF": "MOQ exceeds usable shelf life",
             "MOQ_COVER": "MOQ exceeds stock cover", "CLAIM_CONTRADICTED": "claims disagree with our records", "WITHHELD": "refuses to share records", "STRENGTH_ADJUSTED": "strength differs from spec"}


_memo = {}


def question_bank():
    q = pd.DataFrame(QUESTIONS, columns=["ID", "Topic", "Question", "Evidence requested", "Knockout", "Applies to"])
    q["Attribute"] = q["ID"].map(Q_TO_ATTR)
    q["Mandatory"] = "Y"
    return q


def _applies(row, quoted):
    return not str(row["Applies to"]).startswith("Cold") or bool(quoted & {"RM-009", "RM-010"})


def vendor_questions(v):
    """One row per question for a vendor. Recomputed only when the vendor's data changes."""
    key = (v, json.dumps(db.record(v), sort_keys=True), json.dumps(db.answers(v), sort_keys=True))
    if _memo.get(v, (None,))[0] != key:
        _memo[v] = (key, _vendor_questions(v))
    return _memo[v][1].copy()


def _vendor_questions(v):
    rec = {**db.record(v), "vendor": v}
    quoted = {l["rm_code"] for l in rec["lines"]}
    hist = data.sheet("Vendor_History")
    has_hist = (hist["Vendor"] == v).any()
    ans = {a["qid"]: a for a in db.answers(v)}
    valid_coa = any(c.get("retest_date", "") and str(c["retest_date"]) >= "2026-12-20" for c in rec["coas"])
    rows = []
    for _, q in question_bank().iterrows():
        a = ans.get(q["ID"], {})
        status = a.get("status", "not_answered")
        ev = a.get("evidence", "none")
        if q["ID"] in FROM_QUOTE and rec["lines"] and status != "answered":
            have = [l for l in rec["lines"] if any(l.get(f) is not None for f in FROM_QUOTE[q["ID"]])]
            if have:
                status = "answered" if len(have) == len(rec["lines"]) else "partial"
                ev = "document"
                a = {**a, "summary": a.get("summary") or f"In the quote, for {len(have)} of {len(rec['lines'])} lines"}
        if q["ID"] in ("Q4", "Q6") and has_hist:
            ev = "our_records"      # code-derived: our own PO and inspection history beats a claim
        if q["ID"] == "Q5" and valid_coa:
            ev = "document"
        rows.append({"id": q["ID"], "topic": q["Topic"], "attribute": q["Attribute"], "question": q["Question"], "mandatory": True, "knockout": bool(q["Knockout"]), "applicable": _applies(q, quoted),
                     "status": status, "evidence": ev, "summary": a.get("summary", ""), "rating": a.get("rating"), "file": a.get("evidence_file")})
    return pd.DataFrame(rows)


def attribute_table(v):
    """Per attribute: % answered, % evidence-backed, what is outstanding."""
    q = vendor_questions(v)
    q = q[q["applicable"]]
    out = []
    for a in ATTRIBUTES:
        g = q[q["attribute"] == a["key"]]
        answered = g["status"].isin(["answered", "partial"]).sum()
        backed = g["evidence"].isin(["document", "our_records"]).sum()
        n = max(len(g), 1)
        rated = [RATING[r] for r in g["rating"] if r in RATING]
        pending = g[(~g["status"].isin(["answered", "refused"])) & g["mandatory"]]
        pct_b = backed / n
        out.append({"vendor": v, "attribute": a["key"], "questions": len(g), "answered": int(answered), "answered_pct": answered / n, "backed": int(backed), "backed_pct": pct_b,
                    "rating_score": sum(rated) / len(rated) if rated else None,
                    "refused": int((g["status"] == "refused").sum()), "waiting": pending["id"].tolist()})
    return pd.DataFrame(out)


def all_attributes(vendors=None):
    return pd.concat([attribute_table(v) for v in (vendors or db.VENDORS)], ignore_index=True)


def vendor_summary(v):
    q = vendor_questions(v)
    q = q[q["applicable"]]
    n = max(len(q), 1)
    return {"applicable": len(q), "answered": int(q["status"].isin(["answered", "partial"]).sum()), "answered_pct": q["status"].isin(["answered", "partial"]).sum() / n,
            "backed_pct": q["evidence"].isin(["document", "our_records"]).sum() / n, "refused": int((q["status"] == "refused").sum()),
            "knockouts_open": q[q["knockout"] & ~q["status"].isin(["answered"])]["id"].tolist()}


def support(v):
    """What the vendor has told us it supports. Nothing here is decided in advance."""
    r = db.record(v)
    return sorted(l["rm_code"] for l in r["lines"]), sorted(n["rm_code"] for n in r["not_quoted"])


def replied(v):
    return any(m["direction"] == "in" for m in db.thread(v))


def _flags(r):
    return sorted({i["code"] for i in r["issues"] if i["code"] in SERIOUS})


def line_decisions(q):
    """Should we proceed? One recommendation per RFx line, from rules only. The buyer decides."""
    silent = [v for v in db.VENDORS if not replied(v)]
    names = data.vendors().set_index("Vendor")["Name"].to_dict()
    short = {k: n.split()[0] for k, n in names.items()}
    rows = []
    for _, rm in data.rm_table().iterrows():
        code = rm["RM code"]
        g = q[(q["rm_code"] == code) & (q["not_quoted"] == False)] if len(q) else q   # noqa: E712
        ok = g[(g["cleared_questionnaire"] == True) & (g["comparable"] == True)].sort_values("sku_score", ascending=False) if len(g) else g   # noqa: E712
        asks = [f"{short[r['vendor']]}: {i['text']}" for _, r in g.iterrows() for i in r["issues"] if i["action"] == "Ask"] if len(g) else []
        waiting = [f"Reply from {short[v]}" for v in silent] + asks
        d = {"SKU": code, "Material": rm["Material"], "Template": rm["Priority template"], "Bidders": len(g), "Cleared": len(ok), "Best": None, "Score": None, "Waiting for": waiting}
        if g.empty:
            d.update(Call="Wait" if silent else "No bidder", Why="No vendor has offered this line yet." if silent else "No vendor supports this line.")
        elif ok.empty:
            why = "; ".join(f"{short[r['vendor']]}: {', '.join(r['knockouts']) or 'cannot compare yet'}" for _, r in g.iterrows())
            d.update(Call="Do not proceed", Why=f"No bidder has passed the checks. {why}")
        else:
            top = ok.iloc[0]
            fl = _flags(top)
            d.update(Best=short[top["vendor"]], Score=round(float(top["sku_score"]), 1))
            flag_text = ", ".join(FLAG_TEXT[f] for f in fl)
            if pd.notna(top["late_days"]) and top["late_days"] > 15:     # after first production on 4 January
                d.update(Call="Hold", Why=f"Best option {short[top['vendor']]} arrives {int(top['late_days'])} days after need-by, past first production.")
            elif waiting:
                d.update(Call="Wait", Why=f"{short[top['vendor']]} leads, but answers are still due that could change this.")
            elif fl:
                d.update(Call="Proceed with conditions", Why=f"{short[top['vendor']]} leads. Conditions: {flag_text}.")
            else:
                d.update(Call="Proceed", Why=f"{short[top['vendor']]} leads with no open flags.")
        rows.append(d)
    return pd.DataFrame(rows)


def cell(key, r, a):
    """What the buyer sees for one vendor on one attribute: the fact, then what backs it."""
    if r is None or r.get("not_quoted") == True:   # noqa: E712
        return "No quote"
    if key == "Cost":
        fact = f"Rs {r['cost_inr_per_spec_kg']:,.0f}/kg" if pd.notna(r.get("cost_inr_per_spec_kg")) else "Cannot compare yet"
        src = "from quote"
    elif key == "Delivery":
        late = f", {int(r['late_days'])}d late" if pd.notna(r.get("late_days")) and r["late_days"] > 0 else ""
        lead = f"{r['lead_days']:.0f}d lead" if pd.notna(r.get("lead_days")) else "lead time unknown"
        if pd.notna(r.get("otif")):
            fact, src = f"OTIF {r['otif']:.0%}, {lead}{late}", "our records" if r["history_level"] == "Line history" else "our records, other items"
        elif pd.notna(r.get("otif_claim_pct")):
            fact, src = f"Claims {r['otif_claim_pct']:.0f}%, {lead}{late}", "unverified claim"
        else:
            fact, src = f"{lead}{late}", "no OTIF data"
    elif key == "Quality":
        coa = f"COA {str(r.get('coa_status')).lower()}"
        if pd.notna(r.get("defect_rate")):
            fact, src = f"Defects {r['defect_rate']:.1%}, {coa}", "our records"
        elif pd.notna(r.get("defect_claim_pct")):
            fact, src = f"Claims {r['defect_claim_pct']:g}%, {coa}", "unverified claim"
        else:
            fact, src = coa, "no defect data"
    elif key == "Inventory":
        moq = f"MOQ {r['moq_kg']:,.0f} kg" if pd.notna(r.get("moq_kg")) else "MOQ unknown"
        life = f", {r['remaining_shelf_months']:.0f}m life" if pd.notna(r.get("remaining_shelf_months")) else ""
        fact, src = moq + life, "from quote"
    else:
        s = a.get("rating_score") if a is not None else None
        fact = "Not answered" if s is None or s != s else f"Rating {s:.0f}/100"
        src = f"{a['answered']} of {a['questions']} answered" if a is not None else ""
    return f"{fact} ({src})"


KNOCK_TEXT = {"Q5": "COA", "Q9": "SDS and regulatory confirmation", "Q10": "Cold chain proof"}
ASK_TEXT = {"NEED_DENSITY": "Density", "NEED_NET_WEIGHT": "Pack weight", "NEED_MOQ_KG": "MOQ in kg", "NO_MOQ": "MOQ", "NO_SHELF": "Shelf life", "COA_STALE": "COA", "COA_EXPIRED": "COA", "COA_CONFLICT": "COA strength",
            "MARKER_MISMATCH": "Strength marker", "NEED_STRENGTH": "Strength", "NO_LEAD": "Lead time", "NO_PRICE": "Price"}
LEVEL = {3: "High", 2: "Medium", 1: "Low"}


def fact(key, r, a):
    """The actual value behind a score: a price for cost, a certificate status for quality."""
    if r is None:
        return ""
    if key == "Cost":
        return f"Rs {r['cost_inr_per_spec_kg']:,.0f}/kg" if pd.notna(r.get("cost_inr_per_spec_kg")) else "Pending"
    if key == "Delivery":
        lead = f"{r['lead_days']:.0f}d lead" if pd.notna(r.get("lead_days")) else "Lead unknown"
        var = f" ±{r['lt_var']:.0f}d" if pd.notna(r.get("lt_var")) else ""
        return f"OTIF {r['otif']:.0%}, {lead}{var}" if pd.notna(r.get("otif")) else f"{lead}, no history"
    if key == "Quality":
        d = f"{r['defect_rate']:.1%} defects, " if pd.notna(r.get("defect_rate")) else ""
        return f"{d}COA {str(r.get('coa_status')).lower()}"
    if key == "Inventory":
        moq = f"MOQ {r['moq_kg']:,.0f} kg" if pd.notna(r.get("moq_kg")) else "MOQ unknown"
        return moq + (f", {r['remaining_shelf_months']:.0f}m life" if pd.notna(r.get("remaining_shelf_months")) else "")
    return f"{a['answered']} of {a['questions']} answered"


def best_vendor(q, code, template, templates):
    """Top vendor for one item under one template, among those that passed the checks."""
    from . import engine
    s, _ = engine.score(q, templates, template)
    g = s[(s["rm_code"] == code) & (s["cleared_questionnaire"] == True) & s["sku_score"].notna()].sort_values("sku_score", ascending=False)   # noqa: E712
    return (g.iloc[0]["vendor"], float(g.iloc[0]["sku_score"])) if len(g) else (None, None)


def why(key, r, a):
    """One short explanation of a score, in plain language."""
    if key == "Cost":
        return " ".join(r["trail"]) or "No conversion was possible yet."
    if key == "Delivery":
        if pd.isna(r.get("otif")):
            return "No delivery history with us, so this attribute is left out of the score. It isn't treated as poor."
        src = "this line" if r["history_level"] == "Line history" else "its other items"
        late = f" Arrives {int(r['late_days'])} days after need-by." if pd.notna(r.get("late_days")) and r["late_days"] > 0 else ""
        return f"Our records for {src}: OTIF {r['otif']:.1%}, lead time varies by {r['lt_var']:.0f} days. Score is 70% OTIF and 30% lead-time steadiness.{late}"
    if key == "Quality":
        base = f"Our records show {r['defect_rate']:.1%} defects." if pd.notna(r.get("defect_rate")) else "No quality history, so this is left out of the score."
        ko = [i["text"] for i in r["issues"] if i["code"].startswith("COA")]
        return " ".join([base, *ko, f"Vendor claims {r['defect_claim_pct']:g}% defects." if pd.notna(r.get("defect_claim_pct")) else ""]).strip()
    if key == "Inventory":
        t = [i["text"] for i in r["issues"] if i["code"] in ("MOQ_SHELF", "MOQ_COVER", "SPACE_CLASH", "SHELF_FAIL", "NO_MOQ", "NEED_MOQ_KG")]
        cost = f"6-month holding cost about Rs {r['inventory_cost_inr']:,.0f}. " if pd.notna(r.get("inventory_cost_inr")) else ""
        return cost + (" ".join(t) or "MOQ and shelf life fit our use and space.")
    qs = vendor_questions(r["vendor"])
    qs = qs[(qs["attribute"] == key) & qs["status"].isin(["answered", "partial", "refused"])]
    notes = "; ".join(f"{x['summary']}" for _, x in qs.head(4).iterrows() if x["summary"])
    return f"Rated from the vendor's answers ({a['answered']} of {a['questions']}): {notes or 'nothing answered yet.'}"


def inbox_state(v, busy, stage):
    """The short indicator shown next to a vendor in the inbox."""
    if busy:
        return "Agents reading", "violet"
    return {"Not started": ("Not sent", "gray"), "Awaiting first reply": ("Waiting for vendor", "blue"), "Needs your approval": ("Reply ready", "red"), "Open questions": ("Reply needed", "orange"),
            "Waiting for vendor": ("Waiting for vendor", "blue"), "Ready for evaluation": ("Complete", "green"), "Ready, with gaps": ("Stopped replying", "orange")}.get(stage, (stage, "gray"))


def waiting_for(v, issues):
    s = vendor_summary(v)
    out = {ASK_TEXT.get(i["key"].split("|")[1], "Clarification") for i in issues if i["tries_left"] > 0}
    out |= {KNOCK_TEXT[k] for k in s["knockouts_open"] if k in KNOCK_TEXT}
    return ", ".join(sorted(out)) or "Nothing"


def friendly_status(v, busy, stage):
    """Plain-language vendor status: what's happening, and whose move it is."""
    sup, dec = support(v)
    m = {
        "Not started": ("RFx not sent yet", "No one", "Send the RFx first."),
        "Awaiting first reply": ("RFx sent. No reply yet", "Vendor", "Waiting for their first reply."),
        "Needs your approval": ("Waiting for your approval", "You", "The agent has something for you to approve in the Cockpit."),
        "Open questions": ("Questions still open", "You", "Nothing has been sent. Check whether a draft was rejected."),
        "Waiting for vendor": ("We asked. Waiting for their answer", "Vendor", "Our email has gone out. Simulate their reply, or chase if they stay silent."),
        "Ready for evaluation": ("Commercial questions complete", "No one", "Their quote can be evaluated."),
        "Ready, with gaps": ("Stopped answering. Gaps remain", "You", "Three tries used. Decide whether to go ahead without these answers."),
    }
    head, who, nxt = m.get(stage, (stage, "No one", ""))
    if busy:
        head, who, nxt = "Agents are reading their latest message", "Agents", "This takes about a minute. The database updates when it finishes."
    return {"headline": head, "ball": who, "next": nxt, "supports": sup, "declined": dec}
