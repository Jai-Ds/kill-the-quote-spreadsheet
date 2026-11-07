"""SQLite system of record: mailboxes, messages, quote records, audit, approvals, events, agent traces."""
import json
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import data

DB = data.RUNTIME / "rfx.db"
CKPT = data.RUNTIME / "checkpoints.db"
MAIL = data.RUNTIME / "mail"
VENDORS = ["V01", "V02", "V03", "V04", "V05"]
_write = threading.Lock()
# Priority levels: High = 3, Medium = 2, Low = 1
DEFAULT_TEMPLATES = {
    "Cost first": {"Cost": 3, "Delivery": 2, "Quality": 1, "Inventory": 2, "Supply risk": 1, "Compliance": 1},
    "Quality first": {"Cost": 1, "Delivery": 2, "Quality": 3, "Inventory": 1, "Supply risk": 1, "Compliance": 3},
    "Reliability first": {"Cost": 1, "Delivery": 3, "Quality": 2, "Inventory": 1, "Supply risk": 3, "Compliance": 1},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rfx(id INTEGER PRIMARY KEY CHECK(id=1), status TEXT, draft TEXT, chat TEXT, sent_at REAL);
CREATE TABLE IF NOT EXISTS mailboxes(vendor TEXT PRIMARY KEY, stage TEXT, summary TEXT DEFAULT '', issue_tries TEXT DEFAULT '{}', busy INTEGER DEFAULT 0, updated_at REAL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, vendor TEXT, direction TEXT, sender TEXT, subject TEXT, body TEXT, attachments TEXT, origin TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS records(vendor TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS field_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, vendor TEXT, rm_code TEXT, field TEXT, old TEXT, new TEXT, message_id INTEGER, at REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, vendor TEXT, actor TEXT, mode TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY AUTOINCREMENT, vendor TEXT, kind TEXT, title TEXT, payload TEXT, status TEXT, thread_id TEXT, created_at REAL, decided_at REAL);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, thread TEXT, agent TEXT, vendor TEXT, started REAL, seconds REAL, turns INTEGER, input_tokens INTEGER, output_tokens INTEGER, cache_read INTEGER, cache_write INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS answers(vendor TEXT, qid TEXT, status TEXT, summary TEXT, evidence TEXT, evidence_file TEXT, rating TEXT, message_id INTEGER, at REAL, PRIMARY KEY(vendor,qid));
CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, version INTEGER, weights TEXT, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS doc_audits(vendor TEXT, file TEXT, rm_code TEXT, document_type TEXT, issuer TEXT, checks TEXT, reason TEXT, at REAL, PRIMARY KEY(vendor,file));
CREATE TABLE IF NOT EXISTS item_tags(rm_code TEXT PRIMARY KEY, template TEXT);
CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, n INTEGER, kind TEXT, name TEXT, input TEXT, output TEXT, ms INTEGER, is_error INTEGER);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    data.RUNTIME.mkdir(exist_ok=True)
    MAIL.mkdir(parents=True, exist_ok=True)
    with _write, conn() as c:
        c.executescript(SCHEMA)
        for col, kind in (("model", "TEXT"), ("replayed", "INTEGER DEFAULT 0")):
            try:
                c.execute(f"ALTER TABLE runs ADD COLUMN {col} {kind}")
            except sqlite3.OperationalError:
                pass   # already there
        c.execute("INSERT OR IGNORE INTO rfx(id,status,draft,chat) VALUES(1,'draft','null','[]')")
        c.execute("DELETE FROM templates WHERE name IN ('Critical Active','Commodity Base','Supply Security')")   # retire older names
        if not c.execute("SELECT 1 FROM templates").fetchone():
            for name, w in DEFAULT_TEMPLATES.items():
                c.execute("INSERT INTO templates(name,version,weights,note,created_at) VALUES(?,1,?,?,?)", (name, json.dumps(w), "Initial version", time.time()))
        for v in VENDORS:
            c.execute("INSERT OR IGNORE INTO mailboxes(vendor,stage,updated_at) VALUES(?,?,?)", (v, "Not started", time.time()))


def reset():
    for p in (DB, Path(str(DB) + "-wal"), Path(str(DB) + "-shm")):   # checkpoints stay: thread ids are unique
        p.unlink(missing_ok=True)
    shutil.rmtree(MAIL, ignore_errors=True)
    init()


def q(sql, *a):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, a).fetchall()]


