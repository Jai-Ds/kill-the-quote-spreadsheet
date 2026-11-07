"""Deterministic rules: unit, strength and currency normalisation, evidence checks and scoring.

No model is called here. AI reads the messy documents; this code does all the maths and rankings,
so every number can be traced and repeated.
"""
import json
import math
from datetime import date, timedelta

import pandas as pd

from . import attributes, data, db, factcheck

PO_DATE = date(2026, 11, 16)   # assumed PO date, two days after the response deadline
WEIGHT_UNITS = {"kg": 1.0, "kgs": 1.0, "g": 0.001, "gm": 0.001, "gram": 0.001, "mg": 1e-6, "tonne": 1000.0, "mt": 1000.0, "quintal": 100.0, "lb": 0.45359237}
VOLUME_UNITS = {"l": 1.0, "litre": 1.0, "liter": 1.0, "ml": 0.001}
SCORE_MIX = {"performance": 0.70, "evidence": 0.30}
EVIDENCE_POINTS = {"Good": 100, "Medium": 60, "Low": 20}   # the evidence level, as the 30% share of the total


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    try:
        return pd.to_datetime(v).date() if v else None
    except (ValueError, TypeError):
        return None


def _issue(code, level, action, text):
    return {"code": code, "level": level, "action": action, "text": text}


def apply_patches(extraction, patches):
    """Applies buyer-approved clarification answers on top of the original extraction."""
    ex = {**extraction, "lines": [dict(l) for l in extraction.get("lines", [])], "coas": list(extraction.get("coas", []))}
    for p in patches or []:
        if p.get("kind") == "coa":
            ex["coas"] = [c for c in ex["coas"] if c.get("rm_code") != p["coa"].get("rm_code")] + [p["coa"]]
            continue
        for l in ex["lines"]:
            if l.get("rm_code") == p.get("rm_code"):
                l[p["field"]] = p["value"]
                l.setdefault("patched", []).append(p["field"])
    return ex


def history(vid, code):
    h = data.sheet("Vendor_History")
    h = h[h["Vendor"] == vid]
    line = h[h["RM code"] == code]
    if len(line):
        r = line.iloc[0]
        return {"level": "Line history", "po_lines": int(r["PO lines"]), "otif": float(r["OTIF %"]), "defect": float(r["Rejected (kg)"]) / float(r["Received (kg)"]), "lt_var": float(r["Lead time variability (days)"])}
    if len(h):
        return {"level": "Vendor history only", "po_lines": int(h["PO lines"].sum()), "otif": h["On-time in-full lines"].sum() / h["PO lines"].sum(),
                "defect": h["Rejected (kg)"].sum() / h["Received (kg)"].sum(), "lt_var": float(h["Lead time variability (days)"].mean())}
    return {"level": "No history", "po_lines": 0, "otif": None, "defect": None, "lt_var": None}


def _claim_status(claim, actual, tolerance, records):
    if claim is None:
        return "No claim"
    if actual is None:
        return "Withheld" if records == "refused" else "Unverified"
    return "Matches" if abs(claim - actual) <= tolerance else "Contradicts"


