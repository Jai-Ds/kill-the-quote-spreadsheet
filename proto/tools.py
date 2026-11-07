"""Tools the agents can call. Each agent gets an allowlist. Validation here is code-enforced, not prompt-enforced."""
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz
import numpy as np
import openpyxl
import pandas as pd
from docx import Document

from . import attributes, data, db, engine, factcheck

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
PAGE = 12000


@dataclass
class Tool:
    name: str
    description: str
    props: dict
    fn: Callable
    strict: bool = True


def S(desc=""):
    return {"type": ["string", "null"], "description": desc}


def R(desc=""):
    return {"type": "string", "description": desc}


def N(desc=""):
    return {"type": ["number", "null"], "description": desc}


def file_to_text(path):
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".txt", ".eml"):
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        with fitz.open(p) as d:
            return "\n".join(pg.get_text() for pg in d)
    if ext == ".docx":
        d = Document(str(p))
        parts = [x.text for x in d.paragraphs if x.text.strip()]
        for t in d.tables:
            parts += [" | ".join(c.text for c in r.cells) for r in t.rows]
        return "\n".join(parts)
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(p, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"[Sheet: {ws.title}]")
            out += [" | ".join("" if c is None else str(c) for c in row) for row in ws.iter_rows(values_only=True) if any(c is not None for c in row)]
        return "\n".join(out)
    return ""


def _files(vendor):
    out = {}
    for m in db.thread(vendor):
        if m["direction"] == "in":
            for a in m["attachments"]:
                out[Path(a).name] = Path(a)
    return out


def _find(ctx, name):
    f = _files(ctx["vendor"])
    if name not in f:
        raise ValueError(f"No attachment called {name}. Available: {sorted(f)}")
    return f[name]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _grounded(ctx, quote):
    """Code-enforced citation check: a quote must exist in the vendor's text, unless it came from an image."""
    if not quote:
        return False
    src = ""
    has_image = False
    for m in db.thread(ctx["vendor"]):
        if m["direction"] == "in":
            src += " " + m["body"]
            for a in m["attachments"]:
                if Path(a).suffix.lower() in IMAGE_EXT:
                    has_image = True
                else:
                    src += " " + file_to_text(a)
    return has_image or _norm(quote)[:60] in _norm(src)


# ------------------------------------------------------------- reading
def list_files(ctx):
    mid = ctx.get("message_id")
    cur = [Path(a).name for a in db.message(mid)["attachments"]] if mid else []
    return {"in_this_message": cur, "all_from_vendor": sorted(_files(ctx["vendor"]))}


def read_attachment(ctx, file, offset):
    p = _find(ctx, file)
    if p.suffix.lower() in IMAGE_EXT:
        return "This is an image. Use view_image."
    t = file_to_text(p)
    o = int(offset or 0)
    chunk = t[o:o + PAGE]
    if not chunk.strip() and p.suffix.lower() == ".pdf":
        return "No text layer. Use view_image with a page number."
    more = f"\n[Continues: call again with offset {o + PAGE}]" if len(t) > o + PAGE else ""
    return chunk + more


def view_image(ctx, file, page):
    p = _find(ctx, file)
    if p.suffix.lower() == ".pdf":
        with fitz.open(p) as d:
            raw = d[int(page or 1) - 1].get_pixmap(dpi=130).tobytes("png")
        mt = "image/png"
    elif p.suffix.lower() in IMAGE_EXT:
        raw = p.read_bytes()
        mt = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    else:
        raise ValueError("Use read_attachment for this file.")
    return [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(raw).decode()}}]


def get_thread(ctx, limit):
    rows = db.thread(ctx["vendor"], int(limit or 6))
    return [{"direction": m["direction"], "subject": m["subject"], "body": m["body"][:1500], "attachments": [Path(a).name for a in m["attachments"]]} for m in rows]


def get_current_record(ctx):
    r = db.record(ctx["vendor"])
    lines = [{k: x for k, x in l.items() if k != "last_message"} for l in r["lines"]]   # ids would break replay
    return {"lines": lines, "not_quoted": r["not_quoted"], "discounts": r["discounts"], "terms": r["terms"], "claims": r["claims"], "coas": r["coas"]}


