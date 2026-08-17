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

On 2026-08-13 a normal ChatGPT conversation invoked `get_due_cards` and returned the same real local Anki data seen by the local smoke test (`total_due=8`, `returned=5`). On 2026-08-17, one disposable card separately validated the local Good-review path through AnkiConnect's scheduler-backed `answerCards` action, including confirmed success and duplicate-sync protection.

Still unvalidated: ChatGPT **voice-mode** tool invocation, ChatGPT custom-app invocation of the write tools, Again/batch review write-back, and all Anki note/content write-back.

## MCP tools

The bridge exposes four narrowly scoped tools:

- `get_due_cards(deck="000-WuCai Inbox", limit=20)` — returns teacher-facing note fields plus card scheduling metadata. It intentionally omits Anki's rendered `question`/`answer` HTML because source note fields are cleaner and more useful for tutoring.
- `decide_tutor_next_step(...)` — applies the lightweight-first Tutor policy and appends learner evidence to a local JSONL event log without changing Anki.
- `record_review_result(...)` — durably records exactly one ReviewEvent for a completed interaction. First-attempt success maps to Good; first-attempt failure maps to Again. It does not call Anki.
- `sync_pending_reviews(dry_run=true)` — checks pending ReviewEvents and scheduler snapshots. Real scheduler calls require both `dry_run=false` and `ANKI_REVIEW_WRITEBACK_ENABLED=true`.

The Anki read tool declares read-only safety hints. Tutor and ReviewEvent tools accurately declare their local writes as non-destructive and closed-world.

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

Success means the smoke test prints the due count and real card IDs/field names from `000-WuCai Inbox`.

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

Anki reads and `record_review_result` do not mutate Anki. Tutor decisions use a local append-only JSONL store; ReviewEvents use a local SQLite queue with stable event IDs. `sync_pending_reviews` defaults to dry-run, and real review write-back is disabled unless `ANKI_REVIEW_WRITEBACK_ENABLED=true` is explicitly set for the process.

The one approved Good-path experiment used AnkiConnect's normal scheduler mechanism and did not directly edit due dates, intervals, stability, difficulty, FSRS internals, or note content. Production/batch write-back remains disabled.

## Product documentation

See [PRD.md](./PRD.md). The Google Drive Living PRD remains the project source of truth during discovery.
