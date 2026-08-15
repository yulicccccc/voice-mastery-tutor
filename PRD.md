# AI Voice Oral Mastery Coach — Living PRD

**Version:** v1.2  
**Status:** Discovery / Product Core Validation  
**Last updated:** 2026-08-14

> Synced from the project Living PRD in Google Drive. The Google Doc remains the project source of truth.

## 0. DOCUMENT RULES — LOCKED

This Google Doc is the single source of truth for the project. Every confirmed requirement, implementation decision, experiment result, failure mode, technical risk, and rejected direction must be recorded here. Discussion does not automatically equal a requirement. Items are explicitly labeled as LOCKED, HYPOTHESIS, OPEN RISK, EXPERIMENT RESULT, or REJECTED.

## 1. PRODUCT ORIGIN & MISSION — LOCKED

The product originates from a real-life constraint: many useful periods of time are hands-busy / eyes-busy but ears and voice remain available, including driving, housework, walking, commuting, and repetitive work. Traditional Anki-style study often assumes the user can sit down, look at a screen, and press buttons. This product should convert those otherwise underused periods into active learning with an AI tutor.

Mission: Make exceptional one-on-one tutoring continuously accessible and affordable to everyone.

Core product story: Collected knowledge is not learned knowledge. The product closes the gap from captured information to usable mastery.

Capture ≠ Learning ≠ Mastery.

## 2. PRODUCT DEFINITION — LOCKED

A voice-first, hands-free, dialogue-first AI oral mastery tutor. It should behave more like a patient human tutor than an audio player or voice flashcard system.

The product asks, waits, listens, diagnoses, teaches only what is needed, requests a new attempt, tests transfer, records mastery evidence, and schedules future retrieval.

Internal shorthand: “advanced voice Anki + human-like tutor.” This is useful as an internal mental model but should not constrain the product to flashcards only.

## 3. CORE LEARNING MODEL — LOCKED

The product uses two nested loops.

**Inner Tutor Loop:**

Question / scenario → learner speaks → diagnose → minimal intervention → learner retries → reconstruct / re-explain → example or transfer test → mastery evidence.

**Outer Memory Loop:**

Due item → retrieval attempt → review outcome → spaced scheduling → future retest.

Anki/FSRS is the preferred memory scheduler in early versions. The AI Tutor owns diagnosis and teaching.

## 4. DEFAULT LEARNING UNIT — LOCKED

Default unit: Atomic Retrieval Unit.

Principles:

- short and orally answerable;
- one main association or target at a time;
- minimal cognitive load by default;
- suitable for hands-free contexts;
- can represent either knowledge recall or target performance.

Two broad atomic types:

A. Knowledge atomic unit: relatively clear fact, concept, distinction, cause, definition, step, or relationship.

B. Performance atomic unit: no single exact answer; success is judged by a target performance rubric, e.g. small talk, interview response, explanation, persuasion, English speaking.

High-cognition framework questions are allowed as an optional advanced mode, not the default.

## 5. MATERIAL INGESTION & ATOMIC TRANSFORMATION — LOCKED

The learner should be able to provide a long note, webpage clipping, Anki deck/card, or other source without manually creating every training prompt.

Pipeline:

Source material → preserve original source → identify knowledge structure → derive atomic retrieval units → tutor training.

Rule: Never destroy the source. Derive trainable units from the source.

The AI may propose splits or derived questions, but source provenance must be preserved.

## 6. VOICE / HANDS-FREE UX — LOCKED

The user may have only mouth and ears available. Therefore the system must minimize screen dependence, taps, menus, and decision burden.

Defaults:

- AI proactively selects the next due/appropriate unit.
- One question at a time.
- One feedback point at a time.
- Short AI turns; learner speaks more.
- User should not need to organize notes or manually maintain the learning log during a session.
- AI must not end or pause a training session unless the user explicitly stops, or a safety constraint requires it.
- In high-risk contexts such as driving, the interface must avoid visual interaction and minimize distraction.

## 7. DIAGNOSIS-FIRST TEACHING — LOCKED

The AI must not assume that a failed response means “forgot.” It must diagnose before choosing an intervention.

Possible learner states include:

- independently recalled;
- recalled with hesitation;
- cannot retrieve but appears to understand;
- partial understanding;
- misconception;
- can repeat wording but does not understand;
- understanding repaired but retrieval still weak;
- can explain but cannot transfer;
- stable mastery evidence.