# ------------------------------------------------------------- writing the record
LINE_FIELDS = ["vendor_description", "price", "currency", "price_unit", "net_kg_per_unit", "density_g_ml", "strength_value", "strength_unit", "strength_marker", "moq_value", "moq_unit", "moq_text",
               "lead_time_days", "shelf_life_months", "remaining_shelf_months", "freight_inr_per_kg", "read_note"]


def save_quote_line(ctx, rm_code, source_file, source_quote, confidence, **fields):
    v = ctx["vendor"]
    allowed = data.rm_table()["RM code"].tolist()
    if rm_code not in allowed:
        raise ValueError(f"{rm_code} is not an RFx line. Lines: {allowed}. Do not save unrelated items.")
    if not _grounded(ctx, source_quote):
        raise ValueError("source_quote was not found in the vendor's documents. Re-read the document and quote it exactly.")
    if fields.get("price") is not None and fields["price"] <= 0:
        raise ValueError("Price must be positive.")
    if not 0 <= confidence <= 1:
        raise ValueError("Confidence must be between 0 and 1.")
    rec = db.record(v)
    line = next((l for l in rec["lines"] if l["rm_code"] == rm_code), None)
    if line is None:
        line = {"rm_code": rm_code}
        rec["lines"].append(line)
    changed = []
    for k, val in fields.items():
        if val is not None and line.get(k) != val:   # null means no new information: never erase a known value
            db.audit(v, rm_code, k, line.get(k), val, ctx.get("message_id"))
            line[k] = val
            changed.append(k)
    line.update({"source_file": source_file, "source_quote": source_quote, "confidence": confidence, "last_message": ctx.get("message_id")})
    rec["not_quoted"] = [n for n in rec["not_quoted"] if n["rm_code"] != rm_code]
    db.save_record(v, rec)
    ctx.setdefault("touched", []).append(rm_code)
    return {"saved": rm_code, "changed": changed}


def mark_not_quoted(ctx, rm_code, reason):
    v = ctx["vendor"]
    rec = db.record(v)
    if any(l["rm_code"] == rm_code for l in rec["lines"]):
        return "Already has a quote; left as is."
    rec["not_quoted"] = [n for n in rec["not_quoted"] if n["rm_code"] != rm_code] + [{"rm_code": rm_code, "reason": reason}]
    db.save_record(v, rec)
    return "ok"


def save_vendor_facts(ctx, certifications=None, **facts):
    v = ctx["vendor"]
    rec = db.record(v)
    terms = {"incoterm", "payment_terms", "validity", "freight_inr_per_kg", "freight_note"}
    for k, val in facts.items():
        if val is not None:
            (rec["terms"] if k in terms else rec["claims"])[k] = val
    if certifications:
        rec["claims"]["certifications"] = certifications
    db.save_record(v, rec)
    return "ok"


def save_discount(ctx, applies_to, pct, min_line_value_inr, condition, source_quote):
    if not _grounded(ctx, source_quote):
        raise ValueError("source_quote was not found in the vendor's documents.")
    rec = db.record(ctx["vendor"])
    rec["discounts"] = [d for d in rec["discounts"] if d.get("pct") != pct] + [{"applies_to": applies_to, "pct": pct, "min_line_value_inr": min_line_value_inr, "condition": condition}]
    db.save_record(ctx["vendor"], rec)
    return "ok"


def save_coa(ctx, rm_code, file, batch, mfg_date, retest_date, issue_date, strength_value, strength_unit, marker):
    rec = db.record(ctx["vendor"])
    rec["coas"] = [c for c in rec["coas"] if c.get("rm_code") != rm_code] + [dict(rm_code=rm_code, file=file, batch=batch, mfg_date=mfg_date, retest_date=retest_date, issue_date=issue_date, strength_value=strength_value, strength_unit=strength_unit, marker=marker)]
    db.save_record(ctx["vendor"], rec)
    return "ok"


def finish_extraction(ctx, summary, new_information):
    rec = db.record(ctx["vendor"])
    rec["summary"] = summary
    db.save_record(ctx["vendor"], rec)
    ctx["result"] = {"summary": summary, "new_information": new_information}
    ctx["done"] = True
    return "Done."


