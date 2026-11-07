import streamlit as st

from proto import attributes as A
from proto import data, db, ui

ui.header("Attributes management", "What matters for each item?")
bank = A.question_bank()
latest = ui.latest_rows()
main, side = st.columns([2, 1])

with side, ui.card("templates"):
    ui.title("Templates", "Priority starting point")
    name = st.radio("Template", list(latest), label_visibility="collapsed")
    cur = latest[name]
    with st.form(f"f{name}{cur['version']}", border=False):
        new = {}
        for a in A.ATTRIBUTES:
            new[a["key"]] = st.segmented_control(a["name"], ["High", "Medium", "Low"], default=A.LEVEL[int(cur["weights"][a["key"]])], key=f"{name}{a['key']}{cur['version']}")
        if st.form_submit_button("Save changes", type="primary", width="stretch"):
            w = {k: {"High": 3, "Medium": 2, "Low": 1}.get(v, 1) for k, v in new.items()}
            if w != cur["weights"]:
                v = db.save_template(name, w, "Changed in Attributes management")
                db.event(None, "Buyer", "buyer", f"Saved {name} version {v}.")
                st.rerun()
    with st.expander("Create new template", icon=":material/add:"):
        with st.form("new_template", border=False, clear_on_submit=True):
            new_name = st.text_input("Template name", placeholder="Launch critical")
            lv = {}
            for a in A.ATTRIBUTES:
                lv[a["key"]] = st.segmented_control(a["name"], ["High", "Medium", "Low"], default="Medium", key=f"new{a['key']}")
            if st.form_submit_button("Create template"):
                nm = new_name.strip()
                if not nm:
                    st.error("Enter a template name.")
                elif nm in latest:
                    st.error("That name is already in use.")
                else:
                    db.save_template(nm, {k: {"High": 3, "Medium": 2, "Low": 1}.get(x, 2) for k, x in lv.items()}, "Created by the buyer")
                    db.event(None, "Buyer", "buyer", f"Created template {nm}.")
                    st.rerun()

with main:
    with ui.card("model"):
        ui.title("Decision model", "Six attributes, grounded in facts", f'<span class="muted">Priorities shown for {ui.esc(name)}</span>')
        TONE = {"High": "blue", "Medium": "neutral", "Low": "neutral"}
        rows = []
        for a in A.ATTRIBUTES:
            lvl = A.LEVEL[int(cur["weights"][a["key"]])]
            rows.append([f"<strong>{ui.esc(a['name'])}</strong>", ui.esc(a["why"]), ui.esc(a["measure"]), ", ".join(a["questions"]), ui.badge(lvl, TONE[lvl])])
        ui.table(["Attribute", "Why it is measured", "How it is measured", "Questions", "Priority"], rows)
    with st.expander("The 10 questions vendors receive", icon=":material/quiz:"):
        ui.table(["ID", "Question", "Attribute", "Knockout"], [[r["ID"], ui.esc(r["Question"]), ui.esc(r["Attribute"]), ui.badge("Yes", "bad") if r["Knockout"] else "No"] for _, r in bank.iterrows()])
    with st.expander("How the evaluation score is calculated", icon=":material/calculate:"):
        st.markdown("""
The score is calculated in code from the quotes, our records and the questionnaire, so the same inputs always give the same result.

- **Each attribute is scored 0-10.** The best bid on Cost scores 10, and each 1% above it loses 0.5. Inventory works the same way on holding cost, at 0.15 per 1%. Delivery is 70% OTIF and 30% lead-time steadiness. Quality comes from our defect records. Supply risk and Compliance come from rated answers.
- **The template weights them:** High counts 5, Medium 2, Low 1. An attribute with no data is left out, not scored as zero.
- **Total = 70% weighted attributes + 30% evidence.** Evidence is the level from Claims vs evidence for that vendor and item: Good counts 100, Medium 60, Low 20.
- **Knockouts:** a failed knockout, such as an expired COA, removes a vendor from the ranking whatever its score.""")

with ui.card("tags"):
    tags = db.item_tags()
    rm = data.rm_table()
    ui.title("Item tags", "Apply priorities by ingredient", f'<span class="muted">{len(rm)} items · {len(latest)} templates</span>')
    if st.session_state.get("tag_note"):
        ui.insight(st.session_state["tag_note"])
    cols = st.columns(2)
    for i, (_, r) in enumerate(rm.iterrows()):
        code = r["RM code"]
        old = tags[code]
        with cols[i % 2]:
            a, b = st.columns([1.4, 1], vertical_alignment="center")
            a.html(f'<div class="tag"><span>{code[-3:]}</span><div><strong>{ui.esc(r["Material"].split(" (")[0])}</strong><small>{ui.esc(r["Spec strength"])}</small></div></div>')
            new = b.selectbox(r["Material"], list(latest), index=list(latest).index(old), key=f"tag{code}{old}", label_visibility="collapsed")
        if new != old:
            w = ui.latest()
            q = ui.quotes()
            was = A.best_vendor(q, code, old, w)[0] if len(q) else None
            now = A.best_vendor(q, code, new, w)[0] if len(q) else None
            db.set_item_tag(code, new)
            n = ui.names()
            lab = lambda x: n[x].split()[0] if x else "no cleared vendor"   # noqa: E731
            msg = f"{code[-3:]} {r['Material']} moved from {old} to {new}. "
            msg += f"Best vendor changes from {lab(was)} to {lab(now)}." if was != now else f"Best vendor stays {lab(now)}."
            st.session_state.tag_note = msg
            db.event(None, "Buyer", "buyer", msg)
            st.rerun()

ui.bias("New vendors have no history with us, so their OTIF and defect claims can't be checked and their evidence level is usually Low. This favours existing vendors. A fairer treatment for new vendors is on the roadmap.")
ui.next_step("Check claims against evidence", "app_pages/evidence.py")
