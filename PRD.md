# AI Voice Oral Mastery Coach — Living PRD

**Version:** v1.5

**Status:** Discovery / Product Core Validation

**Last updated:** 2026-08-17

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

Inner Tutor Loop:

Question / scenario → learner speaks → diagnose → minimal intervention → learner retries → reconstruct / re-explain → example or transfer test → mastery evidence.

Outer Memory Loop:

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

Layer A — Immutable Source

Preserve the original captured/source content and provenance. AI must not silently rewrite the historical source.

Layer B — Canonical Learning Target

The current prompt and answer/reference used for retrieval. Changes to these require stronger evidence because they alter what is being tested.

Layer C — Tutor Learning Overlay

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

A. Item-level state (per Anki card / atomic unit)

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

B. Concept-level state (across cards)

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

For the first real ChatGPT-based prototype, Google Sheets will act as a Teacher Feed / integration bus between capture tools, the Tutor, and later the Anki Bridge.

Rationale: the existing web-note capture workflow already supports Google Sheets. This allows the learner to continue capturing material with very low friction while giving the Tutor a structured source it can inspect without requiring direct Anki access in the first prototype.

Default prototype flow:

Web notes / WuCai -> Google Sheet Teacher Feed -> ChatGPT Tutor -> Tutor learning events / learner-state updates -> Google Sheet -> later Anki Bridge -> Anki/FSRS.

The Google Sheet is teacher-facing infrastructure. The learner should not need to open or maintain it during normal study.

The Tutor should use the Teacher Feed to:

- identify new material waiting to be learned;

- read source text, tags, links, and provenance;

- derive Tutor Units and oral questions;

- record item-level learning evidence and learner insights;

- surface prerequisite gaps and weak concepts;

- choose what to teach next together with Anki due state when available.

MVP design principle: do not require a direct ChatGPT-to-Anki connection before validating the teaching loop. Google Sheets can decouple capture, tutoring, and Anki synchronization so each component can be tested independently.

Recommended minimal shared identifiers: source_item_id, anki_note_id when available, anki_card_id when available, source_text, source_url, tags, capture_time, tutor_status, and sync_status. The detailed learner model may live in separate tabs or a Tutor-owned store rather than bloating the raw capture row.

Boundary: Google Sheets is an integration surface, not the ultimate source of truth for Anki scheduling. Anki/FSRS remains the scheduling source of truth once a card is linked. The Tutor remains the source of truth for teaching-state evidence and learner-model interpretation.

Superseded decision note — 2026-08-13:

Google Sheets remains potentially useful as a capture source / Teacher Feed because the web-note workflow already supports it, but it is no longer the preferred bridge between the AI Tutor and Anki. A direct local Anki integration through AnkiConnect + MCP was successfully validated. The preferred direction is now: capture tools may feed Anki, while the Tutor reads Anki directly when technically available. Avoid unnecessary Google Drive/Sheet round-tripping between Tutor and Anki.

## 29. DIRECT LOCAL ANKI ACCESS — EXPERIMENT RESULT, VALIDATED 2026-08-13

Validation objective:

Prove that an OpenAI agent can read real due-card data from the learner’s desktop Anki without the learner manually copying card content into the conversation.

Result: VALIDATED first through Codex CLI and then through an ordinary non-Codex ChatGPT conversation using a custom MCP app over OpenAI Secure MCP Tunnel. ChatGPT itself successfully invoked `get_due_cards` and returned real local Anki data from `000-WuCai Inbox` (`total_due=8`, `returned=5`).

Updated boundary: ordinary ChatGPT text-chat attachment is now VALIDATED. The remaining product-surface question is whether the desired ChatGPT voice mode can invoke the same custom MCP app reliably during a hands-free tutoring session. Voice-mode MCP use remains NOT YET VALIDATED.

Validated data path:

Validated ordinary-ChatGPT path: ChatGPT conversation -> custom app `Anki Voice Tutor` -> OpenAI Secure MCP Tunnel -> local `tunnel-client` -> stdio `anki_mcp_server.py` -> AnkiConnect at `http://127.0.0.1:8765` -> desktop Anki -> real card data returned to ChatGPT. Codex direct MCP remains a useful diagnostic path but is not the intended learner-facing surface.

Secure Tunnel path also reached local readiness:

