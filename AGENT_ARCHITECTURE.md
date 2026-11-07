## Summary

| Question | Answer |
|---|---|
| Orchestration | LangGraph `StateGraph`, one run per mailbox event, with SQLite checkpoints |
| Multi-agent pattern | Graph-orchestrated specialists. Eight agents with separate roles, tools and context. They hand off through graph state and the database, not by chatting |
| Agent loop | Custom harness on the Anthropic SDK (`proto/agentkit.py`), not LangChain. The model chooses which tools to call and when to stop |
| Models | Routed per job: `claude-haiku-5-5` by default, `claude-sonnet-5-5` where accuracy needs it. Opus isn't used. See Cost control |
| Trigger | Event-driven. A new message starts the graph in a background worker with no user action |
| Human in the loop | LangGraph `interrupt()`. The graph sleeps at the gate, checkpointed, until the buyer acts |
| System of record | SQLite (`runtime/rfx.db`): messages, records, field audit, approvals, events, runs, tool steps |
| Decisions | Agents read, reason and draft. Deterministic code calculates and ranks. The buyer approves anything that leaves |
| Evidence | No scores. The Evidence Evaluator answers 10 yes-or-no conditions per document. Code counts them into Good, Medium or Low, which decides Pass or Fail |
| Vendor line support | Not pre-assigned. Every vendor receives all 10 lines; the agents record what each one says it supports |
| Evaluation model | 10 questions feed 6 attributes. Items are tagged to a template, and each run ranks the top vendors for that template's items |

## Why this is an agent system and not an LLM wrapper

A wrapper sends text to a model and shows what comes back. Here:

- **Agents act through tools.** The Extractor decides what to open, reads it, saves records, and repairs a call if validation rejects it.
- **Agents loop.** Each one runs until it decides it's finished, within a turn limit.
- **Control flow depends on what's found.** A question skips extraction, a failed review loops back, a steering attempt goes to the Liaison and the buyer.
- **State persists.** Records, per-vendor memory and paused workflows survive restarts.
- **Agents check each other.** An independent Reviewer re-reads the sources and can send work back.
- **The system acts unprompted.** A new email starts it. Nobody clicks "process".

## The agents

| Agent | Job | Tools | Effort | Max turns |
|---|---|---|---|---|
| RFx Co-pilot | Builds the RFx with the buyer | get_rfx_lines, get_storage, get_vendors, update_rfx_draft | low | 6 |
| Intake Router | Classifies each message, and detects steering attempts and requests for company information | get_thread, submit_triage | low | 4 |
| Document Extractor | Turns any format into structured records | list_files, read_attachment, view_image, get_thread, get_current_record, save_quote_line, mark_not_quoted, save_vendor_facts, save_discount, save_coa, finish_extraction | medium | 16 |
| Extraction Reviewer | Independently checks the record against sources. Cannot write to it | list_files, read_attachment, view_image, get_current_record, submit_review | medium | 10 |
| Questionnaire Analyst | Maps what the vendor said onto the 10 questions, with status, evidence and rating | list_files, read_attachment, view_image, get_thread, get_recorded_answers, save_question_answers, finish_mapping | low | 8 |
| Evidence Evaluator | Assesses each evidence document against 10 fixed conditions. Those answers decide whether each claim passes or fails | get_documents_to_check, read_attachment, view_image, record_document_check, finish_verification | medium | 10 |
| Vendor Liaison | Decides the next move, owns vendor memory, and declines requests for company information | get_open_issues, get_questionnaire_gaps, get_thread, get_vendor_memory, update_vendor_memory, check_uom_rule, draft_vendor_email, escalate_to_buyer, no_action | medium | 8 |
| Analyst | Answers buyer questions with real analysis, as a headline, metric cards, a chart and a colour-coded table | get_data_dictionary, get_evidence, run_analysis, submit_answer | medium | 8 |

Rule engines, deliberately not agents: **Normaliser** (units, strength, FX, duty, freight, discount), **Evidence Checker** (claims vs history, COA, shelf life, MOQ, space, lead time, knockouts), **Fact check** (counts the 10 conditions, applies the gates, and gives Good, Medium or Low), **Scorer** (per-SKU score, vendor roll-up) and **Decision rules** (proceed, conditions, wait, hold, do not proceed).

## Graph

