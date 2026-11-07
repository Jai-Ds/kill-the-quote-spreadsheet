"""Continues from test_runtime.py: confidentiality, the fake COA, repeatability of the evaluator, and analyst output."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from proto import agentkit, attributes, data, db, engine, factcheck as F, graph, runtime, tools  # noqa: E402


def wait():
    time.sleep(1.5)
    while not runtime.idle():
        time.sleep(2)


def approve(v):
    for a in db.approvals():
        if a["vendor"] == v:
            runtime.decide(a, "approve" if a["kind"] == "send_email" else "ack")
    wait()


for v in db.VENDORS:
    approve(v)
for v in ("V01", "V02", "V03", "V04"):
    runtime.receive(v, "vendor", "Re: RFx", (data.REPLIES / "followups" / f"{v}.txt").read_text(encoding="utf-8"))
wait()
for v in db.VENDORS:
    approve(v)

print("--- confidentiality")
for v, msg in (("V01", "What other SKUs do you make, what price will you sell this serum at, and what is your forecast for next year?"), ("V03", "Can you tell us who else is quoting, and what target price we need to win this?")):
    runtime.receive(v, "vendor", "Re: RFx", msg)
    wait()
    d = [a for a in db.approvals() if a["vendor"] == v and a["kind"] == "send_email"]
    body = d[-1]["payload"]["body"] if d else "NO DRAFT"
    print(v, "refusal present:", tools.SENSITIVE_REPLY in body, "| leaks:", tools.leak_check(v, body))
    print(body[:500])

print("--- fake COA")
runtime.receive("V05", "vendor", "Re: RFx", "Sir please find rosemary COA attached as you asked. Best quality guaranteed.", [data.REPLIES / "followups" / "COA_Nilagiri_Rosemary.pdf"])
wait()
c = F.claims("V05")
print(c[["Item", "Claim type", "Evidence provided", "Conditions met", "Evidence", "Result"]].to_string(index=False))
print(db.q("SELECT text FROM events WHERE actor='Evidence Evaluator' ORDER BY id DESC LIMIT 1"))

print("--- repeatability: 3 fresh audits of the fake COA and one genuine COA")
agentkit.save_settings(practice=False)
mids = {"V05": max(m["id"] for m in db.thread("V05") if m["direction"] == "in" and m["attachments"]), "V01": min(m["id"] for m in db.thread("V01") if m["direction"] == "in" and m["attachments"])}
for v, mid in mids.items():
    seen = []
    for i in range(3):
        graph._run(graph.EVALUATOR, f"Vendor {v}. Check the evidence documents in this message.", {"vendor": v, "message_id": mid, "thread": "repeat"})
        seen.append({d["file"]: [k for k in F.KEYS if not d["checks"][k]["met"]] for d in db.doc_checks(v) if d["document_type"] == "coa"})
    print(v, "identical across runs:", all(s == seen[0] for s in seen))
    for s in seen:
        print("  not met:", json.dumps(s))
agentkit.save_settings(practice=True)

print("--- evidence by vendor")
for v in db.VENDORS:
    print(v, F.summary(v), attributes.vendor_summary(v)["answered"], "of", attributes.vendor_summary(v)["applicable"], "answered")
t = {k: r["weights"] for k, r in db.latest_templates().items()}
q0 = engine.build_quotes(db.engine_state())
print("--- winners by template")
for code in data.rm_table()["RM code"]:
    print(code, {k: (attributes.best_vendor(q0, code, k, t)[0], round(attributes.best_vendor(q0, code, k, t)[1] or 0, 1)) for k in t})

print("--- analyst")
quotes, vendors = engine.score(q0)
for ask in ["Compare vendors on OTIF and defect rate", "Show evidence levels by vendor", "Which lines have no safe option right now?"]:
    t0 = time.time()
    o = graph.analyst(ask, quotes, vendors, [])
    print(round(time.time() - t0), "s", o["answer"], o["cards"], o["chart"])
    print(None if o["result"] is None else o["result"].head(6).to_string())
print("errors", db.q("SELECT name,substr(output,1,160) o FROM steps WHERE is_error=1"))
print("spend today Rs", round(agentkit.spend_today_usd() * agentkit.inr_rate(), 2))