def x(sql, *a):
    with _write, conn() as c:
        return c.execute(sql, a).lastrowid


init()


# ---- events
def event(vendor, actor, mode, text):
    """mode: auto, approval, buyer, system"""
    x("INSERT INTO events(at,vendor,actor,mode,text) VALUES(?,?,?,?,?)", time.time(), vendor, actor, mode, text)


def version():
    r = q("SELECT (SELECT COALESCE(MAX(id),0) FROM events) e,(SELECT COUNT(*) FROM approvals WHERE status='pending') a,(SELECT COALESCE(SUM(busy),0) FROM mailboxes) b")[0]
    return (r["e"], r["a"], r["b"])


# ---- rfx
def rfx():
    r = q("SELECT * FROM rfx")[0]
    r["draft"], r["chat"] = json.loads(r["draft"]), json.loads(r["chat"])
    return r


def save_rfx(draft=None, chat=None, status=None):
    r = rfx()
    x("UPDATE rfx SET draft=?,chat=?,status=?,sent_at=? WHERE id=1", json.dumps(r["draft"] if draft is None else draft, ensure_ascii=False),
      json.dumps(r["chat"] if chat is None else chat, ensure_ascii=False), status or r["status"], time.time() if status == "sent" else r["sent_at"])


# ---- mail
def add_message(vendor, direction, sender, subject, body, attachments=(), origin="manual"):
    return x("INSERT INTO messages(vendor,direction,sender,subject,body,attachments,origin,created_at) VALUES(?,?,?,?,?,?,?,?)",
             vendor, direction, sender, subject, body, json.dumps([str(a) for a in attachments]), origin, time.time())


def thread(vendor, limit=None):
    rows = q("SELECT * FROM messages WHERE vendor=? ORDER BY id", vendor)
    for r in rows:
        r["attachments"] = json.loads(r["attachments"])
    return rows[-limit:] if limit else rows


def message(mid):
    r = q("SELECT * FROM messages WHERE id=?", mid)[0]
    r["attachments"] = json.loads(r["attachments"])
    return r


# ---- mailbox
def mailbox(vendor):
    r = q("SELECT * FROM mailboxes WHERE vendor=?", vendor)[0]
    r["issue_tries"] = json.loads(r["issue_tries"])
    return r


def mailboxes():
    return [mailbox(v) for v in VENDORS]


def set_stage(vendor, stage):
    x("UPDATE mailboxes SET stage=?,updated_at=? WHERE vendor=?", stage, time.time(), vendor)


def set_busy(vendor, delta):
    x("UPDATE mailboxes SET busy=MAX(0,busy+?) WHERE vendor=?", delta, vendor)


def set_summary(vendor, text):
    x("UPDATE mailboxes SET summary=? WHERE vendor=?", text, vendor)


def bump_tries(vendor, keys):
    t = mailbox(vendor)["issue_tries"]
    for k in keys:
        t[k] = t.get(k, 0) + 1
    x("UPDATE mailboxes SET issue_tries=? WHERE vendor=?", json.dumps(t), vendor)


# ---- record (what the agents have established about a vendor's offer)
EMPTY = {"lines": [], "not_quoted": [], "discounts": [], "terms": {}, "claims": {}, "coas": [], "summary": ""}


def record(vendor):
    r = q("SELECT data FROM records WHERE vendor=?", vendor)
    return json.loads(r[0]["data"]) if r else json.loads(json.dumps(EMPTY))


def save_record(vendor, rec):
    x("INSERT INTO records(vendor,data) VALUES(?,?) ON CONFLICT(vendor) DO UPDATE SET data=excluded.data", vendor, json.dumps(rec, ensure_ascii=False))