Nodes: `triage`, `extract`, `review`, `dispute`, `questionnaire`, `verify`, `rules`, `liaison`, `escalate`, `queue_approval`, `human_gate`, `send`, `wrap`.

- `triage` routes on intent, failing safe: anything that isn't an auto-reply, a question or a steering attempt goes to extraction, so a wrong label can't lose data. A steering attempt goes straight to `liaison`, so that text is never processed as data.
- `review` returns to `extract` once. A second failure goes to the buyer as a dispute.
- `questionnaire` runs after review, then `verify` runs the Evidence Evaluator if the message has attachments. `rules` follows, so evaluation data always reflects the latest evidence.
- If the Router flags a request for company information, the Liaison must reply, and code requires the standard refusal in the draft.
- `queue_approval` is separate from `human_gate` because LangGraph re-runs a node on resume. The approval must not be created twice.

## Evaluation model

**Questionnaire to attributes.** The questionnaire was cut from 42 questions to 10, keeping all six attributes. Each question belongs to exactly one attribute (`proto/attributes.py`). Q5, Q9 and Q10 are knockouts.

| Attribute | Questions | Scored from |
|---|---|---|
| Landed cost | Q1 price and terms, Q2 units and strength | Rs per spec kg (rules) |
| Delivery reliability | Q3 lead time, Q4 OTIF | 70% OTIF and 30% lead-time steadiness, from our records |
| Quality | Q5 COA, Q6 rejections and certificates | Defect rate from our records |
| Inventory and storage fit | Q7 MOQ and shelf life | 6-month holding cost and write-off risk |
| Supply risk | Q8 source and continuity | Answer rating |
| Compliance and spec fit | Q9 SDS and regulation, Q10 cold chain | Answer ratings |

**Answer tracking.** For each vendor and question the system stores status (answered, partly, refused, not answered), evidence (document, our records, vendor statement, none) and a rating. The cold-chain question applies only to vendors quoting peptides. The buyer sees each answer in the vendor's inbox under Questionnaire answers, and every vendor side by side in Vendor status. Facts already in the quote, such as price or MOQ, are filled in by code so nobody is asked twice.

**The AI's role in Supply risk and Compliance.** The Questionnaire Analyst labels each answer good, ok or weak. Code turns the labels into points (100, 60, 20). This is the one place AI judgement feeds a score, and each label is visible under Questionnaire answers.

**Priority templates.** Cost first, Quality first and Reliability first rate each attribute High, Medium or Low (weights 5, 2, 1), and buyers can create their own. Every item is tagged to one template, editable at any time. A run covers only that template's items and shows the top three vendors that passed the checks. Saving a template appends a version in the background. Quality stays protected in Cost first because knockouts still apply.

**Score.** Calculated in code, in `engine.score()`. Total = 70% weighted attribute performance + 30% evidence, where the evidence level counts Good 100, Medium 60, Low 20. The best bid on Cost scores 10, and each 1% above it loses 0.5. Inventory works the same way on holding cost, at 0.15 per 1%. Attributes with no data are left out, not scored as zero. A failed knockout removes a vendor from the ranking.

**Claims vs evidence.** `proto/factcheck.py` lists every claim per vendor and item. An AI asked for a score out of 10 can give a different number on each run, so evidence has no scores. Every claim goes through the same 10 yes-or-no conditions.

| # | Condition | Decided by |
|---|---|---|
| 1 | Issuer named | Agent |
| 2 | Maker or independent source | Agent |
| 3 | Right SKU | Agent |
| 4 | Answers our question | Agent |
| 5 | Supports the claim (gate) | Agent; code overrides on a strength conflict |
| 6 | Enough data | Agent |
| 7 | Complete | Agent |
| 8 | In date | Code for COAs, otherwise agent |
| 9 | Dates make sense (gate) | Code for COAs, otherwise agent |
| 10 | Looks genuine (gate) | Agent |

| Conditions met | Evidence | Result |
|---|---|---|
| 8 to 10 | Good | Pass |
| 6 or 7 | Medium | Pass |
| 5 or fewer | Low | Fail |

