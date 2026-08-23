# Voice Mastery Tutor

A voice-first AI mastery tutor. This repository is currently in product-core validation.

## Technical validation status

The read-only Anki bridge has now been validated through an **ordinary ChatGPT conversation**, not only Codex:

```text
ChatGPT
  -> custom MCP app (Anki Voice Tutor)
  -> OpenAI Secure MCP Tunnel
  -> local stdio MCP server
  -> AnkiConnect
  -> desktop Anki
```

On 2026-08-13 a normal ChatGPT conversation invoked `get_due_cards` and returned the same real local Anki data seen by the local smoke test (`total_due=8`, `returned=5`). On 2026-08-17, disposable cards separately validated the local Good and Again review paths through AnkiConnect's scheduler-backed `answerCards` action, including confirmed success and duplicate-sync protection. The Teacher Triage MVP was later validated through a fresh ChatGPT conversation: durable triage state and learner overrides were recovered without reclassifying the candidate batch or creating ReviewEvents.

The current daily path is private GPT Actions -> local Actions API -> Cloudflare Quick Tunnel -> desktop Anki. Still unvalidated: direct Custom Action invocation inside ChatGPT **Voice Mode**, sustained multi-card production review write-back, and all Anki note/content write-back.

## Tutor tools

The bridge exposes narrowly scoped tools:

- `get_due_cards(deck="<deck-name>", limit=20)` — returns teacher-facing note fields plus card scheduling metadata. It intentionally omits Anki's rendered `question`/`answer` HTML because source note fields are cleaner and more useful for tutoring.
- `get_study_session(session_id=None)` — loads the latest Anki-created batch, its selected card content, scheduler snapshots, and durable progress. The Anki dialog supports one or more decks and a user-selected count from 1–20; 5 is only the default.
- `record_triage_results(session_id, results)` — appends one durable batch of Teacher Triage decisions without rewriting the StudySession or changing Anki.
- `get_tutor_context(card_id)` — reconstructs compact card-level teaching memory independently of a ChatGPT transcript.
- `decide_tutor_next_step(...)` — applies the lightweight-first Tutor policy and appends learner evidence to a local JSONL event log without changing Anki.
- `record_review_result(...)` — durably records exactly one ReviewEvent for a completed interaction. First-attempt success maps to Good; first-attempt failure maps to Again. It does not call Anki.
- `sync_pending_reviews(dry_run=true, session_id=None)` — checks pending ReviewEvents and scheduler snapshots, optionally restricted to one batch. Real scheduler calls require both `dry_run=false` and `ANKI_REVIEW_WRITEBACK_ENABLED=true`.

The Anki read tool declares read-only safety hints. Tutor and ReviewEvent tools accurately declare their local writes as non-destructive and closed-world.

The private GPT Actions schema exposes exactly seven operation IDs:

```text
getDueCards
getStudySession
getTutorContext
recordTriageResults
decideTutorNextStep
recordReviewResult
syncPendingReviews
```

Teacher Triage keeps three layers separate:

```text
immutable Candidate StudySession
  -> untriaged cards
  -> Teacher Triage
  -> durable triage_result events
  -> derived active/reference/ignored queues
```

The active treatments are `understand`, `remember`, `apply`, and `practice`.
`reference` and `ignore` remain in the immutable candidate material but are
excluded from active learning. Effective treatment is the latest
`learner_override` when present, otherwise the latest Teacher result. Triage
creates no ReviewEvent and never touches the Anki scheduler. A fresh ChatGPT
conversation recovers the durable triage state instead of classifying the same
cards again.

## Local setup

Requirements:

- Desktop Anki running
- AnkiConnect installed and listening on `http://127.0.0.1:8765`
- Python 3.11+ recommended

Windows setup:

```powershell
git clone https://github.com/yulicccccc/voice-mastery-tutor.git
cd voice-mastery-tutor
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python smoke_test_anki.py
```

Success means the smoke test prints the due count and real card IDs/field names from the configured deck.

## Full ChatGPT ↔ local Anki rebuild guide

See:

**[docs/ANKI_MCP_CONNECTION_RUNBOOK.md](./docs/ANKI_MCP_CONNECTION_RUNBOOK.md)**

The runbook records the complete reproduction path for a new computer:

- AnkiConnect verification
- repository/Python setup
- local MCP smoke test
- optional Codex diagnostic path
- Secure MCP Tunnel setup
- ChatGPT custom MCP app attachment
- real ChatGPT acceptance test
- MCP safety annotations and tool refresh behavior
- Windows/OneDrive/path problems
- secret-handling mistake and rotation rule
- corporate SentinelOne/security intervention
- what is validated vs still unvalidated

Do not reproduce the tunnel work on a managed corporate computer if endpoint-security policy objects. Use an approved personal/test machine instead.

## Safety boundary for this milestone

Anki reads, triage, and `record_review_result` do not mutate Anki. Tutor and triage decisions use a local append-only JSONL store; ReviewEvents use a local SQLite queue with stable event IDs. `sync_pending_reviews` defaults to dry-run, and real review write-back is disabled unless `ANKI_REVIEW_WRITEBACK_ENABLED=true` is explicitly set for the process.

The one approved Good-path experiment used AnkiConnect's normal scheduler mechanism and did not directly edit due dates, intervals, stability, difficulty, FSRS internals, or note content. Production/batch write-back remains disabled.

## Remote study batch prototype

The Anki add-on under `anki_addon/voice_mastery_tutor/` creates an immutable,
local study-session manifest when the user clicks **开始今天的复习**. Every batch
gets a stable `session_id`; earlier manifests are preserved when a new batch is
created. The private GPT can load that batch from a phone while the Mac, local
Actions service, and tunnel remain online. Per-card Tutor events and ReviewEvents
carry the same `session_id`, so later synchronization can be restricted to that
batch. Creating or studying a batch performs zero Anki scheduler writes.

The cross-device phone flow is implemented but still requires a real phone
acceptance test before it is considered validated.

## Product documentation

See [PRD.md](./PRD.md). The Google Drive Living PRD remains the project source of truth during discovery.