def normalise_line(vid, line, ex, rfx_row, rm_row, rel):
    """Turns one extracted quote line into comparable rupees per spec-equivalent kg."""
    issues, trail = [], []
    code = rm_row["RM code"]
    qty = float(rfx_row["RFx quantity: net 6M need (kg)"])
    avg_month = float(data.sheet("RM_Requirement").set_index("RM code").loc[code, "Average per month"])
    conf = _num(line.get("confidence"))
    price = _num(line.get("price"))
    cur = (line.get("currency") or "").upper() or None
    unit = (line.get("price_unit") or "").strip().lower()
    density = _num(line.get("density_g_ml"))
    net = _num(line.get("net_kg_per_unit"))

    if conf is not None and conf < 0.7:
        issues.append(_issue("LOW_CONF", "warn", "Confirm", f"The agent is not sure it read this line correctly (confidence {conf:.0%}). Check the source."))

    # 1. unit -> price per kg
    per_kg = None
    if price is None:
        issues.append(_issue("NO_PRICE", "block", "Ask", "No price could be read for this line."))
    elif unit in WEIGHT_UNITS:
        per_kg = price / WEIGHT_UNITS[unit]
        trail.append(f"Weight unit: {price:,.2f} per {unit} = {per_kg:,.2f} per kg (assumed, pure weight conversion)")
    elif unit in VOLUME_UNITS:
        if density:
            per_kg = price / VOLUME_UNITS[unit] / density
            trail.append(f"Volume unit: {price:,.2f} per {unit} / density {density} = {per_kg:,.2f} per kg (vendor density)")
            ref = _num(rm_row["Reference density (g/mL)"])
            if ref and abs(density - ref) / ref > 0.05:
                issues.append(_issue("DENSITY_OFF", "warn", "Confirm", f"Vendor density {density} is over 5% from our reference {ref}."))
        else:
            issues.append(_issue("NEED_DENSITY", "block", "Ask", f"Quoted per {'litre' if unit == 'l' else unit} with no density, so it cannot be converted to kg."))
    elif net:
        per_kg = price / net
        trail.append(f"Pack unit: {price:,.2f} per {unit or 'pack'} / {net:g} kg net = {per_kg:,.2f} per kg")
    else:
        issues.append(_issue("NEED_NET_WEIGHT", "block", "Ask", f"Quoted per '{unit or 'unknown unit'}' with no net weight, so it cannot be converted to kg."))

    # 2. discount
    disc_pct = 0.0
    for d in ex.get("discounts") or []:
        if code in (d.get("applies_to") or []) and per_kg:
            floor = _num(d.get("min_line_value_inr")) or 0
            if per_kg * qty > floor:
                disc_pct = (_num(d.get("pct")) or 0) / 100
                trail.append(f"Discount {disc_pct:.1%} applied: {d.get('condition', '')}")

    # 3. currency
    rate, rate_date = data.fx_rate()
    per_kg_inr = None
    if per_kg is not None:
        base = per_kg * (1 - disc_pct)
        if cur == "USD":
            per_kg_inr = base * rate
            trail.append(f"Currency: US$ {base:,.2f} x {rate} ({rate_date}) = Rs {per_kg_inr:,.2f} per kg")
        elif cur in ("INR", "RS", None):
            per_kg_inr = base
            if cur is None:
                issues.append(_issue("CURRENCY_ASSUMED", "info", "Assume", "No currency stated; assumed INR because the vendor is Indian."))
        else:
            issues.append(_issue("CURRENCY", "block", "Ask", f"Currency {cur} has no rate in FX_Rates."))

    # 4. landed cost
    landed = None
    freight = _num(line.get("freight_inr_per_kg"))
    if freight is None:
        freight = _num((ex.get("terms") or {}).get("freight_inr_per_kg"))
    incoterm = ((ex.get("terms") or {}).get("incoterm") or "").upper()
    imported = cur == "USD" or incoterm.startswith(("CIF", "FOB", "CFR"))
    if per_kg_inr is not None:
        landed = per_kg_inr
        if imported:
            duty = float(data.company()["Import duty on imported RM"])
            landed *= 1 + duty
            trail.append(f"Import duty {duty:.0%} added (assumption in Company sheet) = Rs {landed:,.2f} per kg")
            if freight is None:
                issues.append(_issue("INLAND_FREIGHT", "info", "Assume", "Clearance and inland freight are the buyer's cost and are not stated, so they are not included."))
        if freight:
            landed += freight
            trail.append(f"Freight Rs {freight:,.2f} per kg added = Rs {landed:,.2f} per kg")

    # 5. strength
    factor, sv, su, sm = 1.0, None, None, None
    if rm_row["Strength adjustable?"] == "Y":
        sv, su, sm = data.spec_strength(rm_row["Spec strength"])
        vs, vu = _num(line.get("strength_value")), (line.get("strength_unit") or "").lower()
        vm = (line.get("strength_marker") or "").lower()
        if vs is None:
            factor = None
            issues.append(_issue("NEED_STRENGTH", "block", "Ask", f"No strength stated. Our spec is {rm_row['Spec strength']}."))
        else:
            if vu == "%" and su == "ppm":
                vs *= 10000
            elif vu == "ppm" and su == "%":
                vs /= 10000
            needs_marker = sm not in ("active", "peptide", "")
            if needs_marker and sm.split()[0] not in vm:
                factor = None
                issues.append(_issue("MARKER_MISMATCH", "block", "Ask", f"Strength is on '{line.get('strength_marker')}', but our spec uses {sm}. These cannot be compared."))
            elif abs(vs - sv) > 1e-9:
                factor = sv / vs
                issues.append(_issue("STRENGTH_ADJUSTED", "warn", "Confirm", f"Offered at {vs:g}{su} against spec {sv:g}{su}: {factor:.2f} kg needed per spec kg."))
                trail.append(f"Strength: spec {sv:g}{su} / offered {vs:g}{su} = factor {factor:.3f}")

    cost_spec = landed * factor if landed is not None and factor else None
    if cost_spec is not None and factor != 1.0:
        trail.append(f"Cost per spec-equivalent kg = Rs {cost_spec:,.2f}")

    # 6. MOQ
    mv, mu = _num(line.get("moq_value")), (line.get("moq_unit") or "").strip().lower()
    moq = None
    if mv is not None:
        if mu in WEIGHT_UNITS:
            moq = mv * WEIGHT_UNITS[mu]
        elif net:
            moq = mv * net
        elif mu in VOLUME_UNITS and density:
            moq = mv * VOLUME_UNITS[mu] * density
        else:
            issues.append(_issue("NEED_MOQ_KG", "block", "Ask", f"MOQ of {mv:g} {mu} cannot be converted to kg."))
    elif line.get("moq_text"):
        issues.append(_issue("NEED_MOQ_KG", "block", "Ask", f"MOQ is unclear: '{line['moq_text']}'. Ask for the size in kg."))
    else:
        issues.append(_issue("NO_MOQ", "warn", "Ask", "MOQ is not stated."))

    # 7. shelf life, cover and space
    f = factor or 1.0
    need_kg, month_kg = qty * f, avg_month * f
    rem = _num(line.get("remaining_shelf_months"))
    total_life = _num(line.get("shelf_life_months"))
    min_rem = float(rm_row["Min remaining shelf life at receipt (months)"])
    if rem is None and total_life is not None:
        rem = total_life
        issues.append(_issue("REMAINING_ASSUMED", "warn", "Confirm", f"Remaining life at delivery not stated. Total life of {total_life:g} months used as the best case."))
    if rem is None:
        issues.append(_issue("NO_SHELF", "warn", "Ask", "Shelf life is not stated."))
    shelf_fail = rem is not None and rem < min_rem
    if shelf_fail:
        issues.append(_issue("SHELF_FAIL", "block", "Flag", f"{rem:g} months left at delivery; our minimum is {min_rem:g}."))
    usable = month_kg * rem if rem is not None else None
    write_off = 0.0
    if moq is not None and usable is not None and moq > usable:
        write_off = moq - usable
        issues.append(_issue("MOQ_SHELF", "warn", "Flag", f"MOQ {moq:g} kg, but only {usable:,.0f} kg can be used before expiry: {write_off:,.0f} kg at risk of write-off."))
    max_del = float(rfx_row["Max per delivery (kg)"]) * f
    if moq is not None and moq > max_del and write_off == 0:
        issues.append(_issue("MOQ_COVER", "warn", "Flag", f"MOQ {moq:g} kg exceeds our stock cover limit of {max_del:,.0f} kg per delivery."))
    per_pallet = float(rm_row["kg per pallet"])
    pallets = math.ceil(max(moq or 0, 0.001) / per_pallet)

    # 8. lead time
    lead = _num(line.get("lead_time_days"))
    need_by = _date(rfx_row["First need-by date"])
    arrival = PO_DATE + timedelta(days=lead) if lead is not None else None
    late_days = (arrival - need_by).days if arrival and need_by else None
    if lead is None:
        issues.append(_issue("NO_LEAD", "warn", "Ask", "Lead time is not stated."))
    elif late_days > 0:
        issues.append(_issue("LATE", "warn", "Flag", f"PO on {PO_DATE} arrives {arrival}, {late_days} days after the need-by date."))

    # 9. COA
    coa = next((c for c in ex.get("coas") or [] if c.get("rm_code") == code), None)
    coa_status = "Not provided"
    if coa:
        retest, issued = _date(coa.get("retest_date")), _date(coa.get("issue_date"))
        coa_status = "Valid"
        limit = int(data.company()["COA maximum age at quote (months)"])
        if retest and need_by and retest < need_by:
            coa_status = "Expired"
            issues.append(_issue("COA_EXPIRED", "block", "Ask", f"COA batch {coa.get('batch')} retest date {retest} is before our need-by date."))
        elif issued and (date(2026, 11, 14) - issued).days > limit * 30.5:
            coa_status = "Stale"
            issues.append(_issue("COA_STALE", "warn", "Ask", f"COA issued {issued} is older than {limit} months."))
        cv, cu = _num(coa.get("strength_value")), (coa.get("strength_unit") or "").lower()
        qv, qu = _num(line.get("strength_value")), (line.get("strength_unit") or "").lower()
        if cv and qv and cu == qu and abs(cv - qv) / qv > 0.05:
            coa_status = "Conflict"
            issues.append(_issue("COA_CONFLICT", "warn", "Ask", f"COA shows {cv:g}{cu} but the quote says {qv:g}{qu}."))

    # 10. knockouts from the questionnaire
    claims = ex.get("claims") or {}
    ko = []
    if coa_status == "Expired":
        ko.append("COA expired")
    if claims.get("coa_policy") == "after_order_only":
        ko.append("No COA before order")
    if claims.get("regulatory_ok") is False:
        ko.append("Regulatory not confirmed")
    if rm_row["Storage zone"] == "Cold" and claims.get("cold_chain") != "validated_logger":
        ko.append("Cold chain not validated")
    if shelf_fail:
        ko.append("Shelf life below minimum")

    # 11. inventory cost over the 6-month horizon
    inv_cost = None
    if cost_spec is not None and landed is not None:
        carry = float(data.company()["Inventory carrying cost (per year)"])
        zone = data.sheet("Storage").set_index("Zone").loc[rm_row["Storage zone"]]
        cycle = max(moq or 0, month_kg) / 2
        holding = cycle * landed * carry * 0.5
        space = pallets * float(zone["Holding cost (INR per pallet per month)"]) * 6
        inv_cost = holding + space + write_off * landed

    h = history(vid, code)
    otif_claim, defect_claim = _num(claims.get("otif_pct")), _num(claims.get("defect_pct"))
    rec = claims.get("records_sharing")
    otif_status = _claim_status(otif_claim / 100 if otif_claim is not None else None, h["otif"], 0.05, rec)
    defect_status = _claim_status(defect_claim / 100 if defect_claim is not None else None, h["defect"], 0.01, rec)
    claim_status = "Contradicts" if "Contradicts" in (otif_status, defect_status) else otif_status
    if claim_status == "Contradicts":
        issues.append(_issue("CLAIM_CONTRADICTED", "warn", "Flag", f"Claimed OTIF {otif_claim}% / defects {defect_claim}%, but our records show OTIF {h['otif']:.1%} / defects {h['defect']:.1%}."))
    if rec == "refused":
        issues.append(_issue("WITHHELD", "warn", "Flag", "Vendor refuses to share delivery and rejection records."))

    blocked = [i for i in issues if i["level"] == "block" and i["action"] == "Ask"]
    comparable = cost_spec is not None and not any(i["code"] in ("MARKER_MISMATCH", "NEED_STRENGTH", "NEED_DENSITY", "NEED_NET_WEIGHT", "NO_PRICE") for i in issues)
    return {
        "vendor": vid, "rm_code": code, "material": rm_row["Material"], "relationship": rel, "template": db.item_tags()[code], "zone": rm_row["Storage zone"],
        "vendor_description": line.get("vendor_description"), "quoted_price": price, "quoted_currency": cur, "quoted_unit": unit,
        "cost_inr_per_spec_kg": cost_spec, "landed_inr_per_kg": landed, "strength_factor": factor, "rfx_qty_kg": qty, "need_kg": need_kg,
        "spend_inr": cost_spec * qty if cost_spec is not None else None, "moq_kg": moq, "lead_days": lead, "late_days": late_days,
        "remaining_shelf_months": rem, "write_off_kg": write_off, "pallets": pallets, "inventory_cost_inr": inv_cost, "coa_status": coa_status,
        "history_level": h["level"], "otif": h["otif"], "defect_rate": h["defect"], "lt_var": h["lt_var"], "otif_claim_pct": otif_claim, "defect_claim_pct": defect_claim,
        "claim_status": claim_status,
        "knockouts": ko, "cleared_questionnaire": not ko, "comparable": comparable, "open_asks": len(blocked), "confidence": conf,
        "issues": issues, "trail": trail, "source_file": line.get("source_file"), "source_quote": line.get("source_quote"), "read_note": line.get("read_note"),
    }