OpenAI Secure MCP Tunnel control plane -> local `tunnel-client` daemon -> stdio `anki_mcp_server.py`; local `http://127.0.0.1:8080/readyz` returned `ready`. A later browser-based setup successfully registered the tunnel-backed custom app in ordinary ChatGPT and a real ChatGPT tool call returned local Anki data. This upgrades the tunnel path from local-readiness-only to end-to-end ChatGPT read validation.

Key conclusion:

Direct ChatGPT-to-Anki read access is technically feasible and end-to-end text-chat access has been demonstrated. The user does not need to copy/paste Anki cards for the Tutor. Remaining work is voice-mode tool invocation, safe review/content write-back, learner-model persistence, tutoring quality, and convenient personal-computer startup — not basic Anki read feasibility.

## 30. REPRODUCIBLE SETUP RUNBOOK — NEW COMPUTER / RECOVERY

Purpose:

This runbook must be sufficient to recreate the validated read-only integration on another Windows computer. Do not rely on conversational memory.

A. Prerequisites

1. Install desktop Anki.

2. Install and enable the AnkiConnect add-on.

3. Keep desktop Anki open while testing or tutoring.

4. Confirm Python is installed and available as `python`.

5. Clone `yulicccccc/voice-mastery-tutor`.

6. Install dependencies from `requirements.txt`.

7. Optional for OpenAI-agent validation: install Codex CLI.

8. Optional for ChatGPT Tunnel experiments: create an OpenAI Platform Secure MCP Tunnel and install the official `tunnel-client` binary.

B. Verify AnkiConnect before MCP

With Anki open, browse to `http://127.0.0.1:8765`.

Expected response resembles `{"apiVersion":"AnkiConnect v.6"}`.

Then test due-card discovery. A broad `is:due` query returned 1909 cards in the first experiment and immediately exposed a queue-size problem. Scope tests to a deck, e.g. `deck:"000-WuCai Inbox" is:due`.

Important semantic observation: the Anki UI showed 4 Learn + 4 Due for `000-WuCai Inbox`, while `is:due` returned 8 cards. Tutor logic must distinguish learning/relearning cards from ordinary review-due cards instead of assuming `is:due` means only the Due column.

C. Inspect card structure before designing the Teacher API

Use AnkiConnect `findCards`, then `cardsInfo`.

Observed issues:

- `question` and `answer` can contain large rendered HTML/CSS/style blocks and are noisy teacher inputs.

- `fields` contains cleaner source note fields and should be preferred.

- Do not hard-code `Front = question` and `Back = answer`.

- Multiple note models exist. The validated deck contained at least `Basic-53d93` and `Cloze-WuCai`.

- A Basic note’s `Back` may contain source/title metadata rather than an answer.

- Scheduling identity is card-level (`card_id`), while note content is note-level (`note_id`). Preserve both.

D. Current read-only MCP implementation

Repository file: `anki_mcp_server.py`.

Implementation characteristics:

- Python FastMCP server using stdio transport.

- Default AnkiConnect endpoint `http://127.0.0.1:8765`.

- Default deck `000-WuCai Inbox`.

- One teacher-facing tool: `get_due_cards(deck, limit)`.

- Internally calls AnkiConnect `findCards`, then `cardsInfo`.

- Returns card_id, note_id, deck, model, raw fields, due, queue, type, reps, lapses, interval, factor, left, modified, next_reviews.

- Omits rendered `question` / `answer` HTML noise.

- Read-only: no note mutation, review answer, FSRS mutation, due-date change, or scheduling write.

- Current per-call cap: 100 cards.

Associated repository files: `requirements.txt`, `smoke_test_anki.py`, `README.md`.

E. Clone and local smoke test on Windows

Do NOT clone into `C:\Windows\System32`; the first attempt failed with permission denied. Use a normal user-writable folder.

Example:

`cd $HOME\Documents`

`git clone https://github.com/yulicccccc/voice-mastery-tutor.git`

`cd .\voice-mastery-tutor`

`python -m pip install -r requirements.txt`

`python .\smoke_test_anki.py`

Validated smoke-test result on 2026-08-13:

- deck=`000-WuCai Inbox`

- total_due=8

- returned=5

- real card_id / note_id / model / field names returned.

A Pydantic `IncompleteFieldDefinitionWarning` appeared but did not prevent the read test from succeeding; treat it as cleanup, not a blocker.

F. Codex CLI direct validation path — CURRENTLY THE MOST RELIABLE REPRODUCTION PATH

Install Codex CLI using the current official OpenAI Windows installer. After installation, open a NEW PowerShell window so PATH refreshes, then confirm `codex --version`.

Register the local MCP globally:

`codex mcp add anki-local -- python C:/Users/<WINDOWS_USER>/Documents/voice-mastery-tutor/anki_mcp_server.py`

Start Codex with `codex`.

Inside Codex, run `/mcp`.

Expected evidence:

- server `anki-local`

- tool `get_due_cards`

Then ask Codex to call the tool, for example:

`Use the anki-local MCP tool get_due_cards with deck="000-WuCai Inbox" and limit=5. Return the card_id, note_id, model, and fields for each card.`

Validated result:

Codex called `anki-local.get_due_cards` and returned five real cards from the local Anki collection. This is the acceptance test for read-only feasibility.

Note: Codex startup displayed `MCP startup interrupted` in one run, but `/mcp` still listed `anki-local` and the actual tool call succeeded. Runtime tool-call evidence outranks a generic startup warning when judging whether the integration works.

G. Secure MCP Tunnel setup — VALIDATED END TO END FOR ORDINARY CHATGPT READ

OpenAI Platform tunnel created during experiment:

Name: `Anki Voice Mastery Tunnel`.

Architecture:

ChatGPT/OpenAI control plane -> Secure MCP Tunnel -> local tunnel-client -> stdio MCP server -> AnkiConnect -> Anki.

Runtime credential policy:

- create a Restricted runtime credential with only the minimum Tunnel permissions required by the current OpenAI setup;

- never paste secrets into chat, screenshots, source control, or permanent shell history;

- if exposed, revoke immediately and replace.

Create a local tunnel profile using `sample_mcp_stdio_local`, the tunnel ID from OpenAI Platform, and an MCP command pointing to `anki_mcp_server.py`.

Important Windows path pitfall: the first MCP command used Windows backslashes and the tunnel preflight interpreted/stripped them, producing a nonexistent path. Switching the MCP script path to forward slashes fixed the issue.

Observed profile location:

`C:\Users\<WINDOWS_USER>\AppData\Roaming\tunnel-client\anki-local.yaml`

Preflight:

`tunnel-client doctor --profile anki-local --explain`

Validated result: `RESULT ok`.

Run foreground daemon:

`tunnel-client run --profile anki-local`

Keep this terminal open.

Validated log included `tunnel-client started`.

Validated local readiness endpoint:

`http://127.0.0.1:8080/readyz`

Response: `ready`.

H. Ordinary ChatGPT-conversation connection status — VALIDATED; VOICE STILL UNVALIDATED

Developer mode was enabled in ChatGPT. The visible UI was confusing because Apps/Plugins/Connectors naming was in transition and the obvious settings pages did not initially show a custom MCP entry. A later browser-based setup successfully used the existing `Anki Voice Mastery Tunnel` to configure a custom ChatGPT app named `Anki Voice Tutor`, scan its MCP tools, and invoke `get_due_cards` from a new ordinary ChatGPT conversation.

Therefore:

- local Anki read path = VALIDATED;

- Codex -> local MCP -> Anki = VALIDATED;

- Secure tunnel daemon -> local MCP readiness = VALIDATED;

- ordinary ChatGPT conversation -> custom app -> Secure MCP Tunnel -> Anki = VALIDATED for read-only text chat.

The ordinary ChatGPT read acceptance criterion was met by a real tool call returning local Anki data. Do not extend that claim to voice mode or Anki write-back until those are separately tested.

I. Corporate endpoint-security pitfall

The Windows test machine runs SentinelOne. It repeatedly flagged `tunnel-client.exe` as suspicious even though the downloaded archive matched the official OpenAI release hash.

Policy:

- do not bypass, disable, or evade corporate endpoint security;

- verify official package hashes;

- if the security product blocks the workflow, use an approved personal/test machine or obtain IT approval.

Observed effect:

`tunnel-client` could run and reach `/readyz`, but `tunnel-client codex plugin install` failed with `tunnel-client binary is not executable`, plausibly related to endpoint-security interference. This plugin path is therefore NOT a reliable reproduction method on the corporate PC.

J. Other pitfalls discovered

1. `C:\Windows\System32` clone attempt failed because the directory was not user-writable. Use user Documents/projects.

2. Windows Documents may be redirected to OneDrive. Do not assume `$HOME\Documents` contains downloaded tools; discover the actual path when needed.

3. Verify downloaded binaries by hashing the original release archive when the release publishes archive checksums.

4. A runtime credential was accidentally exposed once in a screenshot. It was revoked and replaced. Secret-handling is an explicit acceptance criterion.

