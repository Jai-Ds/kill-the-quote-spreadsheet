"""Live end-to-end test of the event-driven system, without the UI."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from proto import db, engine  # noqa: E402

db.reset()
from proto import runtime  # noqa: E402

db.save_rfx(draft={"title": "RFx KPC-2026-014", "scope": "Ingredients for our new serum.", "terms": ["Cold chain must be validated."], "response_due": "14 November 2026"})
only = sys.argv[1:] or db.VENDORS
runtime.STAGGER.update({v: 1 + i for i, v in enumerate(db.VENDORS)})
t0 = time.time()
runtime.send_rfx()
time.sleep(8)
while not runtime.idle():
    time.sleep(3)
    if time.time() - t0 > 560:
        print("TIMEOUT")
        break
print("done in", round(time.time() - t0), "s")
for e in db.q("SELECT vendor,actor,mode,text FROM events ORDER BY id"):
    print(e["vendor"], "|", e["actor"], "|", e["mode"], "|", e["text"][:190])
print([(m["vendor"], m["stage"]) for m in db.mailboxes()])
print("approvals:", [(a["vendor"], a["kind"], a["title"][:60]) for a in db.approvals()])
print(json.dumps(db.q("SELECT agent,COUNT(*) runs,SUM(turns) turns,ROUND(AVG(seconds),1) avg_s,SUM(input_tokens) inp,SUM(cache_read) cread,SUM(cache_write) cwrite,SUM(output_tokens) outp FROM runs GROUP BY agent"), indent=0))
print("tool errors:", db.q("SELECT name,COUNT(*) n FROM steps WHERE is_error=1 GROUP BY name"), db.q("SELECT output FROM steps WHERE is_error=1 LIMIT 4"))
q, v = engine.score(engine.build_quotes(db.engine_state()))
print(q[["vendor", "rm_code", "cost_inr_per_spec_kg", "cleared_questionnaire", "comparable", "sku_score"]].round(1).sort_values(["rm_code", "vendor"]).to_string(index=False))