Rule: Diagnose first, then choose the intervention.

## 8. FAILURE / HELP LADDER — LOCKED

When the learner cannot answer, the AI should not immediately reveal the full answer.

Default progressive support:

1. wait / allow retrieval effort;
2. smallest useful cue;
3. stronger cue;
4. partial structure / first element;
5. concise answer only if necessary;
6. require learner to produce the answer again after help.

The amount of help used must be recorded because “correct after hint” is not equivalent to independent retrieval.

## 9. UNDERSTANDING REPAIR BRANCH — LOCKED

If the learner does not understand the content, the tutor temporarily leaves pure retrieval mode and enters explanation mode.

Flow:

Detect understanding gap → explain why / underlying mechanism → concrete example → learner explains in own words → alternate example / near-transfer problem → return to retrieval loop.

The tutor must distinguish “can repeat” from “understands.” If the user says “I can repeat it but I still don’t understand,” the system must downgrade the mastery state and continue teaching.

User self-report can override an overly optimistic AI mastery judgment.

## 10. EXAMPLES, WHY, AND TRANSFER — LOCKED

For method or conceptual learning, the tutor should explain why the method works, not only the procedure.

Concrete examples are a required repair tool when abstract explanation is insufficient.

Mastery is stronger only after the learner can use the idea in a new example, compare cases, generate an example, or solve a near-transfer situation.

Repeating the teacher’s sentence alone is insufficient evidence of mastery.

## 11. CONTINUITY RULE — LOCKED

The default learning session continues automatically from one unit to the next. The tutor must not repeatedly ask “Do you want to continue?” The user explicitly controls stopping or switching to product-reflection mode.

## 12. PRODUCT-REFLECTION MODE — LOCKED

During a training experiment the learner may pause content practice to report a product problem or idea. The system must distinguish:

A. learning interaction;

B. product-design reflection.

Product observations discovered during practice must be added to the PRD experiment log before training resumes.

## 13. ANKI INTEGRATION — LOCKED DIRECTION

Early product direction: integrate with Anki rather than rebuild Anki.

Division of responsibility:

- Capture layer (e.g. WuCai/web notes): get information in.
- Anki / FSRS: scheduling and memory review state.
- Voice Tutor: oral retrieval, diagnosis, understanding repair, examples, transfer, mastery evidence.

Core principle:

Anki decides when to ask again. The AI Tutor decides what to do when the learner cannot answer well.

## 14. ANKI REVIEW STATE VS TUTOR MASTERY STATE — LOCKED

These are separate.

Anki review outcome describes the first unaided retrieval attempt for scheduling.

Tutor mastery state describes what the learner can do after diagnosis/teaching in the current session.

MVP rating mapping:

- Again = first unaided retrieval failed.
- Good = first unaided retrieval succeeded.

Hard/Easy may be added later after evidence shows reliable automatic rating.

If the learner initially fails, receives explanation, and later understands, the Anki review can still be Again while Tutor Mastery records “understanding repaired / transfer passed.”

## 15. ANKI REVIEW WRITE-BACK — LOCKED DIRECTION

The Tutor should not directly manipulate FSRS scheduling parameters such as due date, interval, difficulty, or stability.

It creates a Review Event tied to anki_card_id and later submits the review outcome through Anki’s scheduler. Anki remains the scheduling source of truth.

ReviewEvent minimum data:

- event_id;
- anki_card_id;
- anki_note_id;
- first_attempt_result;
- mapped_anki_rating;
- hints_used;
- understanding_gap_detected;
- explanation_given;
- transfer_result;
- tutor_mastery_state;
- source/scheduler snapshot;
- created_at;
- sync_status.

Offline/hands-free learning may create pending Review Events. A later Anki Bridge can apply them when Anki is reachable.

Conflict rule: if the same card has been reviewed elsewhere after the snapshot, do not silently overwrite. MVP behavior: skip conflict and log it.

## 16. CONVERSATION-DRIVEN CARD EVOLUTION — NEW, LOCKED REQUIREMENT

Problem: during tutoring, the learner may discover a new insight, recurring mistake, better explanation, personal example, missing prerequisite, or a flaw in the original card. These learning artifacts should not disappear when the conversation ends.

First principle: the difficult part is not technically editing Anki; the difficult part is deciding WHAT is safe and useful to edit without corrupting the original source or turning cards into bloated notes.

