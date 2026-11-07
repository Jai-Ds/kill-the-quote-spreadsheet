"""Offline test of routing, replay and the spend cap. Uses a fake model, so it costs nothing."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ["PROTO_RUNTIME"] = tempfile.mkdtemp(prefix="cost_test_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from proto import agentkit as K  # noqa: E402
from proto import db, graph, tools  # noqa: E402


class Block(NS):
    def model_dump(self, **_):
        return {k: v for k, v in vars(self).items()}


calls = []


def fake(**kw):
    calls.append(kw["model"])
    if "fallbacks" in kw.get("extra_body", {}):
        assert kw["model"] != K.HAIKU, "Haiku must not send fallbacks"
    last = kw["messages"][-1]
    if isinstance(last["content"], list):      # a tool result came back: finish
        content = [Block(type="text", text="done")]
        stop = "end_turn"
    else:
        content = [Block(type="tool_use", id=f"t{len(calls)}", name="get_rfx_lines", input={})]
        stop = "tool_use"
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=100, output_tokens=1000, cache_read_input_tokens=0, cache_creation_input_tokens=0))


K.client = NS(beta=NS(messages=NS(create=fake)))
ctx = lambda: {"vendor": None, "thread": "t"}  # noqa: E731
A = K.Agent("Test", "system", ["get_rfx_lines"], model=K.HAIKU)
checks = []


def check(name, ok):
    checks.append(ok)
    print("PASS" if ok else "FAIL", name)


K.save_settings(practice=True, daily_cap_inr=50)
K.run_agent(A, "task one", ctx(), tools.REGISTRY)
check("first run calls the model", len(calls) == 2)
spent = K.spend_today_usd()
check("cost uses Haiku price", abs(spent - 2 * (100 * 0.10 + 1000 * 0.50) / 1e6) < 1e-9)
K.run_agent(A, "task one", ctx(), tools.REGISTRY)
check("identical run replays with no model call", len(calls) == 2)
check("replay costs nothing", K.spend_today_usd() == spent)
K.run_agent(A, "task two", ctx(), tools.REGISTRY)
check("a new request still calls the model", len(calls) == 4)
K.save_settings(practice=False)
K.run_agent(A, "task one", ctx(), tools.REGISTRY)
check("practice off always calls the model", len(calls) == 6)
K.save_settings(practice=True)
K.run_agent(A, "x", ctx(), tools.REGISTRY, model=K.SONNET)
check("router override uses Sonnet", calls[-1] == K.SONNET)

K.save_settings(practice=False, daily_cap_inr=0)
try:
    K.run_agent(A, "task three", ctx(), tools.REGISTRY)
    check("spend cap stops the agent", False)
except K.BudgetStop:
    check("spend cap stops the agent", True)
K.save_settings(practice=True, daily_cap_inr=50)

d = db.MAIL / "x"
d.mkdir(parents=True, exist_ok=True)
txt = d / "a.txt"
txt.write_text("x")
img = d / "a.jpg"
img.write_bytes(b"x")
m1 = db.add_message("V01", "in", "v", "s", "b", [txt])
m2 = db.add_message("V01", "in", "v", "s", "b", [img])
check("text goes to Haiku", graph.route_extraction({"message_id": m1})[0] == K.HAIKU)
check("photo goes to Sonnet", graph.route_extraction({"message_id": m2})[0] == K.SONNET)
check("reviewer failure escalates to Sonnet", graph.route_extraction({"message_id": m1, "review_problems": [{"x": 1}]})[0] == K.SONNET)
check("no Opus anywhere", all(a.model != "claude-opus-5-5" for a in graph.AGENTS))
print({a.name: (a.model.replace("claude-", ""), a.effort) for a in graph.AGENTS})
print(f"{sum(checks)} of {len(checks)} passed")
shutil.rmtree(os.environ["PROTO_RUNTIME"], ignore_errors=True)
