import streamlit as st

from proto import attributes as A
from proto import db, tools, ui

ui.header("Vendor status", "Where does each vendor stand?")

TONE = {"red": "warn", "orange": "bad", "green": "good", "blue": "blue", "violet": "blue", "gray": "neutral"}
boxes = db.mailboxes()
rows, waits = [], {}
for b in boxes:
    v = b["vendor"]
    got = A.replied(v)
    s = A.vendor_summary(v)
    sup, _ = A.support(v)
    label, color = A.inbox_state(v, b["busy"], b["stage"])
    w = A.waiting_for(v, tools._issue_view(v)) if got else "First reply"
    waits[v] = w
    rows.append([ui.vendor_cell(v, True), ui.badge(label, TONE.get(color, "neutral")), f"<strong>{len(sup)} of 10</strong>" if got else "-", f"{s['answered_pct']:.0%}" if got else "-", f"{s['backed_pct']:.0%}" if got else "-", ui.esc(w)])

held = [v for v, w in waits.items() if w != "Nothing"]
if held:
    worst = max(held, key=lambda v: len(waits[v].split(",")))
    ui.insight(f"{ui.short(worst)} has the most outstanding.", f" Waiting for: {waits[worst]}. {len(held)} of {len(boxes)} vendors still have something open.", "warn")
else:
    ui.insight("Nothing is outstanding.", " Every vendor is ready for evaluation.")

with ui.card("overview"):
    ui.title("Reply progress", "Vendor overview", '<span class="muted">Every vendor received all 10 lines</span>')
    ui.table(["Vendor", "Status", "Lines supported", "Questions answered", "Backed by evidence", "Waiting for"], rows)

CELL = {"answered": ("A", "good", "Answered"), "partial": ("P", "warn", "Partly"), "refused": ("R", "bad", "Refused"), "not_answered": ("N", "neutral", "Not answered")}
with ui.card("coverage"):
    ui.title("Question coverage", "Who answered what", " ".join(ui.badge(t, k) for t, k in (("Answered", "good"), ("Partly", "warn"), ("Refused", "bad"), ("Not answered", "neutral"))))
    done = [b["vendor"] for b in boxes if A.replied(b["vendor"])]
    if not done:
        st.caption("No replies yet.")
    else:
        bank = A.question_bank()
        out = "<span></span>" + "".join(f'<b title="{ui.esc(r["Question"])}">{r["ID"]}</b>' for _, r in bank.iterrows())
        for v in done:
            out += f"<div>{ui.vendor_cell(v)}</div>"
            for _, r in A.vendor_questions(v).iterrows():
                if r["applicable"]:
                    c, tone, word = CELL[r["status"]]
                    out += f'<div class="cell {tone}" title="{ui.esc(r["topic"])}: {word}">{c}</div>'
                else:
                    out += f'<div class="cell na" title="{ui.esc(r["topic"])}: does not apply">-</div>'
        st.html(f'<div class="heat-wrap"><div class="heat">{out}</div></div>')
        ui.note("Hover over a square to see the question. Open a vendor in the inbox to read what they said.")

ui.next_step("Ask the analyst about the quotes", "app_pages/analysis.py")
