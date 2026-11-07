import streamlit as st

from proto import attributes as A
from proto import db, engine, factcheck as F
from proto import ui

ui.header("Claims vs evidence", "Can I trust what vendors claim?")
ui.need_replies()
names = ui.names()
p = engine.EVIDENCE_POINTS
ui.insight("Evidence decides 30% of the total.", f" Good counts {p['Good']}, Medium {p['Medium']}, Low {p['Low']}. No evidence is always Low and always fails.")

with st.expander("How ratings work", icon=":material/checklist:"):
    st.markdown("""
There are no scores. The Evidence Evaluator agent answers 10 fixed yes-or-no conditions about each document, and code rechecks dates and strength. OTIF and defect claims are checked by code against our own POs, receipts and inspections.

| Conditions met | Evidence | Result |
|---|---|---|
| 8 to 10 | Good | Pass |
| 6 or 7 | Medium | Pass |
| 5 or fewer | Low | Fail |

**Gates:** if a claim misses Supports the claim, Dates make sense or Looks genuine, it is Low whatever the count.

**For each item:** Good if 80% or more of its own claims (specification, OTIF, defect rate) pass, Medium if 60% or more, otherwise Low. Vendor-wide claims, such as certificates, count only in the vendor's overall evidence.

A pass means nothing looks wrong. The agent can't confirm a document with its issuer.""")
    ui.table(["Condition", "Met when"], [[f"<strong>{ui.esc(n)}</strong>", ui.esc(d)] for _, n, d in F.CONDITIONS])

replied = [v for v in db.VENDORS if A.replied(v)]
if "ev_vendor" not in st.session_state or st.session_state.ev_vendor not in replied:
    st.session_state.ev_vendor = replied[0]
for col, v in zip(st.columns(len(replied)), replied):
    s = F.summary(v)
    if col.button(f"**{ui.short(v)}**  \n{s['claims']} claims · {s['good']} Good · {s['low']} Low", key=f"ev{v}", width="stretch", type="primary" if st.session_state.ev_vendor == v else "secondary"):
        st.session_state.ev_vendor = v
        st.rerun()


@st.dialog("Claim detail", width="large")
def detail(r):
    good = r["Result"] == "Pass"
    st.html(f'<span class="eyebrow">{ui.esc(r["Item"])}</span><strong>{ui.esc(r["Claim type"])}: {ui.esc(r["Claim"])}</strong>')
    st.html(f'<div class="{"pass-box" if good else "fail-box"}">{ui.badge(r["Evidence"] + " · " + r["Result"], "good" if good else "bad")}<br><strong>{r["Conditions met"]} of 10 conditions met.</strong> {ui.esc(r["How it was checked"])}</div>')
    rows = ""
    for x in F.KEYS:
        c = r["checks"][x]
        rows += f'<div class="cond"><span class="tick {"good" if c["met"] else "bad"}">{"✓" if c["met"] else "✕"}</span><div><strong>{ui.esc(F.NAME[x])}</strong><small>{ui.esc(c["note"])}</small></div>{ui.badge("Met" if c["met"] else "Not met", "good" if c["met"] else "bad")}<em>{ui.esc(c["by"])}</em></div>'
    st.html(f'<span class="eyebrow">10 evidence conditions</span>{rows}')


v = st.session_state.ev_vendor
with ui.card("claims"):
    s = F.summary(v)
    ui.title(names[v], "Claims and supporting proof", ui.badge(f"Overall evidence: {s['level']}", {"Good": "good", "Medium": "warn", "Low": "bad"}[s["level"]]))
    c = F.claims(v)
    a, b = st.columns([3, 1], vertical_alignment="center")
    item = a.selectbox("Item", ["All items"] + list(dict.fromkeys(c["Item"])), label_visibility="collapsed")
    failed = b.toggle("Failed only")
    if item != "All items":
        c = c[c["Item"] == item]
    if failed:
        c = c[c["Result"] == "Fail"]
    c = c.reset_index(drop=True)
    view = c[["Item", "Claim type", "Claim", "Evidence provided", "How it was checked", "Conditions met", "Evidence", "Result"]].assign(**{"Conditions met": c["Conditions met"].map(lambda n: f"{n} of 10")})
    key = f"claims{v}{item}{failed}"
    ev = st.dataframe(ui.colored(view, ["Evidence", "Result"]), hide_index=True, height="content", on_select="rerun", selection_mode="single-row", key=key, alt="Claims",
                      column_config={"Item": st.column_config.TextColumn(width="small"), "Claim": st.column_config.TextColumn(width="small"), "How it was checked": st.column_config.TextColumn(width="medium"), "Conditions met": st.column_config.TextColumn("Met", width="small")})
    rows = ev.selection.rows
    st.caption("Click a row to see its 10 conditions.")
    pick = (key, rows[0]) if rows else None
    if pick and pick != st.session_state.get("claim_open"):
        st.session_state.claim_open = pick
        detail(c.iloc[rows[0]])
    elif not pick:
        st.session_state.pop("claim_open", None)

ui.bias("New vendors have no history with us, so their delivery and defect claims can't be checked and their evidence is usually Low. This favours existing vendors. A fairer treatment is on the roadmap.")
ui.next_step("Run the vendor evaluation", "app_pages/evaluation.py")