5. After installing Codex CLI, an already-open PowerShell did not recognize `codex`; opening a new terminal refreshed PATH.

6. An unrelated pre-existing `cloudflare-api` MCP had expired OAuth and emitted startup warnings. Do not attribute unrelated MCP failures to `anki-local`.

7. Large global due counts make raw `is:due` unusable as the Tutor queue. Tutor must scope/select using deck, learner state, prerequisites, priorities, and session budget.

8. Successful read access is not evidence that review write-back is safe. Write operations remain a separate future experiment.

K. Acceptance criteria for recreating the validated state

The setup is considered successfully recreated only when all of the following are observed:

1. AnkiConnect root responds while Anki is open.

2. `smoke_test_anki.py` returns real cards from `000-WuCai Inbox`.

3. Codex `/mcp` lists `anki-local` and `get_due_cards`.

4. A real `get_due_cards(deck="000-WuCai Inbox", limit=5)` call returns actual local Anki card data.

Optional Tunnel criterion:

5. tunnel-client `doctor` returns ok and `/readyz` returns `ready`.

For recreation on a new computer, add a mandatory acceptance step: ordinary ChatGPT must attach the tunnel-backed custom app and execute `get_due_cards` against real local Anki data. A separate later acceptance step is required for ChatGPT voice mode.

## 31. TECHNICAL VALIDATION DECISION LOG — 2026-08-13

VALIDATED:

- AnkiConnect local read access.

- Deck-scoped due discovery.

- `cardsInfo` source-field retrieval.

- Read-only `get_due_cards` MCP tool.

- Codex CLI calling the MCP tool and receiving real Anki data.

- Secure MCP Tunnel local daemon/profile reaching ready state.

BLOCKED / UNVALIDATED:

- ChatGPT voice-mode invocation of the custom Anki MCP app.

- Codex tunnel plugin installation on the corporate SentinelOne-managed computer.

- Any Anki review write-back or content write-back through MCP.

- Automatic persistent/background tunnel startup on a personal computer; manual foreground startup is the validated baseline.

NEXT DEFAULT TECHNICAL EXPERIMENT:

Recreate the validated manual setup on a personal computer, then test the real target surface: a ChatGPT voice conversation invoking the tunnel-backed `get_due_cards` tool. If voice-tool invocation succeeds, immediately run the first end-to-end teacher interaction over returned cards. Keep all Anki review/content write-back disabled until read-only voice teaching quality is proven.

## 32. CHATGPT APP VALIDATION, TOOL SAFETY METADATA, AND PERSONAL-PC MIGRATION — EXPERIMENT RESULT / LOCKED RECOVERY PLAN

Ordinary ChatGPT acceptance result — VALIDATED 2026-08-13:

A new non-Codex ChatGPT conversation successfully loaded the tunnel-backed custom app `Anki Voice Tutor`, invoked `get_due_cards`, and received the same real local Anki data as the local/Codex tests (`total_due=8`, `returned=5`; card identity matched). This is the required proof that the actual ChatGPT product can read desktop Anki through the Secure MCP Tunnel.

Tool safety metadata pitfall:

The first ChatGPT tool scan labeled the genuinely read-only tool as WRITE / OPEN WORLD / DESTRUCTIVE because the MCP server did not declare behavioral annotations. The server must explicitly declare `readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`. Tool-definition changes may not appear automatically because ChatGPT can retain a frozen/snapshotted app definition; refresh/re-scan the custom app after changing annotations or schemas.

UI/product-surface pitfall:

Apps / Plugins / Connectors naming changed during the experiment. The obvious Plugins/Developer-mode settings pages initially did not expose a clear custom-MCP creation control, even though the feature was ultimately usable. Recovery documentation must describe the underlying requirement — create/configure a custom MCP app against the existing Secure MCP Tunnel and scan its tools — rather than relying only on one screenshot or legacy label.

Corporate-machine hard stop:

The original Windows test computer was company-managed and protected by SentinelOne. SentinelOne repeatedly flagged `tunnel-client.exe`; later the company security team contacted the user. Development on that managed machine must stop. Do not bypass, disable, evade, or locally whitelist corporate endpoint security. Continue this integration only on a personal/approved test computer or with explicit IT approval.

Automatic-start status:

Manual foreground tunnel startup is the validated baseline. An attempt to make the tunnel persist automatically on the corporate machine was not reliably validated and occurred near the security escalation. Automatic startup is therefore NOT a current requirement and must not be reproduced first on the new computer. Recreate the manual path first; add persistence only later as a separate convenience experiment.

