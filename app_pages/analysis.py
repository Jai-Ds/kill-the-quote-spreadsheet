import pandas as pd
import streamlit as st

from proto import data, graph, ui

ui.header("Analysis hub", "What does the data say?")
ui.need_replies()
q, v = ui.scored()
names = ui.names()
short = {k: n.split()[0] for k, n in names.items()}
view = st.segmented_control("View", ["Ask the analyst", "Price table"], default="Ask the analyst", label_visibility="collapsed")

if view == "Price table":
    rate, d = data.fx_rate()

    def cell(r):
        if r.get("not_quoted") == True:   # noqa: E712
            return "Declined"
        if r.get("not_enough_data") == True:   # noqa: E712
            return "Not enough data"
        return f"Rs {r['cost_inr_per_spec_kg']:,.0f}" if r["comparable"] else "Not comparable yet"

    with ui.card("prices"):
        ok = int((q["comparable"] == True).sum())   # noqa: E712
        ui.title("Landed rupees per spec kg", "Like-for-like price comparison", ui.badge(f"{ok} comparable quotes", "good"))
        ui.note(f"After discount, duty, freight, FX (Rs {rate}, {d}) and strength. Click a price to see how it was built.")
        grid = q.assign(c=q.apply(cell, axis=1)).pivot(index=["rm_code", "material"], columns="vendor", values="c").fillna("").reset_index().rename(columns={**short, "rm_code": "SKU", "material": "Material"})
        ev = st.dataframe(grid, hide_index=True, height="content", on_select="rerun", selection_mode="single-cell", key="price", alt="Price comparison")
        cells = ev.selection.cells
        if cells:
            i, col = cells[0]
            code = grid.iloc[i]["SKU"]
            vid = next((k for k, s in short.items() if s == col), None)
            r = q[(q["vendor"] == vid) & (q["rm_code"] == code)]
            if len(r):
                r = r.iloc[0]
                with st.container(border=True):
                    st.markdown(f"**{col}: {r['material']}**")
                    if r.get("source_quote") == r.get("source_quote") and r.get("source_quote"):
                        st.caption(f"{r['source_file']}: \"{r['source_quote']}\"")
                    for t in r["trail"] or ["No conversion was possible yet."]:
                        st.write(t)
                    for i2 in r["issues"]:
                        if i2["action"] == "Ask":
                            st.warning(i2["text"])
    ui.glossary()
    ui.next_step("Set priorities for each item", "app_pages/manage.py")
    st.stop()

if "analyst_view" not in st.session_state:
    st.session_state.analyst_view = []
SAMPLES = ["Compare vendors on OTIF and defect rate", "Which lines have no safe option right now?", "Show evidence levels by vendor", "What if we split it, cheapest per line, among cleared vendors?"]
ask = None
side, main = st.columns([1, 2.6])

with side, ui.card("ask"):
    ui.title("Suggested questions", "What do you want to know?")
    for i, t in enumerate(SAMPLES):
        if st.button(t, key=f"sample{i}", width="stretch"):
            ask = t
    with st.form("ask_form", clear_on_submit=True, border=False):
        typed = st.text_area("Your question", placeholder="Ask about the quotes", height=90, label_visibility="collapsed")
        if st.form_submit_button("Ask", type="primary", icon=":material/send:", width="stretch") and typed.strip():
            ask = typed.strip()


def show(m, i):
    with ui.card(f"ans{i}"):
        st.html(f'<span class="muted">{ui.esc(m["q"])}</span>')
        ui.title("Analyst answer", m["answer"])
        ui.cards(m.get("cards"))
        r = m.get("result")
        if isinstance(r, pd.DataFrame) and len(r):
            t = ui.readable(r)
            if m.get("chart"):
                try:
                    ui.chart(t, m["chart"])
                except Exception as e:   # a chart that can't be drawn must not lose the answer
                    st.caption(f"The chart couldn't be drawn: {str(e)[:120]}")
            st.dataframe(ui.colored(t), hide_index=True, height="content", alt="Analysis result")
            st.download_button("Export CSV", r.to_csv(index=False), "analysis.csv", key=f"dl{i}", icon=":material/download:")
        if m.get("code"):
            with st.expander("Code the agent ran", icon=":material/code:"):
                st.code(m["code"], language="python")


with main:
    if ask:
        with st.spinner("Analyst is working"):
            try:
                hist = [{"q": m["q"], "a": m["answer"]} for m in st.session_state.analyst_view]
                out = graph.analyst(ask, q, v, hist)
                out["q"] = ask
                st.session_state.analyst_view.append(out)
            except Exception as e:
                st.error(f"The analyst couldn't answer: {str(e)[:200]}")
    if not st.session_state.analyst_view:
        ui.insight("Ask a question to get a chart, key figures and a table.", " Every number comes from analysis of the real quotes.")
    for i, m in reversed(list(enumerate(st.session_state.analyst_view))):
        show(m, i)

ui.next_step("Set priorities for each item", "app_pages/manage.py")