_last = {"key": None, "df": None}


def build_quotes(state):
    """One row per vendor x RFx line. Recomputed only when the underlying data changes."""
    key = json.dumps([state, db.item_tags()], sort_keys=True, default=str)
    if _last["key"] != key:
        _last.update(key=key, df=_build_quotes(state))
    return _last["df"].copy()


def _build_quotes(state):
    rm = data.rm_table().set_index("RM code", drop=False)
    rfx = data.sheet("RFx_Lines").set_index("RM code")
    rows = []
    for vid, raw in state.get("extractions", {}).items():
        ex = apply_patches(raw, state.get("patches", {}).get(vid))
        by_code = {l.get("rm_code"): l for l in ex.get("lines", []) if l.get("rm_code")}
        tries = (state.get("clarifications", {}).get(vid) or {}).get("issue_tries", {})
        max_tries = int(data.company()["Maximum clarification tries"])
        # Nobody is pre-assigned to a line. Rows exist only for what the vendor has told us.
        declined = {n.get("rm_code") for n in ex.get("not_quoted", [])}
        for code in sorted((set(by_code) | declined) & set(rm.index)):
            level = history(vid, code)["level"]
            rel = {"Line history": "Current supplier of this line", "Vendor history only": "Existing vendor, new line", "No history": "New vendor"}[level]
            if code not in by_code:
                reason = next((n.get("reason") for n in ex.get("not_quoted", []) if n.get("rm_code") == code), "Declined")
                rows.append({"vendor": vid, "rm_code": code, "material": rm.loc[code, "Material"], "relationship": rel, "template": db.item_tags()[code],
                             "zone": rm.loc[code, "Storage zone"], "comparable": False, "cleared_questionnaire": False, "not_quoted": True, "knockouts": [], "issues": [
                                 _issue("NOT_QUOTED", "info", "Flag", reason)], "trail": [], "open_asks": 0})
                continue
            row = normalise_line(vid, by_code[code], ex, rfx.loc[code], rm.loc[code], rel)
            row["not_quoted"] = False
            if any(i["level"] == "block" and i["action"] == "Ask" and tries.get(f"{code}|{i['code']}", 0) >= max_tries for i in row["issues"]):
                row["not_enough_data"] = True
                row["comparable"] = False
                row["issues"].append(_issue("NOT_ENOUGH_DATA", "block", "Flag", f"No usable answer after {max_tries} tries: marked Not enough data."))
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Combined storage check across all of a vendor's lines in a zone
    free = data.sheet("Storage").set_index("Zone")["Free"]
    for (vid, zone), g in df[df["not_quoted"] == False].groupby(["vendor", "zone"]):  # noqa: E712
        need = g["pallets"].sum()
        if need > free[zone]:
            for i in g.index:
                df.at[i, "issues"] = df.at[i, "issues"] + [_issue("SPACE_CLASH", "warn", "Flag", f"Vendor's MOQs across {zone} lines need {need:.0f} pallets; only {free[zone]:.0f} are free. Ask about split delivery.")]
    return df


