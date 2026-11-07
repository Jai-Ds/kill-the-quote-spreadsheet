"""The agent harness: tool-use loop, model routing, replay cache, spend cap, prompt caching and tracing."""
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import anthropic

from . import data, db

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
# USD per million tokens: input, output, cache read, 5-minute cache write
PRICES = {HAIKU: (0.10, 0.50, 0.01, 0.125), SONNET: (2, 10, 0.20, 2.5), "claude-opus-5-5": (4, 20, 0.20, 5)}
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # Haiku has no server-side fallback
FINISHERS = {"submit_triage", "submit_review", "finish_extraction", "finish_mapping", "finish_verification", "draft_vendor_email", "escalate_to_buyer", "no_action", "submit_answer"}
REPLAY = data.RUNTIME / "replay"
REPLAY.mkdir(exist_ok=True)
SETTINGS = data.RUNTIME / "settings.json"
SPEND = data.RUNTIME / "spend.json"     # survives a demo reset, so resetting can't hide spend


def _load_env():
    # The key lives outside the Drive-synced project folder.
    for f in (Path.home() / ".aerchain" / ".env", Path(__file__).resolve().parents[1] / ".env"):
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
client = anthropic.Anthropic(max_retries=3, timeout=240)


class BudgetStop(Exception):
    pass


def settings():
    d = {"practice": True, "daily_cap_inr": 50}
    if SETTINGS.exists():
        d.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
    return d


def save_settings(**kw):
    SETTINGS.write_text(json.dumps({**settings(), **kw}), encoding="utf-8")


def inr_rate():
    return data.fx_rate()[0]


def spend_today_usd():
    if not SPEND.exists():
        return 0.0
    return json.loads(SPEND.read_text(encoding="utf-8")).get(str(date.today()), 0.0)


def _add_spend(usd):
    d = json.loads(SPEND.read_text(encoding="utf-8")) if SPEND.exists() else {}
    k = str(date.today())
    d[k] = d.get(k, 0.0) + usd
    SPEND.write_text(json.dumps(d), encoding="utf-8")


def cost_usd(model, inp, out, cr, cw):
    p = PRICES[model]
    return (inp * p[0] + out * p[1] + cr * p[2] + cw * p[3]) / 1e6


@dataclass
class Agent:
    name: str
    system: str          # static role, rules and shared RFx context: byte-identical across runs so it caches
    tools: list          # allowlist of tool names: an agent can only do what its tools allow
    effort: str = "medium"
    max_turns: int = 14
    model: str = HAIKU   # default route; graph.route_extraction() can raise it for a specific run


def _schema(t):
    # Strict mode guarantees schema-valid calls. The two wide record tools exceed its limit on optional
    # fields, so they are validated in code instead.
    if t.strict:
        return {"name": t.name, "description": t.description, "strict": True,
                "input_schema": {"type": "object", "properties": t.props, "required": list(t.props), "additionalProperties": False}}
    need = [k for k, v in t.props.items() if "null" not in (v.get("type") if isinstance(v.get("type"), list) else [v.get("type")])]
    return {"name": t.name, "description": t.description, "input_schema": {"type": "object", "properties": t.props, "required": need, "additionalProperties": False}}


def _short(v, n=1500):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + f"... [{len(s) - n} more chars]"