# ------------------------------------------------------------- triage and review
def submit_triage(ctx, intent, injection_suspected, sensitive_request, summary):
    ctx["result"] = {"intent": intent, "injection": injection_suspected, "sensitive": sensitive_request, "summary": summary}
    ctx["done"] = True
    return "ok"


def submit_review(ctx, verdict, problems):
    ctx["result"] = {"verdict": verdict, "problems": problems}
    ctx["done"] = True
    return "ok"


# ------------------------------------------------------------- rule engine access and liaison
def _issue_view(vendor):
    q = engine.build_quotes(db.engine_state())
    out = []
    if q.empty:
        return out
    tries = db.mailbox(vendor)["issue_tries"]
    limit = int(data.company()["Maximum clarification tries"])
    for _, r in q[q["vendor"] == vendor].iterrows():
        for i in r["issues"]:
            if i["action"] == "Ask":
                k = f"{r['rm_code']}|{i['code']}"
                out.append({"key": k, "rm_code": r["rm_code"], "material": r["material"], "issue": i["text"], "tries_used": tries.get(k, 0), "tries_left": max(0, limit - tries.get(k, 0))})
    return out


def get_open_issues(ctx):
    return {"issues": _issue_view(ctx["vendor"]), "rule": "Only issues with tries_left above 0 may be asked. Others are already marked Not enough data."}


def check_uom_rule(ctx, from_unit):
    u = data.sheet("UoM_Rules")
    hit = u[u["From"].astype(str).str.contains(str(from_unit), case=False, regex=False)]
    return hit.to_dict("records") or "No rule for this unit: ask the vendor."


def get_vendor_memory(ctx):
    return db.mailbox(ctx["vendor"])["summary"] or "No memory yet."


def update_vendor_memory(ctx, summary):
    db.set_summary(ctx["vendor"], summary[:1500])
    return "ok"


SENSITIVE_REPLY = "This is sensitive company information, so we will not be sharing it."
INTERNAL_WORDS = ("selling price", "retail price", "margin", "forecast", "opening stock", "safety stock", "bill of materials", "target price", "budget", "evaluation score", "ranking", "ranked", "shortlist")


def leak_check(v, body):
    """Code-enforced confidentiality. Company data can sit in the database, but it never goes in an email."""
    low = body.lower()
    hits = [f"internal term '{w}'" for w in INTERNAL_WORDS if w in low]
    if re.search(r"\bfg-\d+", low):
        hits.append("a finished-goods code")
    numbers = {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]{3,}", body)}
    f = data.sheet("Forecast_6M")
    plan = {int(x) for x in f.select_dtypes("number").to_numpy().ravel() if x == x}
    if numbers & plan:
        hits.append("a forecast volume")
    prices = {round(float(l["price"]), 2) for o in db.VENDORS if o != v for l in db.record(o)["lines"] if l.get("price")}
    shown = {round(float(n.replace(",", "")), 2) for n in re.findall(r"(?:Rs\.?|INR|₹|US\$|USD)\s*([\d,]+(?:\.\d+)?)", body)}
    if shown & prices:
        hits.append("another vendor's price")
    return hits


def draft_vendor_email(ctx, subject, body, issue_keys):
    v = ctx["vendor"]
    others = data.vendors().set_index("Vendor")["Name"].to_dict()
    for k, n in others.items():
        if k != v and n.split()[0].lower() in body.lower():
            raise ValueError(f"Blocked: the draft mentions another vendor ({n}). Vendors must not see each other.")
    leaks = leak_check(v, body)
    if leaks:
        raise ValueError(f"Blocked: the draft contains company information ({', '.join(leaks)}). Remove it. If the vendor asked for it, use only this sentence: {SENSITIVE_REPLY}")
    if ctx.get("sensitive") and SENSITIVE_REPLY not in body:
        raise ValueError(f"The vendor asked for company information. The email must include this exact sentence: {SENSITIVE_REPLY}")
    open_keys = {i["key"]: i for i in _issue_view(v)}
    spent = [k for k in issue_keys if k in open_keys and open_keys[k]["tries_left"] == 0]
    if spent:
        raise ValueError(f"These issues have no tries left, so remove them: {spent}")
    ctx["result"] = {"action": "email", "subject": subject, "body": body, "issue_keys": issue_keys}
    ctx["done"] = True
    return "Draft queued for buyer approval. Nothing has been sent."


