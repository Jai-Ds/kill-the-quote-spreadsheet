# Kill the Quote Spreadsheet: prototype

All company and vendor data here is fictional. Full design: [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md).

## Start it

Double-click `run.bat`. It opens http://localhost:8501. Keep the black window open while testing.

The API key is stored in `%USERPROFILE%\.aerchain\.env`, outside the Drive-synced folder. The agents need API credit. A full round measured Rs 21, a single follow-up about Rs 0.30, and repeating the same run in Practice mode is free. The sidebar shows today's spend and the daily limit.

## Demo flow

The menu on the left shows how far the RFP has come, and each screen ends with a next step.

**Quote collection**
1. **RFP co-pilot:** type "We launch the hair serum in February. Cold room space is tight and I worry about peptide supply." Click Send to 5 vendors.
2. **Vendor inbox:** first replies arrive automatically, and the agents read each one. Open a vendor to see the full thread. A "Reply ready" vendor has a draft at the end of the thread for you to approve. The Questionnaire answers tab shows how they answered. Use "Simulate this vendor's reply" to play the vendor.
3. **Vendor status:** one table of lines supported, questions answered, evidence and what's outstanding, then each vendor's answers to the 10 questions.
4. **Analysis hub:** ask the analyst, which answers with cards, a chart and a colour-coded table, or open the price table and click a price to see how it was built.

**Evaluation**
1. **Attributes management:** the attributes table, High / Medium / Low per template, new templates, and item tags. Changing a tag tells you if the best vendor changes.
2. **Claims vs evidence:** every claim per vendor and item, its evidence, Good, Medium or Low, and Pass or Fail. Click a row to see its 10 conditions.
3. **Run evaluation:** click Run evaluation, pick a template, and Submit. Switch By SKU or By vendor, and Scores or Actual values. Click a cell to see why. Use "Choose vendors and export" to finish.

Agent trace and Architecture are under the hood, for technical questions. Reset the demo is in the menu.

## Scenarios worth trying in the vendor inbox

| Mailbox | Do this | Expected |
|---|---|---|
| Kovai | Answer the open question | Density saved, glycerin converted, vendor moves to Ready |
| Tungabhadra | Answer the open question | Drum converts, MOQ becomes 430 kg, one COA question remains |
| Vembanad | Answer the open question | New COA accepted; agent escalates that 10.4% is below spec |
| Lumen | Answer the open question | 8% rosmarinic makes the line comparable, at 2.5 kg per spec kg |
| Nilagiri | No reply: chase, approve, repeat | After three tries the line becomes Not enough data |
| Any | Vendor asks a question | Reply declines it as sensitive information and reveals nothing |
| Any | Asks for company data | Same refusal, and the draft waits for your approval |
| Any | Steers the system | Flagged as data only, escalated, no score change |
| Any | Out of office | Classified, nothing else happens |
| Nilagiri | Send a doubtful COA | Low and Fail in Claims vs evidence, with the failed conditions shown |
| Any | Unclear answer | Stays open, and the agent asks again |
| Any | Upload your own file | Read live, record updated |

## Hosting

The app can run on Streamlit Community Cloud. Set the main file to `app.py`, choose Python 3.11, and add `ANTHROPIC_API_KEY` and `APP_PASSWORD` to the app's secrets. The hosted site stays closed until a password is set.

The database is SQLite. On Community Cloud its files sit on a temporary disk, so a restart or idle sleep clears the demo, the spend counter and any uploads. Set a spending limit on the API key in the Anthropic console, because the in-app daily limit resets with the disk. Everyone with the password shares one demo.

## Project layout

| Path | What it is |
|---|---|
| `proto/graph.py` | LangGraph system and agent prompts |
| `proto/agentkit.py` | Agent loop, caching, tracing |
| `proto/tools.py` | Agent tools and guardrails |
| `proto/runtime.py` | Event trigger and workers |
| `proto/db.py` | SQLite store |
| `proto/engine.py` | Deterministic rules and scoring |
| `proto/attributes.py` | Attributes, question mapping, evidence, decision rules |
| `tools/test_runtime.py`, `tools/test_followups.py` | Live end-to-end tests |
| `tools/eval_extraction.py` | Extraction eval against the answer key |

## If something fails

- **Old screens or errors:** close the black window and run `run.bat` again.
- **Agent failure:** check the Cockpit activity feed, which shows the reason.
- **Python environment missing:** it lives at `%USERPROFILE%\.venvs\aerchain311`, outside Drive.