Therefore card evolution uses layers.

**Layer A — Immutable Source**

Preserve the original captured/source content and provenance. AI must not silently rewrite the historical source.

**Layer B — Canonical Learning Target**

The current prompt and answer/reference used for retrieval. Changes to these require stronger evidence because they alter what is being tested.

**Layer C — Tutor Learning Overlay**

Conversation-derived information that can evolve frequently, including:

- My Insight / learner-generated understanding;
- Common Mistake / recurring error;
- Why / mechanism;
- Concrete Example;
- Counterexample;
- Better Cue / improved question wording;
- Missing Prerequisite;
- Personal Association;
- Tutor Note;
- Mastery evidence.

## 17. CARD UPDATE EVENT MODEL — NEW, LOCKED REQUIREMENT

Every conversation-derived change should be represented first as a CardUpdateEvent rather than an untracked overwrite.

CardUpdateEvent fields:

- update_event_id;
- anki_note_id;
- related anki_card_id(s);
- target_layer / target_field;
- old_value;
- proposed_new_value;
- update_type (insight, misconception, example, cue improvement, answer correction, prerequisite, etc.);
- origin (learner said it / tutor inferred / source-derived);
- source_reference or conversation reference;
- confidence;
- created_at;
- sync_status;
- reversible/version history.

## 18. SAFE AUTO-UPDATE POLICY — NEW, LOCKED DIRECTION

Not every conversational insight should rewrite Front/Back.

Safe to auto-save to Tutor Overlay:

- learner’s own insight;
- recurring mistake;
- personal example;
- tutor explanation summary;
- hint that worked;
- mastery evidence.

Needs stronger validation before changing Canonical Prompt/Answer:

- correcting a factual answer;
- changing the meaning of the card;
- deleting source-derived content;
- merging/splitting cards;
- changing the prompt in a way that changes the tested association.

The product should prefer reversible append/update operations over destructive replacement.

## 19. ANKI CONTENT WRITE-BACK — TECHNICAL FEASIBILITY

Technically feasible. Anki content belongs to a Note; scheduling belongs to Cards. A note can generate multiple cards. The integration must retain both note_id and card_id.

MVP write-back architecture:

Tutor conversation → CardUpdateEvent → validation → pending content-sync queue → Anki Bridge → update note fields/tags → Anki sync.

For supported note types, preferred dedicated fields include:

- Source;
- TutorNotes;
- MyInsight;
- CommonMistakes;
- Examples;
- LastTutorUpdate.

For existing note types that do not have these fields, do not silently damage Front/Back. MVP should keep the overlay in the Tutor database and optionally sync a compact summary only when an approved field mapping exists.

## 20. PRD / MEMORY CONTINUITY — LOCKED

The Living PRD is intended to prevent project knowledge loss. Product decisions, experiments, failure cases, and implementation decisions must be written here rather than relying on conversational memory alone.

## 21. EXPERIMENT FINDINGS SO FAR

- NotebookLM experiment: broadcast-first behavior failed the required dialogue-first tutor loop.
- Open-ended small-talk prompt created activation friction; starting task was too large.
- Atomic retrieval worked better for hands-free practice.
- AI prematurely stopped sessions multiple times; continuity rule added.
- Pure answer reveal risks rote memorization; progressive hints added.
- User sometimes could repeat a response without understanding; understanding-repair and transfer were added.
- Tutor incorrectly marked mastery before learner agreed; user mastery override and dual-state tracking added.
- Concrete examples substantially improved understanding of abstract methods.
- Diagnosis-first behavior is more appropriate than assuming every failure is a memory failure.

## 22. OPEN RISKS / UNVALIDATED ASSUMPTIONS

- Natural voice turn-end detection without interruption.
- Reliable classification of “forgot” vs “does not understand.”
- Reliable mastery/transfer scoring.
- Voice latency and cost.
- Driving safety and cognitive distraction.
- Robust offline queue and eventual Anki synchronization.
- Conflict handling when the same Anki card is reviewed on multiple clients.
- How much conversational information should be promoted from Tutor Overlay into the canonical Anki note.
- Preventing dynamic card updates from making cards too long or changing the original learning target.

## 23. CURRENT PRODUCT THESIS

The product is not primarily another note app and not merely a voice flashcard player. Its job is to convert collected knowledge into retrievable, understandable, transferable ability through a hands-free AI tutor, while using a spaced memory system such as Anki/FSRS for long-term scheduling.

