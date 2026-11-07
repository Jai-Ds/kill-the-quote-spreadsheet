"""Shared helpers for the app pages."""
import html
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from . import agentkit, attributes, data, db, engine

FORMATS = {"V01": "Excel", "V02": "PDF", "V03": "Word", "V04": "Photo, USD", "V05": "Email"}
STAGE_COLOR = {"Not started": "gray", "Awaiting first reply": "gray", "Needs your approval": "red", "Open questions": "orange", "Waiting for vendor": "blue", "Ready for evaluation": "green", "Ready, with gaps": "violet"}
MODE = {"auto": ("Automated", "blue"), "approval": ("Needs approval", "red"), "buyer": ("Buyer", "green"), "system": ("System", "orange")}




def templates():
    return list(db.latest_templates())


def latest_rows():
    return db.latest_templates()


def latest():
    return {k: r["weights"] for k, r in db.latest_templates().items()}


def template_options():
    """Label -> weights for every template version, newest first within each name."""
    out = {}
    for name in db.latest_templates():
        for r in reversed(db.template_versions(name)):
            out[f"{name} v{r['version']}"] = r["weights"]
    return out


@st.fragment(run_every="2s")
def live():
    """Polls the database so agent updates appear without any click."""
    v = db.version()
    if st.session_state.get("db_version") != v:
        first = "db_version" not in st.session_state
        st.session_state.db_version = v
        if not first:
            st.rerun()
    busy = v[2]
    text = (f"{busy} agent run(s) in progress", "Agents working", "") if busy else ("Nothing in progress", "Agents idle", " idle")
    st.html(f'<div class="agent-state"><span class="pulse{text[2]}"></span><div><b>{text[1]}</b><small>{text[0]}</small></div></div>')


def spend_panel():
    s = agentkit.settings()
    rate = agentkit.inr_rate()
    used = agentkit.spend_today_usd() * rate
    pct = min(used / max(s["daily_cap_inr"], 1), 1.0)
    st.html(f'<div class="spend"><div class="top"><span>AI spend today</span><b>Rs {used:.0f} / Rs {s["daily_cap_inr"]}</b></div><div class="track"><i style="width:{pct:.0%}"></i></div></div>')
    p = st.toggle("Practice mode", value=s["practice"], help="An identical request replays the saved real answer for free. Anything new still calls the model. Turn off to make every call fresh.")
    with st.expander("Reset the demo"):
        st.caption("Clears the RFP, mailboxes and records. Spend and saved answers stay.")
        if st.button("Reset", width="stretch"):
            if sum(m["busy"] for m in db.mailboxes()) == 0:
                db.reset()
                st.session_state.clear()
                st.rerun()
    cap = st.number_input("Daily limit (Rs)", 0, 2000, int(s["daily_cap_inr"]), 10, help="Agents pause at this limit.")
    if p != s["practice"] or cap != s["daily_cap_inr"]:
        agentkit.save_settings(practice=p, daily_cap_inr=cap)


def state():
    return db.engine_state()


def names():
    return data.vendors().set_index("Vendor")["Name"].to_dict()


def short(v):
    return names()[v].split()[0]


def quotes():
    return engine.build_quotes(state())


def scored(force=None):
    t = {**latest(), **template_options()}
    return engine.score(quotes(), t, force)


def need_replies():
    if not state()["extractions"]:
        st.info("This fills in as soon as the agents have read the first vendor reply.", title="No vendor data yet", icon=":material/hourglass_empty:")
        st.page_link("app_pages/inbox.py", label="Open vendor inbox", icon=":material/mail:")
        st.stop()


def inr(v):
    return "-" if v is None or v != v else f"Rs {v:,.0f}"


def ago(t):
    s = int(time.time() - t)
    return f"{s}s ago" if s < 60 else f"{s // 60}m ago" if s < 3600 else f"{s // 3600}h ago"


# ---- colour coding. Status colours mean a state; vendor colours follow the vendor, whatever the chart.
GREEN, AMBER, RED, GRAY = ("#e2f3ea", "#197a55"), ("#fbf0d9", "#a56708"), ("#f9e4e4", "#b23a3a"), ("#eef1ef", "#5e6b65")
STATUS = {"pass": GREEN, "good": GREEN, "met": GREEN, "answered": GREEN, "proceed": GREEN, "yes": GREEN, "cleared": GREEN, "best": GREEN, "document": GREEN, "our records": GREEN, "valid": GREEN,
          "medium": AMBER, "partly": AMBER, "partial": AMBER, "wait": AMBER, "ok": AMBER, "stale": AMBER, "proceed with conditions": AMBER, "statement only": AMBER, "conflict": AMBER,
          "fail": RED, "low": RED, "not met": RED, "refused": RED, "hold": RED, "no": RED, "do not proceed": RED, "not answered": RED, "weak": RED, "expired": RED, "failed": RED, "none": RED,
          "watch": AMBER, "cleared but risky": AMBER, "failed knockout": RED, "no history": GRAY, "n/a": GRAY, "no bidder": GRAY}
