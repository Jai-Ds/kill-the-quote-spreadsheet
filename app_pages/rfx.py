import streamlit as st

from proto import data, db, graph, runtime, ui

ui.header("RFP co-pilot", "What are we asking vendors for?")
r = db.rfx()
sent = r["status"] == "sent"
if sent:
    ui.insight("RFP sent to 5 vendors.", " Agents are watching all five mailboxes. Nothing else is needed from you yet.")
chat, draft = st.columns([0.9, 1.1])

with chat, ui.card("chat"):
    ui.title("RFP builder", "Talk through the requirement", ui.badge("Sources connected", "good"))
    box = st.container(height=470, border=False)
    with box:
        if not r["chat"]:
            st.chat_message("assistant").write("Tell me what you're sourcing and what worries you about supply.")
        for m in r["chat"]:
            st.chat_message(m["role"]).write(m["content"])
    msg = st.chat_input("e.g. We're launching the hair serum in February. Cold room space is tight and I worry about peptides.", disabled=sent)
    if msg:
        history = r["chat"] + [{"role": "user", "content": msg}]
        with box:
            st.chat_message("user").write(msg)
            with st.chat_message("assistant"), st.spinner("Working"):
                try:
                    reply = graph.copilot(history, r["draft"])
                    db.save_rfx(chat=history + [{"role": "assistant", "content": reply}])
                    st.rerun()
                except Exception as e:
                    st.error(f"The agent call failed: {e}")

with draft, ui.card("draft"):
    d = db.rfx()["draft"]
    if not d:
        ui.title("Live draft", "Your RFP appears here", ui.badge("Empty", "neutral"))
        st.caption("The draft appears here as you talk.")
    else:
        ui.title("Live draft", d.get("title", "Draft RFP"), ui.badge("Sent", "good") if sent else ui.badge("Draft", "warn"))
        st.write(d.get("scope", ""))
        st.html('<div class="chips"><div><span>Launch</span><strong>1 Feb 2027</strong></div><div><span>First material</span><strong>20 Dec 2026</strong></div><div><span>Vendors</span><strong>5 invited</strong></div></div>')
        notes = {n["rm_code"]: n["note"] for n in d.get("line_notes") or []}
        t = data.sheet("RFx_Lines")
        rows = [f'<div class="item-row"><span>{x["RM code"][-3:]}</span><div><strong>{ui.esc(x["Material"])}</strong><small>{ui.esc(x["Spec strength"])}{" · " + ui.esc(notes[x["RM code"]]) if x["RM code"] in notes else ""}</small></div><b>{x["RFx quantity: net 6M need (kg)"]:,.0f} kg</b></div>' for _, x in t.iterrows()]
        with st.container(height=250, border=False):
            st.html("".join(rows))
        if d.get("questionnaire_focus"):
            st.html(f'<div class="focus"><strong>Questionnaire focus</strong><br>{ui.esc("; ".join(d["questionnaire_focus"]))}</div>')
        if d.get("terms"):
            with st.expander("Terms"):
                st.markdown("\n".join(f"- {x}" for x in d["terms"]))
        ui.note("Quantities come from the forecast and bill of materials. The agent can't invent them.")
        if not sent and st.button("Send to 5 vendors", type="primary", icon=":material/send:", width="stretch"):
            runtime.send_rfx()
            st.rerun()

ui.glossary()
if sent:
    ui.next_step("Watch replies arrive in the vendor inbox", "app_pages/inbox.py")
