# Figma Make brief: Kill the Quote Spreadsheet

Paste everything below into Figma Make. All company and vendor data is fictional.

---

## Build this

Design a clickable React prototype of a procurement web app called **Kill the Quote Spreadsheet**. Use mock data with no backend. Make it a desktop-first B2B tool: calm, clean and easy to scan, never a wall of data. Keep every screen and action listed here, but improve the layout, hierarchy and navigation.

## User and goal

**User:** a category manager at Kesavi Personal Care, an Indian hair care manufacturer. They are sourcing 10 ingredients for a new hair growth serum, launching 1 February 2027. First material is needed by 20 December 2026.

**Today:** vendors reply in Excel, PDF, Word, phone photos and short emails, and the buyer retypes it all into one spreadsheet.

**Goal:** reach a defensible vendor choice for each ingredient, judged on OTIF, defect rate and inventory cost, not only on price. The buyer must always see why a recommendation was made and what proof backs it.

## Product principles

1. **Agents work in the background; the buyer decides.** Nothing goes to a vendor without approval.
2. **Each screen answers one question.** Lead with the answer, and put detail one click away.
3. **Show facts before scores.** A buyer should be able to see the real price, OTIF and certificate status.
4. **Always show the next action.** The buyer should know whose move it is.
5. **Evidence is never a number.** It is only Good, Medium or Low.

## Navigation

A collapsible left menu with three groups:

| Group | Screens |
|---|---|
| Quote collection | RFP co-pilot, Vendor inbox, Vendor status, Analysis hub |
| Evaluation | Attributes management, Claims vs evidence, Run evaluation |
| Under the hood | Agent trace, Architecture |

The menu also shows:
- whether agents are working or idle
- AI spend today against the daily limit, such as Rs 21 of Rs 50
- a Practice mode toggle
- a Reset the demo action

Show progress across the journey, from RFP sent to replies in, questions closed, evidence checked and vendors chosen. Add a clear "next step" prompt on each screen.

## End-to-end journey

1. The buyer talks to the RFP co-pilot and sends the RFP to 5 vendors.
2. Vendor replies arrive by themselves, and agents read them with no click.
3. Where something is unclear, the agent drafts one follow-up email. The buyer edits it, approves it or rejects it in the vendor thread.
4. The buyer checks who has replied, how they answered the questionnaire and what is still missing.
5. The buyer asks the analyst questions and gets charts, not paragraphs.
6. The buyer reviews priorities and item tags, then checks claims against evidence.
7. The buyer runs the evaluation, chooses a vendor per item and exports the decision.

## Screens

### 1. RFP co-pilot
**Question it answers:** what are we asking vendors for?

- **Left:** a chat with the agent. Example: "We launch the hair serum in February. Cold room space is tight and I worry about peptide supply."
- **Right:** a live draft that builds as they talk: title, scope, the 10 lines with spec and quantity, terms, and questionnaire focus areas.
- **Action:** Send to 5 vendors.
- **Also:** a "What the terms mean" glossary.
- **Insight:** quantities come from forecast and bill of materials, so nothing is invented.
- **Next:** Vendor inbox.

### 2. Vendor inbox
**Question it answers:** what has each vendor said, and what do I need to do?

- **Left:** 5 mailboxes, each with a status: Not sent, Waiting for vendor, Agents reading, Reply ready, Reply needed, Complete, Stopped replying.
- **Right, Conversation tab:** an email thread with attachments you can open (Excel, PDF, Word, photo).
- **Right, Questionnaire answers tab:**
  - 3 cards: Questions answered, Backed by evidence, Knockouts still open
  - a table of question, status, what they said, evidence and rating
- **Approval card, when a draft is waiting:** editable subject and message, with Approve and send, and Reject.
- **Escalation card, when the agent needs a decision:** the issue, with Acknowledge.
- **Demo-only panel:** "Simulate this vendor's reply", with a scenario picker: Revised price, Refuses to share records, Vendor asks a question, Asks for company data, Out of office, Steers the system, Unclear answer, Send a doubtful COA, Answer the open question. It also has a text box, file upload, Send as vendor, and No reply: chase. Keep this visually separate from the real product.
- **Insight:** the buyer sees what changed and what needs them, without reading every message.
- **Next:** Vendor status.

### 3. Vendor status
**Question it answers:** where does each vendor stand?

- **Table:** vendor, status, lines supported (such as 6 of 10), questions answered, backed by evidence, waiting for.
- **Heat grid:** vendors by the 10 questions, coloured Answered, Partly, Refused, Not answered, or N/A.
- **Insight:** who is holding things up, and on what.
- **Next:** Analysis hub or Evaluation.

### 4. Analysis hub
**Question it answers:** what does the data say?

Two views:
- **Ask the analyst:** suggested questions and a chat box. Every answer has a one-line headline, 2 to 4 metric cards tinted good, warning or bad, a chart (stacked, grouped or single bar, or line), a colour-coded table, Export CSV, and "Code the agent ran". No paragraphs.
- **Price table:** items by vendors, in landed rupees per spec kg. Cells can say Declined, Not comparable yet, or Not enough data. Clicking a price shows how it was built: unit, discount, currency, duty, freight and strength.

**Insight:** like-for-like prices, and answers to what-if questions such as splitting the award.

### 5. Attributes management
**Question it answers:** what matters for each item?