## 24. LEARNER MODEL / STUDENT PROGRESS MODEL — NEW, LOCKED REQUIREMENT

The tutor must maintain an explicit learner model. A human-like tutor is not merely a question generator; it remembers what the learner has attempted, where they repeatedly fail, what they understand, what they can only repeat, which explanations worked, and what evidence exists for transfer.

The learner model must operate at two levels:

**A. Item-level state (per Anki card / atomic unit)**

- first unaided retrieval result;
- hesitation / response quality;
- hints used and which hint worked;
- recurring error or misconception;
- understanding gap detected;
- explanation(s) that worked;
- learner-generated insight / personal association;
- example or counterexample that improved understanding;
- transfer evidence;
- tutor mastery state;
- Anki review outcome and next due information when available;
- timestamped history rather than only the latest state.

**B. Concept-level state (across cards)**

- concepts currently strong / weak;
- missing prerequisite knowledge;
- repeated misconception patterns across multiple cards;
- concepts that can be recalled but not explained;
- concepts that can be explained but not transferred;
- learner-specific explanations / examples that repeatedly help;
- mastery trajectory over time.

Rule: the tutor should use this learner model to choose what to ask next and how to teach it. The next question should not depend only on deck order or due date.

Important distinction:

Anki memory state answers: “When should this item be retrieved again?”

Tutor learner model answers: “What does this learner currently understand, misunderstand, and need next?”

Safety / accuracy rule: one conversational utterance must not become a permanent student belief profile without evidence. Learner-state inferences should carry confidence, be revised by later evidence, and be overridable by the learner.

## 25. KNOWLEDGE MAP & STARTING-POINT DIAGNOSIS — NEW, LOCKED REQUIREMENT

When source notes, webpages, or Anki material are ingested, the system should not merely convert every sentence into isolated cards. It should derive a lightweight knowledge map showing concepts, atomic units, relationships, and prerequisites.

Purpose:

- help the tutor know what to ask;
- help the learner know where to start;
- identify missing prerequisite knowledge;
- prevent advanced questions from being asked before foundational concepts are understood;
- connect isolated cards into a coherent learning path.

Default flow:

Source / Anki deck → derive concepts and atomic units → infer prerequisite relationships where supported → run a short diagnostic through oral retrieval → update learner model → choose the next best learning unit.

Question-selection priority for the MVP:

1. Due memory items that need retrieval according to Anki/FSRS;
2. prerequisite gaps blocking current understanding;
3. recently exposed misconceptions or weak points;
4. cards containing learner insights or examples worth reconsolidating;
5. transfer checks for concepts previously marked as understood.

The learner's own insights are first-class learning material. They are not merely notes to archive: when relevant, the tutor should bring them back into future retrieval, explanation, or transfer questions so that review reconnects the learner with their own evolving understanding.

New product implication:

The Tutor is not only a voice interface over Anki. It is a persistent Student Model + Teaching Policy operating on top of Anki's memory scheduler.

## 26. ANKI CARDS AS TEACHER-FACING MATERIAL — NEW, LOCKED REQUIREMENT

Core reframing: the learner should not be required to study Anki cards directly. In this product, Anki cards primarily become material for the AI Tutor to read, interpret, schedule from, and teach from. The learner's job is mainly to capture what they want to learn and then participate in oral learning; the Tutor owns the pedagogical transformation and review interaction.

User responsibility:

- collect / highlight / save material worth learning;
- optionally send or sync it into Anki;
- speak answers, questions, confusion, and insights during tutoring;
- explicitly stop or redirect when desired.

Tutor responsibility:

- inspect the card/source and decide what the learner should actually be asked;
- identify whether the existing Anki prompt is pedagogically usable or needs a derived atomic question;
- choose the next item using due state + learner model + prerequisite structure;
- ask orally without requiring the learner to read the card;
- diagnose recall vs understanding vs misconception;
- provide hints, explanations, examples, and transfer tests as needed;
- record learning evidence, misconceptions, insights, and successful explanations;
- update the Tutor Overlay / learner model;
- write the appropriate review outcome back to Anki scheduling;
- propose or safely sync content improvements back to the Anki note when appropriate.

Important architectural implication: Anki Card != Voice Prompt. The Anki card is a teacher-facing memory/scheduling object and source artifact. The Voice Tutor may derive one or more temporary or persistent Tutor Units from it. These Tutor Units can be shorter, more conversational, prerequisite-aware, and adapted to the learner's current state while preserving provenance to the original card/note.

