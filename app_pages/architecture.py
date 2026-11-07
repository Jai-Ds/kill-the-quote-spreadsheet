from pathlib import Path

import streamlit as st

from proto import ui

ui.header("Architecture", "How does it work?")
NODES = [("Mailbox event", ""), ("Intake Router", ""), ("Document Extractor", ""), ("Extraction Reviewer", ""), ("Questionnaire Analyst", ""), ("Evidence Evaluator", ""), ("Rule engine", "code"),
         ("Vendor Liaison", ""), ("Confidentiality check", "code"), ("Human approval", "human"), ("Send email", "code")]
with ui.card("flow"):
    ui.title("System flow", "From vendor message to approved response", ui.badge("Human always decides", "good"))
    st.html('<div class="flow">' + "".join(f'<div class="node {k}"><span>{i:02d}</span>{ui.esc(n)}</div>' for i, (n, k) in enumerate(NODES, 1)) + "</div>")
    ui.note("Green steps are code, not AI. The reviewer can send work back to the extractor once. The Router skips extraction for a vendor question, a steering attempt or an auto-reply.")

NOTES = [("Ingestion", "Read, then verify", "The Intake Router classifies each message. The Document Extractor reads Excel, PDF, Word, photos and email text. An independent Reviewer checks the record against the source before it is used."),
         ("Decisioning", "Facts before scores", "The Questionnaire Analyst maps answers to the 10 questions. The Evidence Evaluator tests 10 conditions per document. Code applies knockouts, evidence levels and weighted scores."),
         ("Outbound safety", "Nothing sends itself", "The Vendor Liaison drafts one consolidated reply. A confidentiality check blocks company data, then the buyer edits, approves or rejects every message.")]
for col, (eye, head, text) in zip(st.columns(3), NOTES):
    col.html(f'<div class="note-card"><span class="eyebrow">{eye}</span><h3>{head}</h3><p>{text}</p></div>')

st.html(f'<div class="callout">{ui.badge("Journey complete", "good")}<h3>A defensible choice, with every fact and proof attached.</h3><p>Agents organise the work. Rules keep it consistent. The category manager owns the decision.</p></div>')

doc = Path(__file__).resolve().parents[1] / "AGENT_ARCHITECTURE.md"
if doc.exists():
    text = doc.read_text(encoding="utf-8")
    st.download_button("Export architecture note", text, "AGENT_ARCHITECTURE.md", icon=":material/download:")
    with st.expander("Full technical write-up", icon=":material/description:"):
        st.markdown(text)
