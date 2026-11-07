import pandas as pd
import streamlit as st

from proto import agentkit, db, graph, ui

ui.header("Agent trace", "What did the AI do?")
runs = pd.DataFrame(db.q("SELECT * FROM runs ORDER BY id DESC"))
JOBS = {"RFx Co-pilot": "Builds the RFP with the buyer", "Intake Router": "Classifies each message, and spots steering attempts and requests for company data", "Document Extractor": "Turns any format into structured records",
        "Extraction Reviewer": "Rechecks the record against the source", "Questionnaire Analyst": "Maps what the vendor said onto the 10 questions", "Evidence Evaluator": "Assesses each document against 10 conditions, which decides each claim's Pass or Fail",
        "Vendor Liaison": "Decides the next move and drafts replies, without releasing company data", "Analyst": "Answers buyer questions with charts, cards and tables"}
done = runs["agent"].value_counts().to_dict() if len(runs) else {}
roster = [[f"<strong>{a.name}</strong>", ui.esc(JOBS[a.name]), a.model.replace("claude-", "").replace("-5-5", "").title(), f"<strong>{done.get(a.name, 0)}</strong>"] for a in graph.AGENTS]

if runs.empty:
    with ui.card("roster"):
        ui.title("Agent roster", "Eight agents, narrow jobs")
        ui.table(["Agent", "Job", "Default model", "Runs"], roster)
    st.info("No agent has run yet.", icon=":material/hourglass_empty:")
    st.stop()

runs = runs.fillna({"replayed": 0, "input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_write": 0, "seconds": 0, "turns": 0})
runs["model"] = runs["model"].fillna("claude-opus-5-5")
runs["cost_usd"] = runs.apply(lambda r: agentkit.cost_usd(r["model"], r["input_tokens"], r["output_tokens"], r["cache_read"], r["cache_write"]), axis=1)
runs["cost_inr"] = runs["cost_usd"] * agentkit.inr_rate()
runs["Model"] = runs["model"].str.replace("claude-", "").str.replace("-5-5", "").str.title()
prompt = runs["input_tokens"].sum() + runs["cache_read"].sum() + runs["cache_write"].sum()
repaired = db.q("SELECT COUNT(*) n FROM steps WHERE is_error=1")[0]["n"]
ui.cards([{"label": "Agent runs", "value": len(runs), "note": "Since the last reset", "tone": "blue"},
          {"label": "Cache hit rate", "value": f"{runs['cache_read'].sum() / prompt:.0%}" if prompt else "-", "note": "Prompt tokens read from cache", "tone": "good"},
          {"label": "Estimated cost", "value": f"Rs {runs['cost_inr'].sum():.2f}", "note": "For the runs on this page", "tone": "warn"},
          {"label": "Tool errors repaired", "value": repaired, "note": "Rejected by validation, then fixed", "tone": "neutral"}])

left, right = st.columns([1.15, 1])
with left, ui.card("roster"):
    ui.title("Agent roster", "Eight agents, narrow jobs")
    ui.table(["Agent", "Job", "Default model", "Runs"], roster)
    with st.expander("Usage by agent"):
        g = runs.groupby(["agent", "Model"]).agg(Runs=("id", "count"), Replayed_calls=("replayed", "sum"), Avg_seconds=("seconds", "mean"), Output_tokens=("output_tokens", "sum"), Cache_read=("cache_read", "sum"), Cost_Rs=("cost_inr", "sum")).reset_index()
        st.dataframe(g.round(3), hide_index=True, height="content", alt="Agent summary")

with right, ui.card("runs"):
    ui.title("Run inspector", "Open a tool call")
    runs["label"] = runs.apply(lambda r: f"#{r['id']} {r['agent']} {ui.short(r['vendor']) if isinstance(r['vendor'], str) else ''} on {r['Model']} ({r['seconds']:.0f}s, {int(r['turns'])} turns, {r['status']})", axis=1)
    pick = st.selectbox("Run", runs["label"].tolist(), label_visibility="collapsed")
    rid = int(runs[runs["label"] == pick]["id"].iloc[0])
    for n, s in enumerate(db.q("SELECT * FROM steps WHERE run_id=? ORDER BY id", rid), 1):
        if s["kind"] == "text":
            st.chat_message("assistant", avatar=":material/smart_toy:").write(s["output"])
        else:
            with st.expander(f"{n}. {'Rejected: ' if s['is_error'] else ''}{s['name']} ({s['ms']} ms)", icon=":material/error:" if s["is_error"] else ":material/build:"):
                st.markdown("Input")
                st.code(s["input"], language="json", wrap_lines=True)
                st.markdown("Result")
                st.code(s["output"], language=None, wrap_lines=True)

ui.next_step("See the system architecture", "app_pages/architecture.py")