Recovery source of truth:

The GitHub repository `yulicccccc/voice-mastery-tutor` now contains `docs/ANKI_MCP_CONNECTION_RUNBOOK.md`, which records the new-computer reproduction sequence, acceptance checks, Windows/OneDrive/path problems, secret-rotation lesson, ChatGPT custom-app/Tunnel validation, tool safety annotations, and corporate-security boundary. No API secret is stored in GitHub or this PRD.

New-computer default sequence:

Anki + AnkiConnect -> clone repo -> install Python deps -> run local smoke test -> create/reuse Secure MCP Tunnel tied to the correct ChatGPT workspace -> create restricted runtime credential -> create `anki-local` stdio tunnel profile with forward-slash script path -> `doctor` -> foreground `run` -> `/readyz` = ready -> configure/refresh `Anki Voice Tutor` custom ChatGPT app -> actual normal ChatGPT `get_due_cards` call -> only then test ChatGPT voice-mode invocation.

Next product-critical unknown:

Text ChatGPT -> Anki is proven. The next highest-value technical test is whether ChatGPT voice mode can invoke the same custom app while preserving the hands-free tutoring loop. Write-back remains disabled and separate.

## 33. ADAPTIVE LEARNING DEPTH — LIGHTWEIGHT BY DEFAULT, DEEPEN ON DEMAND — LOCKED

Core principle: not every knowledge item deserves the same learning depth. The Tutor must protect momentum and low activation energy. Deep learning techniques are tools to use selectively, not mandatory gates for every card.

Default behavior — lightweight review:

- Ask one orally answerable retrieval/performance question.

- If the learner answers adequately and does not signal confusion or need for deeper practice, record the available evidence and move on.

- Do not automatically require explanation, personal example, transfer, case study, or counterfactual practice for every item.

- Prefer the smallest sufficient teaching intervention. The amount of time spent should be proportional to the item’s value and the learner’s actual difficulty.

Triggers for deeper teaching:

- the learner explicitly says “I don’t understand,” “I know the framework but can’t apply it,” “I still need practice,” or equivalent;

- repeated retrieval failure, recurring misconception, or missing prerequisite is detected;

- the learner explicitly marks the item as important/high-value and wants stronger mastery;

- the Tutor has evidence that apparent recall is shallow and the gap materially matters for the target performance.

When a deeper branch is triggered, the Tutor should diagnose the gap first, then recommend a small set of suitable learning methods rather than forcing one universal workflow. Candidate interventions include:

- simpler explanation of the mechanism / why;

- concrete example or analogy;

- compare / contrast or counterexample;

- learner reconstruction in their own words;

- worked example;

- application to a familiar personal/work situation;

- case-study framing such as context → decision → action → outcome/impact;

- counterfactual thinking (“what would likely have happened if X had not changed?”) to expose cause-and-effect;

- near-transfer or novel-transfer question;

- progressive retrieval hints.

The Tutor should choose or recommend only the few interventions most likely to fix the detected gap. Once sufficient evidence is obtained, return to the normal lightweight review loop. Do not create an endless deep-learning branch by default.

Important mastery distinction:

Knowing a framework or definition is not equivalent to being able to apply it. However, application evidence is not required for every card. If the learner can recall a concept but explicitly reports that application is still weak, represent this as an intermediate state such as “concept understood / application not yet fluent” or “in progress,” rather than falsely marking full mastery.

Learner control / value override:

If the learner says a card is not useful or no longer worth studying, the Tutor should not interpret this as fatigue or repeatedly challenge the decision. Treat usefulness/value as a separate dimension from mastery. The learner may skip, suspend, deprioritize, or retire low-value material. The Tutor can record the reason and continue immediately to the next item.

Experiment finding — 2026-08-14:

During a live review, the learner could recall the case-study framework but noticed that applying it to a real contamination incident was substantially harder than remembering the framework. Guided application and counterfactual thinking helped. The learner then identified an equally important product risk: forcing this depth on every card would make sessions too slow and increase startup friction. Product decision: keep deep application techniques available and adaptive, but preserve lightweight review as the default.

## 34. CONVERSATION-INDEPENDENT LEARNER MEMORY — CONVERSATION IS THE CLASSROOM, NOT THE MEMORY — LOCKED

Core principle: the Tutor must not depend on one indefinitely growing ChatGPT conversation to remember the learner. Long-running conversation context is temporary, lossy, model-dependent, and increasingly expensive/complex. The persistent learner state must live outside the conversation in Tutor-owned structured storage.