def _must_reply(ctx):
    if ctx.get("sensitive"):
        raise ValueError(f"The vendor asked for company information, so draft a reply with this exact sentence: {SENSITIVE_REPLY}")


def escalate_to_buyer(ctx, title, detail):
    _must_reply(ctx)
    ctx["result"] = {"action": "escalate", "title": title, "detail": detail}
    ctx["done"] = True
    return "Escalated."


def no_action(ctx, reason):
    _must_reply(ctx)
    ctx["result"] = {"action": "none", "reason": reason}
    ctx["done"] = True
    return "ok"


# ------------------------------------------------------------- questionnaire
def get_recorded_answers(ctx):
    return [{k: a[k] for k in ("qid", "status", "summary", "evidence", "rating")} for a in db.answers(ctx["vendor"])]


def save_question_answers(ctx, answers):
    bank = set(attributes.Q_TO_ATTR)
    bad = [a["question_id"] for a in answers if a["question_id"] not in bank]
    if bad:
        raise ValueError(f"Unknown question ids: {bad}")
    known = {a["qid"]: a for a in db.answers(ctx["vendor"])}
    for a in answers:
        if known.get(a["question_id"], {}).get("status") == "answered" and a["status"] != "answered":
            continue   # never downgrade an answer the vendor already gave
        db.save_answer(ctx["vendor"], a["question_id"], a["status"], a["summary"], a["evidence"], a["evidence_file"], a["rating"], ctx.get("message_id"))
    ctx["saved"] = ctx.get("saved", 0) + len(answers)
    return f"Saved {len(answers)} answers."


def finish_mapping(ctx, summary):
    ctx["result"] = {"summary": summary}
    ctx["done"] = True
    return "Done."


def get_questionnaire_gaps(ctx):
    q = attributes.vendor_questions(ctx["vendor"])
    tries = db.mailbox(ctx["vendor"])["issue_tries"]
    q = q[q["applicable"] & q["mandatory"] & ~q["status"].isin(["answered", "refused"])]
    q = q.assign(tries_used=q["id"].map(lambda i: tries.get(f"Q|{i}", 0)))
    q = q[q["tries_used"] < int(data.company()["Maximum clarification tries"])].sort_values("knockout", ascending=False)
    return {"gaps": [{"key": f"Q|{r['id']}", "question": r["question"], "attribute": r["attribute"], "knockout": r["knockout"], "tries_used": r["tries_used"]} for _, r in q.iterrows()],
            "rule": "Ask every knockout gap, then at most 5 others, the ones that matter most for this vendor's lines."}


# ------------------------------------------------------------- evidence verification
def get_documents_to_check(ctx):
    v = ctx["vendor"]
    rec = db.record(v)
    files = [Path(a).name for a in db.message(ctx["message_id"])["attachments"]]
    coas = [{**c, "code_date_flags": factcheck.date_flags(c)} for c in rec["coas"]]
    lines = [{k: l.get(k) for k in ("rm_code", "vendor_description", "strength_value", "strength_unit", "strength_marker")} for l in rec["lines"]]
    return {"vendor": data.vendors().set_index("Vendor").loc[v, ["Name", "Type"]].to_dict(), "files_in_this_message": files, "coas_on_record": coas, "quoted_lines": lines, "stated_claims": rec.get("claims")}


def record_document_check(ctx, file, rm_code, document_type, issuer, not_met_reasons, reason, **conditions):
    if file not in _files(ctx["vendor"]):
        raise ValueError("That file was not sent by this vendor.")
    notes = {n["condition"]: n["why"] for n in not_met_reasons}
    checks = {k: {"met": bool(conditions[k]), "note": "" if conditions[k] else notes.get(k, ""), "by": "Agent"} for k in factcheck.KEYS}
    db.save_doc_check(ctx["vendor"], file, rm_code, document_type, issuer, checks, reason)
    ctx["checked"] = ctx.get("checked", 0) + 1
    ctx.setdefault("verdicts", []).append(f"{file}: {factcheck.verdict(ctx['vendor'], file, checks)}")
    return "Saved."