- **Gates:** missing a gate condition makes the claim Low, whatever the count, so a fake can't pass on the strength of its other nine answers.
- **No evidence:** always Low and Fail. A claim typed in an email counts as no document.
- **OTIF and defect claims:** no agent is involved. Code answers the same 10 conditions from our POs, receipts and inspections, and needs at least 6 PO lines on that item for Enough data.
- **Item level:** Good if 80% or more of the item's own claims (specification, OTIF, defect rate) pass, Medium if 60% or more, otherwise Low. Vendor-wide claims, such as certificates, count only in the vendor's overall evidence, so one missing certificate doesn't mark down every item. Knockouts still cover regulation and cold chain.
- **Limit:** the agent can't confirm a document with its issuer, so a pass means nothing looks wrong, not that it is proven genuine.

**Reading a result.** One table with two switches: By SKU or By vendor, and Scores or Actual values. Clicking a cell gives one short reason. Scores display out of 10.

## Tools and code-enforced guardrails

Each agent has an allowlist, and calling anything else fails. Guardrails live in tools, not only in prompts. In the terms from the Unloop build, the LLM recommends and code enforces.

| Guardrail | Enforced in code by |
|---|---|
| No invented source | `save_quote_line` rejects a `source_quote` not found in the vendor's documents (images are exempt) |
| Scope | Items that aren't RFx lines are rejected. A vendor not mentioning a line is never treated as an error |
| No data loss | Null fields never erase a stored value, an answer is never downgraded, and every change is written to `field_audit` |
| Vendor confidentiality | `draft_vendor_email` blocks a draft that names another vendor |
| Company confidentiality | Three layers. The Liaison has no tool that reads forecast, cost or stock data. `leak_check` blocks drafts with internal terms, finished-goods codes, forecast volumes or another vendor's price. If the Router flagged a request, the draft must contain the standard refusal, and the Liaison can't end the run without replying |
| Evidence integrity | Code rechecks dates and strength, counts the conditions and applies the gates. The agent can't pass a claim with no evidence |
| Analyst output | `submit_answer` rejects long text, and answers with no table, chart or cards. Chart columns must exist and be numeric |
| Retry limit | Issues with no tries left can't go in an email; three tries per issue |
| Nothing sent silently | Agents can only queue a draft. Sending happens after `human_gate` |
| Scoring integrity | No agent has a tool that can change scores, weights or rankings |
| Analyst safety | `run_analysis` works on copies, with restricted builtins and blocked imports |

Strict tool schemas guarantee valid calls on the smaller tools. The two widest tools exceed the API's limit on optional fields, so code validates them instead.

## Prompt techniques

- **Role and boundary per agent:** each prompt says what the agent owns and what it must not do.
- **Faithfulness rules:** record as stated, never convert, missing stays null. Conversion belongs to the rule engine.
- **Reviewer calibration:** PASS and FAIL examples set the bar, so style differences don't fail a correct record.
- **Structured endings:** agents finish through a tool such as `submit_triage`. No free-text JSON is parsed.
- **Self-correction through tool errors:** rejected calls return the reason, and the agent repairs them.
- **Untrusted content boundary:** vendor text sits in `<untrusted_vendor_content>` tags under a shared trust rule.

## Context engineering

Each run starts with a small working set instead of a growing transcript.

| Layer | Contents | Lifetime |
|---|---|---|
| Static prefix | Tools, role, company, 10 RFx lines, trust rules | Byte-identical across runs; cached |
| Task | The event, invited lines, the message | One run |
| On demand | Attachments, thread, stored record, open issues | Pulled by tools only when needed |
| Structured memory | Records in SQLite | Permanent; the source of truth |
| Rolling memory | Per-vendor summary under about 150 words, rewritten by the Liaison after each event | Life of the RFx |

- **Between runs:** no transcript is carried over. Continuity comes from the database and rolling memory, so context size stays flat however long a vendor thread gets.
- **Within a run:** messages are append-only, which keeps the cache and thinking blocks valid. Long files are paged, not truncated.
- **Co-pilot and Analyst:** bounded windows of 8 turns and 3 Q&A pairs. Earlier analyst tool output isn't carried forward.
- **Not needed yet:** runs are a few turns, far below the 1M window. Server-side compaction and context editing would be the next step for long-lived agents.

## Cost control