def audit(vendor, rm, field, old, new, mid):
    x("INSERT INTO field_audit(vendor,rm_code,field,old,new,message_id,at) VALUES(?,?,?,?,?,?,?)", vendor, rm, field, json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False), mid, time.time())


def engine_state():
    """The shape the deterministic rule engine reads."""
    ex = {r["vendor"]: json.loads(r["data"]) for r in q("SELECT * FROM records")}
    ex = {k: v for k, v in ex.items() if v.get("lines") or v.get("not_quoted")}
    return {"extractions": ex, "patches": {}, "clarifications": {m["vendor"]: {"issue_tries": m["issue_tries"]} for m in mailboxes()}}


# ---- questionnaire answers
def answers(vendor):
    return q("SELECT * FROM answers WHERE vendor=?", vendor)


def save_answer(vendor, qid, status, summary, evidence, evidence_file, rating, mid):
    x("""INSERT INTO answers(vendor,qid,status,summary,evidence,evidence_file,rating,message_id,at) VALUES(?,?,?,?,?,?,?,?,?)
         ON CONFLICT(vendor,qid) DO UPDATE SET status=excluded.status,summary=excluded.summary,evidence=excluded.evidence,evidence_file=excluded.evidence_file,rating=excluded.rating,message_id=excluded.message_id,at=excluded.at""",
      vendor, qid, status, summary, evidence, evidence_file, rating, mid, time.time())


# ---- priority templates, append-only so every version stays reproducible
def template_versions(name=None):
    rows = q("SELECT * FROM templates ORDER BY name, version") if not name else q("SELECT * FROM templates WHERE name=? ORDER BY version", name)
    for r in rows:
        r["weights"] = json.loads(r["weights"])
    return rows


def latest_templates():
    out = {}
    for r in template_versions():
        out[r["name"]] = r
    return out


def save_template(name, weights, note):
    v = max([r["version"] for r in template_versions(name)], default=0) + 1
    x("INSERT INTO templates(name,version,weights,note,created_at) VALUES(?,?,?,?,?)", name, v, json.dumps(weights), note, time.time())
    return v


# ---- document checks by the Evidence Evaluator: 10 yes-or-no conditions per document
def doc_checks(vendor):
    return [{**r, "checks": json.loads(r["checks"])} for r in q("SELECT vendor,file,rm_code,document_type,issuer,checks,reason FROM doc_audits WHERE vendor=? ORDER BY file", vendor)]


def save_doc_check(vendor, file, rm_code, document_type, issuer, checks, reason):
    x("""INSERT INTO doc_audits(vendor,file,rm_code,document_type,issuer,checks,reason,at) VALUES(?,?,?,?,?,?,?,?)
         ON CONFLICT(vendor,file) DO UPDATE SET rm_code=excluded.rm_code,document_type=excluded.document_type,issuer=excluded.issuer,checks=excluded.checks,reason=excluded.reason,at=excluded.at""",
      vendor, file, rm_code, document_type, issuer, json.dumps(checks), reason, time.time())


# ---- item to template tags: set once, defaulting to the workbook
def item_tags():
    tags = data.rm_table().set_index("RM code")["Priority template"].to_dict()
    tags.update({r["rm_code"]: r["template"] for r in q("SELECT * FROM item_tags")})
    return tags


def set_item_tag(code, template):
    x("INSERT INTO item_tags(rm_code,template) VALUES(?,?) ON CONFLICT(rm_code) DO UPDATE SET template=excluded.template", code, template)


# ---- approvals
def add_approval(vendor, kind, title, payload, thread_id):
    x("UPDATE approvals SET status='superseded' WHERE vendor=? AND kind=? AND status='pending'", vendor, kind)
    return x("INSERT INTO approvals(vendor,kind,title,payload,status,thread_id,created_at) VALUES(?,?,?,?,?,?,?)", vendor, kind, title, json.dumps(payload, ensure_ascii=False), "pending", thread_id, time.time())


def approvals(status="pending"):
    rows = q("SELECT * FROM approvals WHERE status=? ORDER BY id", status)
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows


def decide(aid, status):
    x("UPDATE approvals SET status=?,decided_at=? WHERE id=?", status, time.time(), aid)