def finish_verification(ctx, summary):
    ctx["result"] = {"summary": summary}
    ctx["done"] = True
    return "Done."


# ------------------------------------------------------------- RFx co-pilot
def get_rfx_lines(ctx):
    r = data.sheet("RFx_Lines")
    return r[["Line", "RM code", "Material", "Spec strength", "Status", "RFx quantity: net 6M need (kg)", "First need-by date", "Max per delivery (kg)", "Storage zone", "Min remaining shelf life (months)"]].to_dict("records")


def get_storage(ctx):
    return data.sheet("Storage").to_dict("records")


def get_vendors(ctx):
    return data.vendors()[["Vendor", "Name", "Location", "Status", "Type"]].to_dict("records")


def update_rfx_draft(ctx, title, scope, line_notes, terms, questionnaire_focus, response_due):
    d = dict(title=title, scope=scope, line_notes=line_notes, terms=terms, questionnaire_focus=questionnaire_focus, response_due=response_due)
    db.save_rfx(draft=d)
    return "Draft updated."


# ------------------------------------------------------------- analyst
DICTIONARY = """quotes: one row per vendor x SKU. vendor, rm_code, material, template, relationship, cost_inr_per_spec_kg (landed Rs per spec-equivalent kg: the fair price), rfx_qty_kg, spend_inr, moq_kg, lead_days, late_days, remaining_shelf_months, write_off_kg, pallets, zone, inventory_cost_inr, coa_status, history_level, otif (fraction, NaN = no history), defect_rate (fraction, NaN = no history), claim_status, otif_claim_pct, defect_claim_pct, evidence_level (Good, Medium, Low), knockouts (list), cleared_questionnaire (bool: knockout questions passed; NOT the same as risk-free), comparable (bool), not_quoted (bool), sku_score, rank_in_sku, open_asks, risk_flags (list: LATE, SPACE_CLASH, MOQ_COVER, MOQ_SHELF, SHELF_FAIL, COA_CONFLICT, COA_STALE, COA_EXPIRED, CLAIM_CONTRADICTED, WITHHELD, STRENGTH_ADJUSTED).
attrs: one row per vendor x attribute (Cost, Delivery, Quality, Inventory, Supply risk, Compliance). vendor, attribute, questions, answered, answered_pct, backed, backed_pct (evidence-backed share), rating_score, refused.
vendors: one row per vendor. vendor, name, lines_quoted, lines_scored, lines_cleared, vendor_score, spend_scored_inr, evidence_coverage.
claims: one row per claim. vendor, Item, rm_code, Attribute, Claim type, Claim, Evidence provided, Conditions met (of 10), Evidence (Good, Medium, Low), Result (Pass, Fail).
answers: one row per vendor x question. vendor, id (Q1 to Q10), topic, attribute, status (answered, partial, refused, not_answered), evidence, summary, rating, applicable.
names: dict vendor id -> name. Use names, not V01, in anything you show."""


def get_data_dictionary(ctx):
    q = ctx["quotes"]
    return {"dictionary": DICTIONARY, "replies_in": sorted(q["vendor"].unique().tolist()), "rows": len(q)}


def get_evidence(ctx, vendor, rm_code):
    q = ctx["quotes"]
    r = q[(q["vendor"] == vendor) & (q["rm_code"] == rm_code)]
    if r.empty:
        return "No such quote."
    r = r.iloc[0]
    return {"trail": r["trail"], "issues": r["issues"], "source_file": r.get("source_file"), "source_quote": r.get("source_quote")}


BLOCK = ("import ", "__", "open(", "eval(", "exec(", "os.", "sys.", "getattr", "subprocess")
SAFE = ("len", "sum", "min", "max", "round", "sorted", "abs", "range", "list", "dict", "set", "str", "int", "float", "bool", "enumerate", "zip", "any", "all", "print", "isinstance", "tuple", "map", "filter")