| Agent | Model | Effort | Why |
|---|---|---|---|
| Intake Router, Questionnaire Analyst, Vendor Liaison, RFx Co-pilot | Haiku | low | Classification, mapping and short drafting |
| Evidence Evaluator | Haiku | medium | Reads short documents; dates and limits are enforced in code |
| Document Extractor, text files | Haiku | medium | Structured reading, protected by code checks and the Reviewer |
| Document Extractor, photos or after a failed review | Sonnet | medium | Router escalates only when needed |
| Extraction Reviewer | Sonnet | low | A checker should be stronger than the model it checks |
| Analyst | Sonnet | low | Writes code the buyer relies on |

- **Router:** `route_extraction()` picks the model per message and logs its reason.
- **Practice mode:** on by default. An identical request replays its saved real response at no cost; anything new calls the model. Tools still run, so the database, stages and approvals behave normally. Turn it off for fully fresh calls.
- **Spend cap:** a daily limit in rupees, default Rs 50. Agents pause when it's reached. Spend survives a demo reset.
- **Calls skipped by rules:** text-only follow-ups skip the Reviewer, and the Liaison isn't called when nothing is open.
- **Prompt caching and low effort:** covered below. Output tokens were the main cost, mostly thinking.

**Measured, on routed models:**

| Run | Cost | Time |
|---|---|---|
| First round: five replies, with one reviewer escalation | Rs 21.34 | 114 seconds |
| Whole scenario, adding follow-ups, silence, edge cases and two analyst questions | Rs 28.06 | - |
| A single text follow-up | Rs 0.31 | - |
| Identical repeat in Practice mode | Rs 0 | 11 seconds |

The same first round on Opus was estimated at about Rs 122. Most of the cost now sits in the Sonnet steps, the photo and the Reviewer, which is where accuracy pays for itself.

## Prompt caching

- The system block has an explicit `cache_control` breakpoint, and top-level automatic caching moves a second breakpoint forward each turn.
- Nothing volatile (dates, IDs) sits in the prefix. Render order is tools, system, messages.
- Default 5-minute TTL, chosen because replies arrive close together in a demo.

## Reliability and observability

- **Refusals:** server-side `fallbacks: "default"` is on, and a remaining refusal is surfaced as an error.
- **Retries:** the SDK retries transient failures (3 times, 240-second timeout).
- **Concurrency:** 3 background workers, with a lock per vendor so messages from one vendor are processed in order.
- **Stage accuracy:** mailbox stages are derived from facts each time, not set by agents.
- **Early stops:** an agent that stops without calling its finish tool is told to finish, up to twice.
- **Trace:** every run, tool call, input, output, time and token count is stored and shown in Agent trace.

## Measured results

From a live run on routed models, on the five first replies.

| Metric | Result |
|---|---|
| Field extraction (133 checks) | 100% precision and recall, same as Opus |
| Planted traps caught | 9 of 9 |
| Agent failures | 0 |
| Tool calls rejected and repaired | 2, both by the Analyst |

**What the Reviewer earned:** Haiku read "items 1 to 5" as RM-001 to RM-005. The Sonnet Reviewer caught it, the router escalated, and the corrected list passed review.

**How to read these:** the eval is one run on five documents I generated, with a known answer key. It proves the loop works and catches regressions; it says nothing about accuracy on real vendor documents. It scores first replies only, so follow-ups were checked by scenario. Run it with `tools/eval_extraction.py`.

## Known limits

- **Critical known bias against new vendors.** New vendors have no history with us, so their OTIF and defect claims can't be checked and their evidence is usually Low. Evidence is 30% of the total, so existing vendors gain an advantage that says nothing about real quality. Roadmap: a separate new-vendor path that accepts references, trial orders and third-party audits, and judges evidence against what a new vendor could reasonably provide.
- Questionnaire answers are stored per vendor, not per line.
- The attribute-to-question mapping, rating points and evidence weights are design choices, set in code.
- Yes-or-no conditions reduce run-to-run variation but don't remove it, because the agent still reads each document. Practice mode replays saved answers.
- Email delivery is simulated. The vendor first replies are pre-written files; the reading of them is live.
- The job queue is in memory: a restart loses queued work, but paused approvals survive in checkpoints.
- Single machine, SQLite, no login, and no role-based access.
- `run_analysis` is restricted but is not a hardened sandbox. Production needs real isolation.
- No vector search. Ten lines and small threads don't need it; a large catalogue or contract library would.
- The review loop has no independent source for images beyond a second reading by the same model.