Default relationship:

Anki Note/Card -> Teacher Material -> Tutor Unit(s) -> Oral Interaction -> Learner Evidence -> Learner Model + ReviewEvent + CardUpdateEvent -> Anki Sync.

The learner should not need to see Front/Back during normal hands-free sessions. If the source card is poorly written, too large, too abstract, or contains multiple associations, the Tutor should adapt it for oral teaching instead of forcing the learner to study the raw card.

Product principle: Capture should be low-friction; pedagogy should be AI-owned. The system should reduce the user's burden of card design, card maintenance, question selection, and review-state bookkeeping rather than reproducing those chores in a voice interface.

Risk / boundary: the Tutor must preserve the distinction between source truth and derived teaching material. AI-generated Tutor Units may adapt pedagogy, but must not silently alter the factual meaning of the original source.

## 27. CAPTURE-TO-MASTERY OPERATING CONTRACT — NEW, LOCKED REQUIREMENT

Core user contract: the learner is primarily responsible for deciding what is worth learning and capturing it. The learner should not be required to design perfect cards, manually choose study order, inspect scheduling metadata, or maintain learning-state records during normal use.

The AI Tutor is responsible for turning captured material into teachable interaction. It reads Anki cards/notes and source material as teacher-facing inputs, derives appropriate Tutor Units, chooses the next learning target, asks orally, diagnoses performance, teaches only what is needed, records evidence, and updates future teaching decisions.

The normal hands-free user journey should therefore be:

Capture something worth learning -> material reaches the learning system / Anki -> Tutor interprets it -> Tutor decides what to ask -> learner answers orally -> Tutor diagnoses -> hint / explain / example / transfer as needed -> learner retries -> Tutor updates Student Model + Tutor Overlay -> review outcome is written back to Anki/FSRS -> future session resumes from the updated learner state.

Anki's role in this architecture is primarily backend memory infrastructure for the Tutor: source/card storage, identity, review history, and spaced scheduling. It is not required to be the learner's primary study interface.

The Tutor must remember progress in a teacher-like way. Future questions should be informed by prior independent-retrieval results, hints needed, misunderstandings, recurring errors, successful explanations, learner-generated insights, examples that worked, prerequisite gaps, and transfer evidence.

Learner insights are active teaching assets, not passive annotations. When a learner produces a useful personal explanation, association, example, or realization, the Tutor should preserve it in the Tutor Overlay and may deliberately bring it back in later retrieval, explanation, comparison, or transfer practice.

The system should minimize learner maintenance work. If a source card is badly phrased, too broad, too dense, or not orally answerable, the Tutor should adapt or derive a better teaching question while retaining provenance to the source. The learner should not be forced to fix the card before learning can continue.

Product success criterion for this operating model: a user can spend most of their effort on only two actions — capture what they want to learn, and speak with the Tutor — while the system handles pedagogical transformation, progress tracking, spaced-review state, and learning-record maintenance in the background.

Experiment implication: future prototype tests should evaluate not only whether the Tutor can ask and correct, but whether it can use prior learner history and conversation-derived insights to choose a materially better next question than raw Anki order alone.

## 28. GOOGLE SHEET TEACHER FEED — HISTORICAL PROTOTYPE OPTION, SUPERSEDED AS PRIMARY BRIDGE

Google Sheets was considered as a Teacher Feed / integration bus between capture tools, the Tutor, and a later Anki Bridge because the existing web-note workflow already supports it.

Historical prototype flow:

Web notes / WuCai -> Google Sheet Teacher Feed -> ChatGPT Tutor -> Tutor learning events / learner-state updates -> Google Sheet -> later Anki Bridge -> Anki/FSRS.

Boundary: Google Sheets is an integration surface, not the source of truth for Anki scheduling. Anki/FSRS remains the scheduling source of truth once a card is linked. The Tutor remains the source of truth for teaching-state evidence and learner-model interpretation.

**Superseded decision — 2026-08-13:** Google Sheets may remain useful as a capture source, but it is no longer the preferred bridge between the AI Tutor and Anki. Direct local Anki integration through AnkiConnect + MCP was successfully validated. Avoid unnecessary Google Drive/Sheet round-tripping between Tutor and Anki.

## 29. DIRECT LOCAL ANKI ACCESS — EXPERIMENT RESULT, VALIDATED 2026-08-13

