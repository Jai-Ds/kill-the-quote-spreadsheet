"""Event-driven runtime. A new mailbox message triggers the agents in the background, one run at a time per vendor."""
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import data, db, graph, tools

POOL = ThreadPoolExecutor(3, thread_name_prefix="agent")
LOCKS = {v: threading.Lock() for v in db.VENDORS}
ROOT = Path(__file__).resolve().parents[1]
QUESTIONNAIRE = ROOT / "Base Data" / "Kesavi_Vendor_Questionnaire_10Q.docx"
STAGGER = {"V01": 3, "V03": 8, "V02": 13, "V04": 18, "V05": 23}


def refresh_stage(v):
    """Derives each mailbox's stage from facts, so the buyer's view can't drift from reality."""
    t = db.thread(v)
    last_in = max([m["id"] for m in t if m["direction"] == "in"], default=0)
    last_out = max([m["id"] for m in t if m["direction"] == "out"], default=0)
    if not t:
        stage = "Not started"
    elif any(a["vendor"] == v for a in db.approvals()):
        stage = "Needs your approval"
    elif not last_in:
        stage = "Awaiting first reply"
    else:
        issues = tools._issue_view(v)
        live = [i for i in issues if i["tries_left"] > 0]
        spent = [i for i in issues if i["tries_left"] == 0]
        if not live and spent:
            stage = "Ready, with gaps"
        elif last_out > last_in:
            stage = "Waiting for vendor"
        elif live:
            stage = "Open questions"
        else:
            stage = "Ready for evaluation"
    db.set_stage(v, stage)


def _guard(v, fn, label):
    with LOCKS[v]:
        db.set_busy(v, 1)
        try:
            fn()
        except Exception as e:
            msg = str(e)
            if "credit balance" in msg:
                msg = "API credit has run out. Add credit, then send the message again."
            db.event(v, "Orchestrator", "system", f"{label} stopped: {msg[:220]}")
            traceback.print_exc()
        finally:
            db.set_busy(v, -1)
            refresh_stage(v)


def on_message(v, mid):
    """The trigger: every inbound message wakes the agents, with no user action."""
    db.event(v, "Orchestrator", "auto", "New message received. Agents activated.")
    POOL.submit(_guard, v, lambda: graph.start(v, mid), "Processing")


def receive(v, sender, subject, body, attachments=(), origin="manual"):
    mid = db.add_message(v, "in", sender, subject, body, attachments, origin)
    refresh_stage(v)
    on_message(v, mid)
    return mid


def no_reply(v):
    db.event(v, "Buyer", "buyer", "Marked as no reply. Asking the agent for the next step.")
    POOL.submit(_guard, v, lambda: graph.start(v, None, "no_reply"), "Follow-up")


def decide(appr, action, subject=None, body=None):
    if appr["kind"] != "send_email":
        db.decide(appr["id"], "acknowledged")
        db.event(appr["vendor"], "Buyer", "buyer", f"Acknowledged: {appr['title']}")
        refresh_stage(appr["vendor"])
        return
    db.decide(appr["id"], "approved" if action == "approve" else "rejected")
    if action != "approve":
        db.event(appr["vendor"], "Buyer", "buyer", f"Rejected the draft: {appr['title']}")
    v = appr["vendor"]
    POOL.submit(_guard, v, lambda: graph.resume(appr["thread_id"], {"action": action, "subject": subject, "body": body}), "Sending")


def _parse_email(path):
    t = path.read_text(encoding="utf-8")
    head, body = t.split("\n\n", 1)
    h = dict(re.findall(r"^(\w+): (.*)$", head, re.M))
    return h.get("From", ""), h.get("Subject", ""), body.strip()


def _deliver_initial(v):
    d = data.REPLIES / v
    sender, subject, body = _parse_email(d / "email.txt")
    files = [f for f in sorted(d.iterdir()) if f.name != "email.txt"]
    receive(v, sender, subject, body, files, origin="auto")


def send_rfx():
    """Sends the RFx to all vendors, then simulates each vendor's automated first reply on a staggered timer."""
    r = db.rfx()
    d = r["draft"] or {}
    names = data.vendors().set_index("Vendor")["Name"].to_dict()
    db.save_rfx(status="sent")
    for v in db.VENDORS:
        lines = data.rm_table()["Material"].tolist()
        body = f"Dear {names[v]},\n\n{d.get('scope', 'Please quote for the lines below.')}\n\nThe lines in this RFx are below. Please tell us which ones you can supply and quote only those:\n" + "\n".join(f"- {x}" for x in lines) + \
               "\n\nTerms:\n" + "\n".join(f"- {x}" for x in d.get("terms", [])) + f"\n\nPlease respond by {d.get('response_due', '14 November 2026')} and complete the attached questionnaire. Reply in whatever format suits you.\n\nCategory Manager, Kesavi Personal Care"
        db.add_message(v, "out", "Category Manager, Kesavi", d.get("title", "RFx KPC-2026-014"), body, [QUESTIONNAIRE], "agent")
        refresh_stage(v)
        threading.Timer(STAGGER[v], _deliver_initial, [v]).start()
    db.event(None, "Buyer", "buyer", "RFx sent to 5 vendors. Automated first replies will arrive shortly.")


def idle():
    return sum(m["busy"] for m in db.mailboxes()) == 0