Canonical principle: Conversation is the classroom, not the memory.

A tutoring conversation is a disposable session surface. The learner should be able to end a session, open a brand-new ChatGPT conversation later, say “start reviewing,” and continue from the relevant learning state without requiring access to the old transcript.

Persistent memory layers:

1. Long-term Learner Model — durable per-item and per-concept state, including independent retrieval history, prompted recall, understanding gaps, recurring misconceptions, known-but-not-transferable state, mastery evidence, low-value/skip preference, explanations that worked, personal associations, and prerequisite gaps.

2. Recent Learning Summary — a compact, durable summary of the most relevant recent state for each item/concept, including what blocked the learner, what intervention worked, what remains unresolved, and the recommended next teaching target.

3. Current Session Buffer — only the short-lived conversational context needed for the present interaction. Most raw turns should not be required after the session ends.

The full historical transcript is not the learner model. Raw dialogue may be retained for debugging or optional audit, but future teaching must not require replaying or reloading an entire old ChatGPT thread.

Session-resume contract:

New conversation -> read due/appropriate Anki material -> load relevant Learner Model + recent learning summary -> reconstruct only the minimum teaching context -> continue tutoring.

The Tutor should retrieve learner memory selectively. It should not inject the full learner history into every model call. For the current card/concept, load only the state and recent evidence needed to make the next pedagogical decision.

Durability / portability requirement: the persistent learner model must be independent of a specific ChatGPT thread and, where practical, independent of a specific foundation model. Replacing the underlying AI model should not erase the teacher’s knowledge of the learner.

Data minimization rule: preserve structured learning evidence rather than indiscriminately storing every utterance. Example durable record for a concept may include: knows the framework; struggled with spontaneous application; own-work contamination case helped; case-study framing worked; counterfactual thinking helped; next target is independent application to a new case.

Implementation direction for the MVP: the append-only Tutor event store is the starting source of durable evidence. Add a resume/read path that reconstructs the latest per-card/per-concept learner state and a compact recent summary for a new session. Do not make ChatGPT conversation memory the source of truth.

Acceptance criteria:

- A brand-new ChatGPT conversation can resume study without the old chat transcript.

- The Tutor can recover the latest relevant learner state after process restart.

- The next teaching action materially reflects prior learner evidence when relevant.

- Old raw conversation history is not required to choose the next card or teaching intervention.

- The Tutor loads only relevant memory for the active item/concept rather than the entire history.

- Deleting or losing a ChatGPT thread does not erase durable learner progress.

Product implication: the durable product asset is the evolving Learner Model + learning evidence, not the conversation thread itself. The conversation is an interface for teaching; the learner model is the continuity layer.

Experiment finding — 2026-08-17:

During product reflection, the learner identified that using one ever-growing Anki tutoring conversation would eventually become complex and could still lose or forget earlier context. This exposed a critical architecture boundary: session continuity must come from explicit Tutor persistence, not chat-thread memory. Product decision: make conversations disposable and make learner state resumable across fresh conversations.

## 35. PER-CARD DURABILITY & ANKI REVIEW SYNC TRIGGERS — PERSIST PER CARD; SYNC OPPORTUNISTICALLY — LOCKED

Core principle: the system must not depend on a clean ChatGPT session ending in order to preserve learning or update Anki. A voice/chat session may end abruptly, the user may close the conversation, the network may fail, or the next study session may start in a fresh ChatGPT thread. Therefore the durable transaction boundary is the completed card interaction, not the end of the conversation.

Canonical rule: Persist per card; sync opportunistically; session end is only a checkpoint.

Default conversation/session boundary:

- One study session should normally use one ChatGPT conversation, not one conversation per card.

- A later study session should normally be able to start in a fresh ChatGPT conversation and recover from Tutor-owned learner memory.

- Short interruptions inside the same study session may continue in the same conversation.

Per-card completion contract:

1. Tutor presents a card/Tutor Unit and records the learner’s first independent attempt.

2. Tutor may provide hints, explanation, retry, or deeper teaching as needed.

3. When the Tutor decides the current card interaction is complete, it immediately persists the learner-state evidence locally.

4. If the card produced a legitimate Anki scheduling outcome, create exactly one ReviewEvent for that card interaction and mark it pending until safely applied.

5. Attempt Anki synchronization when the relevant write tool is available and Anki is reachable; otherwise leave the ReviewEvent pending and continue the session.

6. Move to the next card without requiring a global session-end action.