Validation objective: prove that an OpenAI agent can read real due-card data from the learner’s desktop Anki without manual copy/paste.

Result: VALIDATED first through Codex CLI and then through an ordinary non-Codex ChatGPT conversation using a custom MCP app over OpenAI Secure MCP Tunnel. ChatGPT itself successfully invoked `get_due_cards` and returned real local Anki data from `000-WuCai Inbox` (`total_due=8`, `returned=5`).

Validated ordinary-ChatGPT path:

ChatGPT conversation -> custom app `Anki Voice Tutor` -> OpenAI Secure MCP Tunnel -> local `tunnel-client` -> stdio `anki_mcp_server.py` -> AnkiConnect at `http://127.0.0.1:8765` -> desktop Anki -> real card data returned to ChatGPT.

Codex direct MCP remains a useful diagnostic path but is not the intended learner-facing surface.

Updated boundary: ordinary ChatGPT text-chat attachment is VALIDATED. The remaining product-surface question is whether ChatGPT voice mode can invoke the same custom MCP app reliably during a hands-free tutoring session. Voice-mode MCP use remains NOT YET VALIDATED.

## 30. REPRODUCIBLE SETUP RUNBOOK — NEW COMPUTER / RECOVERY

Purpose: recreate the validated read-only integration on another Windows computer without relying on conversational memory.

Default recovery sequence:

1. Install desktop Anki.
2. Install and enable AnkiConnect.
3. Keep Anki open while testing/tutoring.
4. Install Python and clone `yulicccccc/voice-mastery-tutor` into a normal user-writable directory.
5. Install `requirements.txt` and run `smoke_test_anki.py`.
6. Verify `http://127.0.0.1:8765` responds and deck-scoped `is:due` returns real cards.
7. Create/reuse OpenAI Secure MCP Tunnel and install the official `tunnel-client`.
8. Use a restricted runtime credential; never store secrets in chat, screenshots, source control, or permanent shell history.
9. Create an `anki-local` stdio tunnel profile pointing to `anki_mcp_server.py`; use forward slashes in the Windows script path.
10. Run `tunnel-client doctor --profile anki-local --explain` and require `RESULT ok`.
11. Run the tunnel in the foreground and verify `/readyz` returns `ready`.
12. Configure/refresh the `Anki Voice Tutor` custom ChatGPT app against the tunnel and scan its tools.
13. Require an actual ordinary ChatGPT `get_due_cards` call against real local Anki data.
14. Only after the text path is proven, test ChatGPT voice-mode invocation.

Important implementation observations:

- A broad `is:due` query returned 1909 cards; tests must be deck-scoped.
- In the validated deck, Anki UI showed 4 Learn + 4 Due while `is:due` returned 8. Tutor selection must distinguish learning/relearning from ordinary review-due cards.
- Prefer raw `fields` from `cardsInfo`; rendered `question`/`answer` may contain large HTML/CSS noise.
- Do not assume `Front = question` and `Back = answer`; heterogeneous note types exist.
- Preserve both `card_id` (scheduling identity) and `note_id` (content identity).
- Do not clone under `C:\Windows\System32`; the first attempt failed with permission denied.
- Windows Documents may be redirected to OneDrive; do not assume paths.
- Opening a new PowerShell may be required after installing CLI tools so PATH refreshes.
- Read success does not validate write-back safety.

## 31. TECHNICAL VALIDATION DECISION LOG — 2026-08-13

**VALIDATED:**

- AnkiConnect local read access.
- Deck-scoped due discovery.
- `cardsInfo` source-field retrieval.
- Read-only `get_due_cards` MCP tool.
- Codex CLI calling the MCP tool and receiving real Anki data.
- Secure MCP Tunnel local daemon/profile reaching ready state.
- Ordinary ChatGPT conversation -> custom app -> Secure MCP Tunnel -> Anki read path.

**BLOCKED / UNVALIDATED:**

- ChatGPT voice-mode invocation of the custom Anki MCP app.
- Any Anki review write-back or content write-back through MCP.
- Automatic persistent/background tunnel startup on a personal computer; manual foreground startup is the validated baseline.

**NEXT DEFAULT TECHNICAL EXPERIMENT:**

Recreate the validated manual setup on a personal computer, then test a ChatGPT voice conversation invoking the tunnel-backed `get_due_cards` tool. Keep all Anki review/content write-back disabled until read-only voice teaching quality is proven.