def run_analysis(ctx, code):
    import builtins
    if any(w in code for w in BLOCK):
        raise ValueError("Blocked operation in code.")
    env = {"__builtins__": {k: getattr(builtins, k) for k in SAFE}, "pd": pd, "np": np, "quotes": ctx["quotes"].copy(), "vendors": ctx["vendors"].copy(), "attrs": ctx["attrs"].drop(columns=["waiting"]).copy(), "claims": ctx["claims"].copy(), "answers": ctx["answers"].copy(), "names": data.vendors().set_index("Vendor")["Name"].to_dict(), "result": None}
    exec(code, env)   # read-only copies, restricted builtins, local demo only
    r = env.get("result")
    ctx["code"] = code
    if isinstance(r, pd.DataFrame):
        ctx["table"] = r
        return {"rows": len(r), "preview": r.head(25).round(2).to_string(index=False)}
    return {"value": str(r)[:3000]}


def submit_answer(ctx, headline, cards=(), chart_type="none", chart_x=None, chart_y=(), chart_color=None, chart_title=None):
    t = ctx.get("table")
    if len(headline) > 170:
        raise ValueError("The headline must be one short sentence. The cards, chart and table carry the detail.")
    if t is None and not cards:
        raise ValueError("Give the answer as a table, a chart or cards. Set `result` to a DataFrame, or add metric cards.")
    if chart_type != "none":
        if t is None:
            raise ValueError("A chart needs a DataFrame in `result` from run_analysis.")
        missing = [c for c in [chart_x, *chart_y, *([chart_color] if chart_color else [])] if c not in t.columns]
        if missing:
            raise ValueError(f"Columns not in the last result: {missing}. It has: {list(t.columns)}")
        bad = [c for c in chart_y if not pd.api.types.is_numeric_dtype(t[c])]
        if bad or not chart_y:
            raise ValueError(f"chart_y must be numeric columns. Not numeric: {bad}")
    ctx["result"] = {"answer": headline, "cards": cards, "chart": None if chart_type == "none" else {"type": chart_type, "x": chart_x, "y": chart_y, "color": chart_color, "title": chart_title}}
    ctx["done"] = True
    return "ok"


_line = {
    "rm_code": R("RFx line this maps to, e.g. RM-003"),
    "vendor_description": S("Vendor's own product name"), "price": N("Number as quoted"), "currency": S("INR, USD..."), "price_unit": S("Unit the price is per: kg, L, drum, bag, box"),
    "net_kg_per_unit": N("Only if the vendor states net kg of one pack"), "density_g_ml": N("Only if stated"), "strength_value": N("Number"), "strength_unit": S("% or ppm"),
    "strength_marker": S("What strength is measured on, e.g. rosmarinic acid, carnosic acid, assay, peptide"), "moq_value": N("Number"), "moq_unit": S("kg, drum, bag..."), "moq_text": S("Exact wording if vague, e.g. one full lot"),
    "lead_time_days": N("Days; weeks x 7"), "shelf_life_months": N("Total"), "remaining_shelf_months": N("Guaranteed at delivery"), "freight_inr_per_kg": N("Only if a per-kg figure is stated for this line"),
    "source_file": R("File name, or email"), "source_quote": R("Short exact quote from the source"), "confidence": {"type": "number", "description": "0 to 1: how sure you are of this reading"}, "read_note": S("Anything uncertain"),
}
_cert = {"type": ["array", "null"], "items": {"type": "object", "properties": {"name": R(), "valid_to": S("YYYY-MM-DD"), "status": S()}, "required": ["name", "valid_to", "status"], "additionalProperties": False}}
_str_list = {"type": "array", "items": {"type": "string"}}