Important rating rule: the Anki review rating is derived from the first unaided retrieval attempt, not from the learner’s eventual success after tutoring. A failed first attempt that is later repaired may still map to Again while Tutor learner state records understanding repaired, prompted recall, or other post-teaching evidence. Tutor retries must not create multiple Anki reviews for the same card interaction.

No-answer / value-skip rule: if the learner marks a card low-value, not worth learning, or skips it without making a genuine retrieval attempt, do not fabricate an Anki review result. Record the value/skip decision in Tutor state. Any future Anki suspend/deprioritize/content action is a separate explicit write-back policy.

Session-start behavior:

- Check for pending ReviewEvents from prior sessions.

- If safe Anki write-back is enabled and Anki is reachable, attempt to flush eligible pending reviews before or alongside building the new queue.

- Load due/appropriate Anki material plus relevant Tutor learner context.

- Do not require the previous ChatGPT transcript.

Session-end behavior:

- If the learner explicitly ends the session, optionally perform a final pending-sync attempt and write a compact session checkpoint/summary.

- Session end is not the durability boundary. Already-completed cards must remain safely persisted even if no explicit end event occurs.

MVP tool responsibility model:

- get_due_cards / get_daily_queue: read Anki scheduling/material state.

- get_tutor_context: read compact Tutor learner memory for the active card/concept.

- decide_tutor_next_step: determine teaching state/action and persist local Tutor evidence as designed.

- record_review_result (or equivalent): create a durable local ReviewEvent after a card is complete; this does not directly mutate FSRS fields.

- sync_pending_reviews: apply eligible pending ReviewEvents through Anki’s normal scheduler, with idempotency and conflict protection.

ChatGPT’s role is to trigger these tools at the correct pedagogical moments. ChatGPT is not the source of truth for sync status. The local Tutor/ReviewEvent store must know whether an event is pending, applied, conflicted, skipped, or failed.

Anki write-back safety requirements:

- Never directly edit due date, interval, stability, difficulty, or other FSRS internals.

- Submit review outcomes through Anki’s scheduler/approved review mechanism.

- Each ReviewEvent requires a stable event_id/idempotency key so retries cannot double-review a card.

- Preserve the card/scheduler snapshot used when the interaction began; if the card was independently reviewed elsewhere before sync, do not silently overwrite. Mark conflict and surface it for later handling.

- A failed network/Anki/tool call must leave the event pending rather than lose it or assume success.

- Actual write success must be confirmed by the tool result before an event is marked applied.

Content evolution remains separate from review scheduling. Learner insights, examples, mistakes, and teaching notes may create Tutor Overlay/CardUpdateEvent records, but they must not automatically rewrite Anki Front/Back merely because a card interaction completed. Review synchronization and note-content synchronization are separate pipelines with different safety thresholds.

MVP implementation sequence:

1. Durable local ReviewEvent queue and state transitions.

2. Dry-run/mock sync tests, including duplicate-call and conflict scenarios.

3. Real local Anki scheduler write-back test on an approved personal/test machine.

4. Ordinary ChatGPT custom-app write invocation test.

5. Separate ChatGPT voice-mode write invocation test.

6. Keep Anki content write-back disabled until review write-back is proven safe.

Acceptance criteria:

- Completing a card persists learner evidence immediately before the next card is started.

- Force-closing the ChatGPT conversation after a completed card does not lose that card’s Tutor state or pending ReviewEvent.

- A new process/new ChatGPT conversation can discover and safely sync prior pending ReviewEvents without the old transcript.

- Repeating sync_pending_reviews after an already-applied event does not create a second Anki review.

- If Anki is offline, the event remains pending and later applies once Anki is available.

- If a card was reviewed elsewhere after the captured snapshot, the event is not silently applied over the newer review.

- Failed first attempt + successful tutoring produces the correct separation between Anki scheduling outcome and Tutor mastery evidence.

- Low-value skip without a retrieval attempt does not fabricate an Anki review.

- Session-end handling is optional for durability; abrupt termination must be safe.

Experiment finding — 2026-08-17:

Product reflection exposed that a session-end-only sync model is fragile because ChatGPT conversations may be disposable and can terminate without a reliable final callback. The preferred architecture is therefore card-level durable event creation plus pending, retryable Anki synchronization. The ChatGPT conversation triggers the workflow, but durable Tutor state and Anki synchronization state live outside the conversation. Real ChatGPT/voice write invocation remains a separate technical validation and must not be assumed from read-only success.

