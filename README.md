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

On 2026-08-13 a normal ChatGPT conversation invoked `get_due_cards` and returned the same real local Anki data seen by the local smoke test (`total_due=8`, `returned=5`).

Still unvalidated: ChatGPT **voice-mode** tool invocation and all Anki review/content write-back.

## MCP tool

The bridge exposes one deliberately read-only tool:

- `get_due_cards(deck="000-WuCai Inbox", limit=20)` — returns teacher-facing note fields plus card scheduling metadata. It intentionally omits Anki's rendered `question`/`answer` HTML because source note fields are cleaner and more useful for tutoring.

The tool declares MCP safety hints as read-only, non-destructive, and closed-world so ChatGPT does not have to infer risk from missing metadata.

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

This version is **read-only**. It does not submit Anki reviews, edit note fields, or manipulate FSRS scheduling state.

## Product documentation

See [PRD.md](./PRD.md). The Google Drive Living PRD remains the project source of truth during discovery.