LEVEL_WEIGHT = {3: 5, 2: 2, 1: 1}   # High, Medium, Low: High has to dominate, or priorities change nothing


def gap_score(value, best, per_point=5.0):
    """100 for the best bid; each 1% above it loses per_point points, so a real price gap matters."""
    return max(0.0, 100 - per_point * 100 * (value - best) / best)


def _known_scores(r, att):
    """The attribute scores that don't depend on the price."""
    return {"Delivery": None if pd.isna(r["otif"]) else 70 * r["otif"] + 30 * max(0, 1 - r["lt_var"] / 10), "Quality": None if pd.isna(r["defect_rate"]) else max(0, 100 - 1000 * r["defect_rate"]),
            "Supply risk": att.loc[(r["vendor"], "Supply risk"), "rating_score"], "Compliance": att.loc[(r["vendor"], "Compliance"), "rating_score"]}


def score(df, templates=None, force_template=None):
    """Scores each vendor on each SKU, then rolls scores up to the vendor by spend."""
    templates = templates or {k: t["weights"] for k, t in db.latest_templates().items()}
    if df.empty:
        return df, df
    q = df.copy()
    ATTR_COLS = ("score_cost", "score_delivery", "score_quality", "score_inventory", "score_supply", "score_compliance", "performance", "evidence_share", "sku_score")
    for c in ATTR_COLS:
        q[c] = None
    q["evidence_level"] = None
    att = attributes.all_attributes(sorted(q["vendor"].unique())).set_index(["vendor", "attribute"])
    for code, g in q[q["comparable"] == True].groupby("rm_code"):  # noqa: E712
        best_cost, best_inv = g["cost_inr_per_spec_kg"].min(), g["inventory_cost_inr"].min()
        for i, r in g.iterrows():
            w = {k: LEVEL_WEIGHT[x] for k, x in templates[force_template or r["template"]].items()}
            s = {"Cost": gap_score(r["cost_inr_per_spec_kg"], best_cost), "Inventory": gap_score(r["inventory_cost_inr"], best_inv, 1.5), **_known_scores(r, att)}
            s = {k: (None if v is None or v != v else v) for k, v in s.items()}
            have = {k: v for k, v in s.items() if v is not None}
            perf = sum(have[k] * w[k] for k in have) / sum(w[k] for k in have)
            q.at[i, "score_cost"], q.at[i, "score_inventory"] = s["Cost"], s["Inventory"]
            q.at[i, "score_delivery"], q.at[i, "score_quality"] = s["Delivery"], s["Quality"]
            q.at[i, "score_supply"], q.at[i, "score_compliance"] = s["Supply risk"], s["Compliance"]
            level = factcheck.item_level(r["vendor"], code)   # Good, Medium or Low, from the 10-condition checks
            q.at[i, "evidence_level"] = level
            q.at[i, "performance"] = perf
            q.at[i, "evidence_share"] = sum(w[k] for k in have) / sum(w.values())
            q.at[i, "sku_score"] = SCORE_MIX["performance"] * perf + SCORE_MIX["evidence"] * EVIDENCE_POINTS[level]
    # An item we can't price yet still shows what we know. It gets no total, so it stays out of the ranking.
    for i, r in q[(q["comparable"] != True) & (q["not_quoted"] != True)].iterrows():  # noqa: E712
        s = _known_scores(r, att)
        q.at[i, "score_delivery"], q.at[i, "score_quality"] = s["Delivery"], s["Quality"]
        q.at[i, "score_supply"], q.at[i, "score_compliance"] = s["Supply risk"], s["Compliance"]
        q.at[i, "evidence_level"] = factcheck.item_level(r["vendor"], r["rm_code"])
    for c in ATTR_COLS:
        q[c] = pd.to_numeric(q[c], errors="coerce")
    q["rank_in_sku"] = q[q["cleared_questionnaire"] == True].groupby("rm_code")["sku_score"].rank(ascending=False, method="min")  # noqa: E712
    names = data.vendors().set_index("Vendor")["Name"]
    out = []
    for vid, g in q.groupby("vendor"):
        sc = g[g["sku_score"].notna()]
        wsum = sc["spend_inr"].sum()
        out.append({"vendor": vid, "name": names[vid], "lines_quoted": int((g["not_quoted"] == False).sum()), "lines_scored": len(sc),  # noqa: E712
                    "lines_cleared": int(g["cleared_questionnaire"].sum()), "vendor_score": (sc["sku_score"] * sc["spend_inr"]).sum() / wsum if wsum else None,
                    "spend_scored_inr": wsum, "evidence_coverage": sc["evidence_share"].mean() if len(sc) else None})
    v = pd.DataFrame(out).sort_values("vendor_score", ascending=False, na_position="last")
    return q, v