## 36. CONTROLLED REAL ANKI SCHEDULER WRITE-BACK — GOOD PATH VALIDATED 2026-08-17 — EXPERIMENT RESULT

Validation scope:

A single disposable test card in deck `999-AI-Tutor-Writeback-Test` was used to validate the real local scheduler write-back path. This was a controlled one-card experiment, not production or batch enablement. No real learning card was modified, Anki sync was not triggered, and the feature flag was disabled again after the experiment.

Validated path:

Tutor ReviewEvent -> durable pending queue -> `sync_pending_reviews(dry_run=false)` -> AnkiConnect `answerCards` -> Anki scheduler -> confirmed tool success -> ReviewEvent `applied`.

Test ReviewEvent:

- event_id: `review_9c2e2fd7b1e4bcb1bbd55953587625f5`;

- first_attempt_result: succeeded;

- mapped_anki_rating: Good;

- tutor_state: independent_recall;

- hints_used: 0;

- initial sync_status: pending.

Actual AnkiConnect write:

- action: `answerCards`;

- cardId: `1786977384810`;

- ease: `3` (Good);

- AnkiConnect response: `[true]`.

Observed scheduler change:

Before review the disposable card was new (`queue=0`, `type=0`, `reps=0`). After the confirmed Good review, Anki moved it into the learning queue (`queue=1`, `type=1`, `reps=1`, `left=2`) and changed its scheduler-managed due/modified values. The integration did not directly set due, interval, stability, difficulty, or FSRS internals.

Confirmation rule — VALIDATED:

The ReviewEvent changed from `pending` to `applied` only after AnkiConnect returned confirmed success. Final event state was `applied`, `sync_attempts=1`, `last_error=null`.

Duplicate-sync protection — VALIDATED IN THIS CONTROLLED CASE:

Immediately repeating `sync_pending_reviews(dry_run=false)` returned `pending_found=0`. `answerCards` was not called a second time, `reps` remained 1, and scheduler state did not change again. Total real `answerCards` calls for the experiment: exactly 1.

Feature-flag safety — VALIDATED:

Real write-back required explicit enablement. After the experiment, `ANKI_REVIEW_WRITEBACK_ENABLED` was removed/disabled and a fresh process read the effective setting as false. Default behavior therefore remains no real Anki review mutation.

AnkiConnect implementation finding:

In the tested environment, Anki 25.09 + AnkiConnect API v6 exposes `answerCards`, whose implementation calls Anki's scheduler `answerCard(card, ease)`. Good maps to ease 3 and Again maps to ease 1. `guiAnswerCard` also exists but depends on Anki GUI reviewer state and is not appropriate for the background ReviewEvent queue.

Known limitation / remaining risk:

AnkiConnect `answerCards` does not accept an idempotency key and does not provide an atomic operation combining scheduler-snapshot comparison with the answer. The Tutor queue can prevent ordinary duplicate retries and can detect post-write snapshot changes, but a small race window remains between precheck and actual scheduler answer. Do not work around this by editing Anki's database or FSRS fields directly.

Test-environment implementation note:

The installed standard-looking Basic note type was actually named `Basic-53d93`, not exactly `Basic`. Test/setup code must not assume the note type name is literally `Basic`; discovery should use the installed note types rather than hard-code one canonical name.

Validation boundary:

This experiment validates one controlled local Good scheduler write-back and duplicate protection after confirmed success. It does NOT yet validate:

- Again write-back on a disposable card;

- batch or production review write-back;

- concurrent multi-client safety under real use;

- AnkiWeb sync behavior after Tutor write-back;

- ordinary ChatGPT custom-app invocation of the write tools;

- ChatGPT voice-mode invocation of the write tools;

- Anki note/content write-back.

Next controlled experiment:

Use one new disposable test card to validate the Again path: first unaided retrieval fails -> one ReviewEvent mapped to Again -> AnkiConnect `answerCards` with ease 1 -> scheduler state changes -> event becomes applied only after confirmed success -> repeated sync produces no second review. Keep all real learning cards out of scope and disable the write-back feature flag immediately after the test.

Product conclusion:

The core review-write architecture has crossed an important feasibility threshold: safe local event persistence, one real scheduler-mediated Good review, confirmed applied-state transition, and no duplicate review on immediate retry have all been demonstrated. The remaining question is no longer simply whether Anki can be written; it is whether the same safety properties hold across failure outcomes, fresh ChatGPT sessions, voice-triggered tool calls, and sustained real-world use.