REGISTRY = {t.name: t for t in [
    Tool("list_files", "List attachments in the current message and from this vendor overall.", {}, list_files),
    Tool("read_attachment", "Read text from an Excel, Word, PDF or text attachment. Long files are paged.", {"file": R("File name"), "offset": N("Character offset, or null")}, read_attachment),
    Tool("view_image", "See an image attachment, or a page of a PDF as an image (for scans or layout).", {"file": R("File name"), "page": N("PDF page, or null")}, view_image),
    Tool("get_thread", "Recent messages in this vendor's mailbox.", {"limit": N("How many, default 6")}, get_thread),
    Tool("get_current_record", "What is already stored for this vendor: lines, terms, claims, COAs.", {}, get_current_record),
    Tool("save_quote_line", "Create or update one quote line. Null fields keep any stored value. Rejected if the quote is not in the source.", _line, save_quote_line, False),
    Tool("mark_not_quoted", "Record that the vendor explicitly declined a line. Silence is not a decline.", {"rm_code": R(), "reason": R("Stated reason")}, mark_not_quoted),
    Tool("save_vendor_facts", "Save terms and questionnaire answers. Null means not stated in this message.", {
        "incoterm": S(), "payment_terms": S(), "validity": S(), "freight_inr_per_kg": N("General per-kg freight"), "freight_note": S(), "vendor_type": S("manufacturer, distributor, trader, mixed"), "otif_pct": N("Claimed; 'above 96' = 96"), "defect_pct": N("Claimed; 'below 1%' = 1"),
        "certifications": _cert, "records_sharing": S("yes, summary, refused, none_available, not_stated"), "sds": S("provided, later, not_stated"), "coa_policy": S("attached, with_dispatch, after_order_only, not_stated"),
        "regulatory_ok": {"type": ["boolean", "null"]}, "cold_chain": S("validated_logger, insulated_no_logger, none, not_stated"), "references": S(), "continuity": S()}, save_vendor_facts, False),
    Tool("save_discount", "Save a discount or rebate, including ones in footnotes.", {"applies_to": _str_list, "pct": {"type": "number"}, "min_line_value_inr": N("Line value it needs, or null"), "condition": R("Wording"), "source_quote": R("Exact quote")}, save_discount),
    Tool("save_coa", "Save a Certificate of Analysis. Dates are YYYY-MM-DD.", {"rm_code": R(), "file": R(), "batch": R(), "mfg_date": S(), "retest_date": S(), "issue_date": S(), "strength_value": N(), "strength_unit": S(), "marker": S()}, save_coa),
    Tool("finish_extraction", "Call last, once everything in this message is saved.", {"summary": R("One sentence, including anything odd"), "new_information": {"type": "boolean"}}, finish_extraction),
    Tool("submit_triage", "Report your classification.", {"intent": {"type": "string", "enum": ["quote", "clarification_answer", "vendor_question", "refusal", "auto_reply", "other"]}, "injection_suspected": {"type": "boolean"}, "sensitive_request": {"type": "boolean", "description": "True if the vendor asks for company information it should not have"}, "summary": R("One sentence")}, submit_triage),
    Tool("submit_review", "Report the review result.", {"verdict": {"type": "string", "enum": ["pass", "fail"]}, "problems": {"type": "array", "items": {"type": "object", "properties": {"rm_code": S(), "field": R(), "stored": S(), "source_says": R(), "evidence": R()}, "required": ["rm_code", "field", "stored", "source_says", "evidence"], "additionalProperties": False}}}, submit_review),
    Tool("get_recorded_answers", "Questionnaire answers already recorded for this vendor.", {}, get_recorded_answers),
    Tool("save_question_answers", "Record answers to questionnaire questions.", {"answers": {"type": "array", "items": {"type": "object", "properties": {
        "question_id": R("Q1 to Q10"), "status": {"type": "string", "enum": ["answered", "partial", "refused"]}, "summary": R("What the vendor said, in a few words"),
        "evidence": {"type": "string", "enum": ["vendor_statement", "document"]}, "evidence_file": S("Document that backs it, or null"), "rating": {"type": "string", "enum": ["good", "ok", "weak"]}},
        "required": ["question_id", "status", "summary", "evidence", "evidence_file", "rating"], "additionalProperties": False}}}, save_question_answers),
    Tool("finish_mapping", "Call last.", {"summary": R("One sentence")}, finish_mapping),
    Tool("get_questionnaire_gaps", "Mandatory questionnaire questions still unanswered by this vendor.", {}, get_questionnaire_gaps),
    Tool("get_documents_to_check", "Documents in this message, COAs on record with code date flags, and the vendor's claims.", {}, get_documents_to_check),
    Tool("record_document_check", "Record the 10 conditions for one evidence document. Skip price sheets and proposals.", {"file": R("File name"), "rm_code": S("RFx line it relates to, or null"),
         "document_type": {"type": "string", "enum": ["coa", "certificate", "declaration", "temperature_log", "test_report", "other"]}, "issuer": R("Who issued it, as shown on the document"),
         **{k: {"type": "boolean", "description": d} for k, _, d in factcheck.CONDITIONS},
         "not_met_reasons": {"type": "array", "description": "One entry for each condition not met", "items": {"type": "object", "properties": {"condition": {"type": "string", "enum": factcheck.KEYS}, "why": R("A few words on what you saw")}, "required": ["condition", "why"], "additionalProperties": False}},
         "reason": R("One or two plain sentences for the buyer")}, record_document_check, False),
    Tool("finish_verification", "Call last.", {"summary": R("One sentence")}, finish_verification),
    Tool("get_open_issues", "Open questions from the rule engine, with tries left.", {}, get_open_issues),
    Tool("check_uom_rule", "Company rule for a unit: assume, confirm or ask.", {"from_unit": R("e.g. drum, L, ppm")}, check_uom_rule),
    Tool("get_vendor_memory", "Rolling summary of this vendor relationship in this RFx.", {}, get_vendor_memory),
    Tool("update_vendor_memory", "Replace the rolling summary. Keep what still matters: positions, promises, tone, unresolved points.", {"summary": R("Under 150 words")}, update_vendor_memory),
    Tool("draft_vendor_email", "Queue one email for buyer approval. This does not send it.", {"subject": R(), "body": R(), "issue_keys": {**_str_list, "description": "Issue keys covered"}}, draft_vendor_email),
    Tool("escalate_to_buyer", "Hand something to the buyer that needs a human decision.", {"title": R(), "detail": R()}, escalate_to_buyer),
    Tool("no_action", "End with nothing to send.", {"reason": R()}, no_action),
    Tool("get_rfx_lines", "RFx lines computed from forecast x BOM.", {}, get_rfx_lines),
    Tool("get_storage", "Warehouse space by zone.", {}, get_storage),
    Tool("get_vendors", "The vendors receiving this RFx. Every vendor receives all lines.", {}, get_vendors),
    Tool("update_rfx_draft", "Replace the RFx draft shown to the buyer.", {"title": R(), "scope": R("2-3 sentences"), "line_notes": {"type": "array", "items": {"type": "object", "properties": {"rm_code": R(), "note": R()}, "required": ["rm_code", "note"], "additionalProperties": False}}, "terms": _str_list, "questionnaire_focus": _str_list, "response_due": R()}, update_rfx_draft),
    Tool("get_data_dictionary", "Columns available for analysis.", {}, get_data_dictionary),
    Tool("get_evidence", "Conversion trail, flags and source quote for one vendor and SKU.", {"vendor": R("V01..V05"), "rm_code": R()}, get_evidence),
    Tool("run_analysis", "Run pandas on read-only copies of quotes and vendors. Set `result` to a DataFrame or value. No imports or file access.", {"code": R("Python")}, run_analysis),
    Tool("submit_answer", "Give the final answer. Every number must come from run_analysis. The last DataFrame in `result` is shown as a colour-coded table.", {
        "headline": R("One short sentence, under 25 words"),
        "cards": {"type": "array", "description": "Two to four key figures", "items": {"type": "object", "properties": {"label": R("A few words"), "value": R("The figure, formatted"), "tone": {"type": "string", "enum": ["good", "warn", "bad", "neutral"]}}, "required": ["label", "value", "tone"], "additionalProperties": False}},
        "chart_type": {"type": "string", "enum": ["bar", "stacked_bar", "grouped_bar", "line", "none"]}, "chart_x": S("Category column of the last result"), "chart_y": {**_str_list, "description": "Numeric columns of the last result, all in one unit"},
        "chart_color": S("Column that splits one numeric column into series, or null"), "chart_title": S("Says what the chart shows")}, submit_answer, False),
]}