TONE = {"good": GREEN, "warn": AMBER, "bad": RED, "neutral": GRAY}
VENDOR_COLOR = {"Kovai": "#2a78d6", "Tungabhadra": "#eb6834", "Vembanad": "#1baf7a", "Lumen": "#eda100", "Nilagiri": "#e87ba4"}
STATE_COLOR = {"Good": "#1baf7a", "Pass": "#1baf7a", "Medium": "#eda100", "Low": "#e34948", "Fail": "#e34948"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def tint(v):
    c = STATUS.get(str(v).strip().lower())
    return f"background-color: {c[0]}; color: {c[1]}; font-weight: 600" if c else ""


def colored(df, cols=None):
    """A Styler that colours status words in the given columns, or in every text column."""
    cols = [c for c in (cols or df.columns) if c in df.columns]
    fmt = {c: "{:,.2f}".format if df[c].dropna().mod(1).any() else "{:,.0f}".format for c in df.select_dtypes("number").columns}
    return df.style.map(tint, subset=cols).format(fmt, na_rep="-")


def cards(items):
    """Metric cards, coloured by what the figure means for the buyer."""
    if not items:
        return
    body = "".join(f'''<div class="metric {c.get('tone', 'neutral')}"><span>{esc(c['label'])}</span><strong>{esc(c['value'])}</strong>{f"<small>{esc(c['note'])}</small>" if c.get("note") else ""}</div>''' for c in items)
    st.html(f'<div class="metrics" style="grid-template-columns:repeat({len(items)},1fr)">{body}</div>')


def readable(df):
    """Vendor names instead of ids, and plain column headings."""
    n = {k: v.split()[0] for k, v in names().items()} | {v: v.split()[0] for v in names().values()}
    out = df.copy()
    for c in out.select_dtypes(exclude="number").columns:
        out[c] = out[c].map(lambda x: n.get(x, x) if isinstance(x, str) else ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
    return out.rename(columns=heading)


def heading(c):
    return c.replace("_", " ").strip().capitalize() if c == c.lower() else c


def _scale(values):
    known = {**VENDOR_COLOR, **STATE_COLOR}
    if all(v in known for v in values):
        return alt.Scale(domain=list(values), range=[known[v] for v in values])
    return alt.Scale(domain=list(values), range=[SERIES[i % len(SERIES)] for i in range(len(values))])


def chart(df, spec):
    """Draws one analyst chart. Each vendor and each state keeps its colour across charts."""
    x, ys, kind = heading(spec["x"]), [heading(y) for y in spec["y"]], spec["type"]
    color = heading(spec["color"]) if spec.get("color") else None
    d = df[[c for c in dict.fromkeys([x, *ys, color]) if c]].dropna(subset=ys).astype({x: object})
    d[x] = d[x].map(str)
    if color:
        long, val, ser = d, ys[0], color
    elif len(ys) > 1:
        long, val, ser = d.melt(id_vars=[x], value_vars=ys, var_name="Series", value_name="Value"), "Value", "Series"
    else:
        long, val, ser = d, ys[0], (x if kind != "line" and set(d[x]) <= set(VENDOR_COLOR) else None)
    tip = [alt.Tooltip(f"{c}:{'Q' if c == val else 'N'}") for c in dict.fromkeys([x, ser, val]) if c]
    order = list(dict.fromkeys(long[x]))
    if kind == "line":
        enc = {"x": alt.X(f"{x}:N", sort=order, title=None), "y": alt.Y(f"{val}:Q", title=val), "tooltip": tip}
        if ser:
            enc["color"] = alt.Color(f"{ser}:N", scale=_scale(list(dict.fromkeys(long[ser]))), title=None, legend=alt.Legend(orient="top"))
        c = alt.Chart(long).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=64)).encode(**enc)
        height = 340
    else:
        if kind == "bar" and not color and len(ys) == 1:
            order = list(long.sort_values(val, ascending=False)[x])
        enc = {"y": alt.Y(f"{x}:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)), "x": alt.X(f"{val}:Q", title=val, stack="zero" if kind == "stacked_bar" else None, axis=alt.Axis(tickCount=6)), "tooltip": tip}
        if ser:
            many = ser != x
            enc["color"] = alt.Color(f"{ser}:N", scale=_scale(list(dict.fromkeys(long[ser]))), title=None, legend=alt.Legend(orient="top") if many else None)
        else:
            enc["color"] = alt.value(SERIES[0])
        if kind == "grouped_bar" and ser and ser != x:
            enc["yOffset"] = alt.YOffset(f"{ser}:N")
        step = 20 if kind == "grouped_bar" and ser and ser != x else 30
        rows = len(order) * (long[ser].nunique() if kind == "grouped_bar" and ser and ser != x else 1)
        c = alt.Chart(long).mark_bar(cornerRadiusEnd=4, stroke="white", strokeWidth=1).encode(**enc)
        height = rows * step + 170   # the height includes the title, legend and axis
    if spec.get("title"):
        c = c.properties(title=alt.Title(spec["title"], anchor="start", fontSize=14))
    st.altair_chart(c.properties(height=height).configure_axis(grid=False, domainColor="#c9c8c2", tickColor="#c9c8c2").configure_view(stroke=None), use_container_width=True)


def glossary():
    with st.expander("What the terms mean", icon=":material/menu_book:"):
        table(["Term", "Meaning"], [[f"<strong>{esc(t)}</strong>", esc(m)] for t, m in data.GLOSSARY])


# ---- page furniture: the layout language shared by every screen
def esc(x):
    return html.escape(str(x))


def load_style():
    st.html("<style>" + (Path(__file__).parent / "style.css").read_text(encoding="utf-8") + vendor_css() + "</style>")


def initials(v):
    return "".join(w[0] for w in names()[v].split()[:2]).upper()


def color(v):
    return VENDOR_COLOR[short(v)]


def vendor_css():
    return "".join(f'.st-key-box_{v}::before{{content:"{initials(v)}";background:{color(v)}}}' for v in db.VENDORS)


def brand():
    st.html('<div class="brand"><div class="brand-mark">KQ</div><div><b>Kill the Quote</b><small>Spreadsheet</small></div></div>')


def journey_state():
    """How far the RFP has come, read from the facts. Returns percent and what comes next."""
    r = db.rfx()
    if r["status"] != "sent":
        return (10, "Send the RFP next") if r["draft"] else (0, "Start with the RFP co-pilot")
    boxes = db.mailboxes()
    n = len(boxes)
    replied = sum(1 for b in boxes if attributes.replied(b["vendor"]))
    ready = sum(1 for b in boxes if b["stage"] in ("Ready for evaluation", "Ready, with gaps"))
    checked = any(db.doc_checks(b["vendor"]) for b in boxes)
    pct = 20 + 30 * replied / n + 20 * ready / n + (15 if checked else 0) + (15 if st.session_state.get("run_template") else 0)
    if replied < n:
        return pct, f"{replied} of {n} replies in"
    if ready < n:
        return pct, f"{ready} of {n} vendors complete"
    return pct, "Evidence checked. Vendor choice next"


def journey():
    pct, text = journey_state()
    st.html(f'<div class="journey"><div class="top"><span>RFP JOURNEY</span><b>{pct:.0f}%</b></div><div class="track"><i style="width:{pct:.0f}%"></i></div><small>{esc(text)}</small></div>')


def header(title, question):
    st.html(f'<div class="page-header"><h1>{esc(title)}</h1><p>{esc(question)}</p></div>')


def badge(text, tone=None):
    return f'<span class="badge {tone or tone_of(text)}"><i></i>{esc(text)}</span>'


def tone_of(text):
    return {GREEN: "good", AMBER: "warn", RED: "bad"}.get(STATUS.get(str(text).strip().lower()), "neutral")


def card(key, **kw):
    return st.container(key=f"card_{key}", **kw)


def title(eyebrow, heading_text, right=""):
    st.html(f'<div class="card-title"><div><span class="eyebrow">{esc(eyebrow)}</span><h2>{esc(heading_text)}</h2></div><div>{right}</div></div>')


def insight(strong, text="", tone=""):
    st.html(f'<div class="insight {tone}"><div><b>{esc(strong)}</b>{esc(text)}</div></div>')


def bias(text):
    st.html(f'<div class="bias"><strong>Known bias.</strong> {esc(text)}</div>')


def note(text):
    st.html(f'<div class="source">{esc(text)}</div>')


def table(headers, rows):
    """A read-only table. Cells are HTML, so they can hold badges and vendor dots."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.html(f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')


def vendor_cell(v, full=False):
    return f'<span class="vcell"><i style="background:{color(v)}"></i>{esc(names()[v] if full else short(v))}</span>'


def next_step(label, page):
    with st.container(key=f"next_{page.split('/')[-1].split('.')[0]}"):
        a, b = st.columns([4, 1], vertical_alignment="center")
        a.html(f'<span class="eyebrow">NEXT STEP</span><strong>{esc(label)}</strong>')
        b.page_link(page, label="Continue", icon=":material/arrow_forward:")
