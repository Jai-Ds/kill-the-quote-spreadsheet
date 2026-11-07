from pathlib import Path

import streamlit as st

from proto import ui

ui.header("Architecture", "How does it work?")
ROWS = [
    ("plain", "Mailbox event", "Message or no reply", "", "Background worker", "One run per vendor"),
    ("agent", "Intake Router", "Classifies the message", "get_thread, submit_triage", "Fail-safe routing", "Attachments always read"),
    ("agent", "Document Extractor", "Reads any format", "read_attachment, save_quote_line, save_coa", "Source check", "Rejects invented quotes"),
    ("agent", "Extraction Reviewer", "Rechecks the record", "read_attachment, submit_review", "One retry only", "Then goes to the buyer"),
    ("agent", "Questionnaire Analyst", "Maps to 10 questions", "get_recorded_answers, save_question_answers", "Answer protection", "Never downgrades answers"),
    ("agent", "Evidence Evaluator", "Answers 10 conditions", "get_documents_to_check, record_document_check", "Fact-check rules", "Gives Good, Medium, Low"),
    ("code", "Rule engine", "No AI at this step", "No tools: pure code", "Normalise and check", "Costs, knockouts, flags"),
    ("agent", "Vendor Liaison", "Chooses the next move", "get_open_issues, draft_vendor_email", "Confidentiality check", "Blocks company data"),
    ("human", "Buyer approval", "Approve, edit or reject", "Graph pauses here", "Send email", "Only after approval"),
]


def node(kind, head, sub):
    return f'<div class="a-node {kind}"><b>{ui.esc(head)}</b><small>{ui.esc(sub)}</small></div>'


with ui.card("flow"):
    ui.title("System flow", "How agents, tools and code work together", ui.badge("Human always decides", "good"))
    body = '<div class="arch-row arch-head"><span>Stage</span><span>Tools it can use</span><span>Code that controls it</span></div>'
    for i, (kind, head, sub, tool, rule, why) in enumerate(ROWS):
        tools = f'<div class="a-node tool"><i>Tools</i>{ui.esc(tool)}</div>' if tool else '<div class="a-node tool empty"></div>'
        body += f'<div class="arch-row">{node(kind, head, sub)}{tools}{node("code", rule, why)}</div>'
        if i < len(ROWS) - 1:
            body += '<div class="arch-down">↓</div>'
    st.html(f'<div class="arch">{body}</div>')
    st.html('<div class="arch-key"><span class="k agent">AI agent</span><span class="k code">Code</span><span class="k human">Person</span><span class="k tool">Tools</span></div>')
    ui.note("The Router sends vendor questions and steering attempts straight to the Liaison, and auto-replies end there. A failed review returns to the Extractor once, and a second failure goes to the buyer. The Evidence Evaluator runs only when a message has attachments. The tools shown are the main ones for each agent.")
    ui.note("RFP Co-pilot and Analyst aren't in this flow, because they work directly with the buyer.")

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