## 32. CHATGPT APP VALIDATION, TOOL SAFETY METADATA, AND PERSONAL-PC MIGRATION — EXPERIMENT RESULT / LOCKED RECOVERY PLAN

Ordinary ChatGPT acceptance result — VALIDATED 2026-08-13:

A new non-Codex ChatGPT conversation successfully loaded the tunnel-backed custom app `Anki Voice Tutor`, invoked `get_due_cards`, and received the same real local Anki data as the local/Codex tests (`total_due=8`, `returned=5`; card identity matched).

**Tool safety metadata pitfall:** the first ChatGPT tool scan labeled the genuinely read-only tool as WRITE / OPEN WORLD / DESTRUCTIVE because the MCP server did not declare behavioral annotations. The server must explicitly declare `readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`. Tool-definition changes may not appear automatically because ChatGPT can retain a frozen/snapshotted app definition; refresh/re-scan the custom app after changing annotations or schemas.

**UI/product-surface pitfall:** Apps / Plugins / Connectors naming changed during the experiment. Recovery documentation should describe the underlying requirement — create/configure a custom MCP app against the existing Secure MCP Tunnel and scan its tools — rather than rely on one screenshot or legacy label.

**Corporate-machine hard stop:** the original Windows test computer was company-managed and protected by SentinelOne. SentinelOne repeatedly flagged `tunnel-client.exe`; later the company security team contacted the user. Development on that managed machine must stop. Do not bypass, disable, evade, or locally whitelist corporate endpoint security. Continue only on a personal/approved test computer or with explicit IT approval.

**Automatic-start status:** manual foreground tunnel startup is the validated baseline. Automatic startup was not reliably validated and must not be reproduced first on a new computer.

Recovery source of truth: `docs/ANKI_MCP_CONNECTION_RUNBOOK.md` in this repository records the new-computer reproduction sequence, acceptance checks, path problems, secret-rotation lesson, ChatGPT custom-app/Tunnel validation, tool safety annotations, and corporate-security boundary. No API secret is stored in GitHub or the PRD.

## 33. ADAPTIVE LEARNING DEPTH — LIGHTWEIGHT BY DEFAULT, DEEPEN ON DEMAND — LOCKED

The Tutor must not force every knowledge item through a deep understanding/transfer workflow. Doing so would make sessions too slow, increase activation friction, and create an “infinite study” problem where learning becomes harder to start than the underlying material warrants.

**Default policy: lightweight first.**

For ordinary review, the Tutor should ask an atomic question, assess the answer, give the smallest useful correction or confirmation, record the evidence, and move on. Deep explanation, application, case-building, transfer, or counterfactual work is optional rather than a universal mastery gate.

**Depth escalation should be triggered when one or more of the following is true:**

- the learner explicitly says “I don’t understand,” “I can repeat it but I can’t use it,” or asks for more practice;
- the learner repeatedly fails or shows a misconception;
- a missing prerequisite blocks understanding;
- the item is unusually important/high-value for the learner’s real goals;
- the Tutor has strong evidence that shallow recall is insufficient for the target performance.

When deeper learning is appropriate, the Tutor should recommend a small number of context-appropriate learning methods rather than force one fixed sequence. Candidate methods include:

- concrete example;
- analogy;
- learner-generated explanation;
- real personal/work case;
- case-study framing (context → decision → action → outcome/impact);
- counterfactual thinking;
- comparison/counterexample;
- near-transfer or application test.

The Tutor should choose the least costly method likely to repair the actual gap, and return to lightweight review once the gap is sufficiently repaired.

**Learner-state distinction:** knowing/recalling a concept but not yet being able to apply it is a legitimate intermediate state. It should not be mislabeled as full mastery, but it also should not automatically trigger a long remediation sequence unless the learner’s goal or evidence warrants deeper work.

**Value-based skipping is not fatigue.** If the learner says a card is not useful, not worth learning, or should be skipped/suspended/deprioritized, the Tutor should treat that as a content-value decision rather than infer tiredness or repeatedly ask whether the learner wants to stop the whole session.

**Experiment finding — 2026-08-14:** case-study and counterfactual practice substantially improved application of a simple framework, but the learner explicitly identified that making this mandatory for every card would dramatically increase startup cost and prolong sessions. Therefore deep transfer is a targeted repair/enrichment strategy, not the default review depth.