def _key(model, agent, messages):
    """Identifies a request by meaning: tool-call ids and thinking blocks don't change what was asked."""
    def clean(c):
        if isinstance(c, list):
            return [clean(x) for x in c if not (isinstance(x, dict) and x.get("type") == "thinking")]
        if isinstance(c, dict):
            return {k: clean(v) for k, v in c.items() if k not in ("id", "tool_use_id", "signature")}
        return c
    raw = json.dumps([model, agent.system, agent.tools, agent.effort, clean(messages)], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _call(agent, model, system, schemas, messages):
    """One model call. In practice mode an identical earlier request replays its real response for free."""
    key = _key(model, agent, messages)
    f = REPLAY / f"{key}.json"
    if settings()["practice"] and f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["content"], d["stop_reason"], (0, 0, 0, 0), True
    cap = settings()["daily_cap_inr"]
    if spend_today_usd() * inr_rate() >= cap:
        raise BudgetStop(f"Daily AI limit of Rs {cap} reached. Raise it in the sidebar, or practise with saved answers.")
    kw = {"betas": [FALLBACK_BETA], "extra_body": {"fallbacks": "default"}} if model != HAIKU else {}
    r = client.beta.messages.create(
        model=model, max_tokens=16000, system=system, tools=schemas, messages=messages,
        thinking={"type": "adaptive"}, output_config={"effort": agent.effort},
        cache_control={"type": "ephemeral"},   # moves the cache breakpoint forward each turn
        **kw,
    )
    if r.stop_reason == "refusal":
        raise RuntimeError("The model declined this request.")
    content = [b.model_dump(mode="json", exclude_none=True) for b in r.content]
    f.write_text(json.dumps({"content": content, "stop_reason": r.stop_reason}, ensure_ascii=False), encoding="utf-8")
    u = r.usage
    tok = (u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
    _add_spend(cost_usd(model, *tok))
    return content, r.stop_reason, tok, False


def run_agent(agent, task, ctx, registry, model=None):
    """Runs one agent to completion. `task` holds only the volatile part of the context."""
    model = model or agent.model
    tools = [registry[n] for n in agent.tools]
    schemas = [_schema(t) for t in tools]
    by_name = {t.name: t for t in tools}
    system = [{"type": "text", "text": agent.system, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": task}]
    start = time.time()
    run_id = db.x("INSERT INTO runs(thread,agent,vendor,started,status,model,replayed) VALUES(?,?,?,?,?,?,0)", ctx.get("thread"), agent.name, ctx.get("vendor"), start, "running", model)
    ctx["run_id"] = run_id
    tot = [0, 0, 0, 0]
    n = status = nudges = replayed = 0
    text = ""
    try:
        for turn in range(agent.max_turns):
            n = turn + 1
            content, stop, tok, hit = _call(agent, model, system, schemas, messages)
            replayed += int(hit)
            tot = [a + b for a, b in zip(tot, tok)]
            messages.append({"role": "assistant", "content": content})   # append-only keeps cache and thinking valid
            text = "".join(b.get("text", "") for b in content if b["type"] == "text")
            if text:
                db.x("INSERT INTO steps(run_id,n,kind,name,input,output,ms,is_error) VALUES(?,?,?,?,?,?,?,0)", run_id, n, "text", "", "", _short(text), 0)
            calls = [b for b in content if b["type"] == "tool_use"]
            if stop != "tool_use" or not calls:
                ends = FINISHERS & set(by_name)
                if ends and not ctx.get("done") and nudges < 2:   # an agent must end through its tool, not by just stopping
                    nudges += 1
                    messages.append({"role": "user", "content": f"You have not finished. End by calling one of: {sorted(ends)}."})
                    continue
                break
            results = []
            for b in calls:   # all results go back in one message, so parallel calls keep working
                t0 = time.time()
                err = 0
                try:
                    if b["name"] not in by_name:
                        raise ValueError(f"Tool {b['name']} is not available to this agent.")
                    out = by_name[b["name"]].fn(ctx, **b["input"])
                except Exception as e:   # the model sees tool errors and can repair its own call
                    out, err = f"ERROR: {e}", 1
                is_image = isinstance(out, list) and out and isinstance(out[0], dict) and out[0].get("type") == "image"
                body = out if is_image or isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
                db.x("INSERT INTO steps(run_id,n,kind,name,input,output,ms,is_error) VALUES(?,?,?,?,?,?,?,?)", run_id, n, "tool", b["name"], _short(b["input"]), _short("[image]" if is_image else out), int((time.time() - t0) * 1000), err)
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": body, "is_error": bool(err)})
            messages.append({"role": "user", "content": results})
            if ctx.get("done"):
                break
        else:
            raise RuntimeError(f"{agent.name} hit its limit of {agent.max_turns} turns.")
        status = "ok"
        return text
    except Exception:
        status = "error"
        raise
    finally:
        db.x("UPDATE runs SET seconds=?,turns=?,input_tokens=?,output_tokens=?,cache_read=?,cache_write=?,status=?,replayed=? WHERE id=?",
             round(time.time() - start, 1), n, tot[0], tot[1], tot[2], tot[3], status or "error", replayed, run_id)