- **Attributes table:** Landed cost, Delivery reliability, Quality, Inventory and storage fit, Supply risk, Compliance and spec fit, each with why it is measured and how.
- **The 10 questions**, with the attribute each feeds and which are knockouts.
- **Templates:** Cost first, Quality first, Reliability first. Each attribute is set High, Medium or Low. Buyers can save changes and create new templates.
- **Item tags:** each ingredient is tagged to a template. Changing a tag shows a message such as "Best vendor changes from Kovai to Vembanad".
- **Explainer:** how the score is calculated, and the known bias against new vendors.
- **Next:** Claims vs evidence.

### 6. Claims vs evidence
**Question it answers:** can I trust what vendors claim?

- **Top note:** evidence decides 30% of the total. Good counts 100, Medium 60, Low 20. No evidence is always Low and always fails.
- **Rule explainer:** 8 to 10 conditions met is Good, 6 or 7 is Medium, 5 or fewer is Low. Good and Medium pass. If Supports the claim, Dates make sense or Looks genuine is missed, the claim is Low.
- **Vendor summary:** claims, counts of Good, Medium and Low, passed, failed, and overall evidence.
- **Claims table for one vendor:** filter by item and by failed only. Columns are item, claim type, claim, evidence provided, how it was checked, conditions met, evidence and result.
- **Row detail:** the 10 conditions, each Met or Not met, with who checked it (Agent, Code or Rule) and a note.
- **The 10 conditions:** Issuer named, Maker or independent source, Right SKU, Answers our question, Supports the claim, Enough data, Complete, In date, Dates make sense, Looks genuine.
- **Known-bias note:** new vendors have no history with us, so their evidence is usually Low.
- **Next:** Run evaluation.

### 7. Run evaluation
**Question it answers:** who should I choose?

- **Run evaluation button:** opens a dialog to pick a template, showing how many items use it, then Submit.
- **Switches:** By SKU or By vendor, and Scores or Actual values.
- **By SKU:** for each item, the top 3 vendors that passed the checks, then those that failed. Columns are the 6 attributes, Evidence, Total and Note (Best, or a reason such as COA expired).
- **Actual values:** the same grid with Rs per kg, OTIF and lead time, defects and COA status, MOQ and shelf life.
- **Click any cell:** one short explanation.
- **Choose vendors and export:** pick a vendor or Hold per item, then export the decision to Excel.
- **Insight:** the best vendor per item, with the trade-off and the reason, not a black-box rank.

### 8. Agent trace
**Question it answers:** what did the AI do?

Show 4 metrics (agent runs, cache hit rate, estimated cost, tool errors repaired), a table of the 8 agents with job, model and runs, a usage table by agent, and a run picker that opens each tool call with its input and result.

### 9. Architecture
**Question it answers:** how does it work?

A flow diagram and the technical write-up:

Mailbox event → Intake Router → Document Extractor ↔ Extraction Reviewer → Questionnaire Analyst → Evidence Evaluator → Rule engine → Vendor Liaison → Confidentiality check → Human approval → Send email.

## Colour rules

- **Status:** green for Good, Pass, Answered and Proceed. Amber for Medium, Partly and Wait. Red for Low, Fail, Refused and Hold. Grey for N/A. Always pair colour with a word.
- **Each vendor keeps one colour on every chart:** Kovai blue `#2a78d6`, Tungabhadra orange `#eb6834`, Vembanad aqua `#1baf7a`, Lumen yellow `#eda100`, Nilagiri pink `#e87ba4`.
- Keep the rest of the interface neutral, so colour always means something.

## Mock data

**Vendors:**

| Vendor | Location | Type | Reply format |
|---|---|---|---|
| Kovai Finechem | Coimbatore | Existing manufacturer | Excel |
| Tungabhadra Actives | Hubballi | Distributor | PDF |
| Vembanad Botanicals | Kochi | Existing, family-run | Word |
| Lumen Peptide Trading | Singapore | New trader, quotes in USD | Phone photo |
| Nilagiri Phytolabs | Ooty | New | Short email |

**Items:**

| Code | Item | Spec | Template |
|---|---|---|---|
| 001 | Propanediol | >=99.5% purity | Cost first |
| 002 | Glycerin | >=99.5% purity | Cost first |
| 003 | Niacinamide | >=99% purity | Quality first |
| 004 | D-Panthenol | 98% active | Quality first |
| 005 | Caffeine | >=98.5% purity | Quality first |
| 006 | Preservative blend | 90:10 blend | Quality first |
| 007 | Hydroxyethylcellulose | 4,000-6,000 cP | Cost first |
| 008 | Rosemary extract | 20% rosmarinic acid | Quality first |
| 009 | Copper Tripeptide-1 | 1,000 ppm peptide | Reliability first |
| 010 | Acetyl Tetrapeptide-3 | 500 ppm peptide | Reliability first |

**Sample evaluation row:** Propanediol, Kovai, Rs 322 per spec kg, OTIF 96%, COA valid, Evidence Good, Total 7.0, Best.

**Sample failed claim:** Nilagiri, Rosemary COA. Batch 001 was made after its COA was issued, and every result sits exactly on its limit. Low, Fail.

## Deliver

- All 9 screens, linked through the menu
- Working states: inbox tabs, approval card, Run evaluation dialog, By SKU and By vendor switches, row and cell detail, and analyst answers
- Empty states, such as no replies yet
- One reusable set of components: status badge, metric card, data table, chart card and detail panel
