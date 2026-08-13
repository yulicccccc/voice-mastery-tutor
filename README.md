# Voice Mastery Tutor

A voice-first AI mastery tutor. This repository is currently in product-core validation.

## MCP technical validation: ChatGPT -> Anki

The first integration is deliberately read-only:

```text
ChatGPT -> Secure MCP Tunnel -> local MCP server -> AnkiConnect -> Anki
```

The MCP server exposes one tool:

- `get_due_cards(deck="000-WuCai Inbox", limit=20)` — returns teacher-facing note fields plus card scheduling metadata. It intentionally omits Anki's rendered `question`/`answer` HTML because source note fields are cleaner and more useful for tutoring.

### 1. Requirements

- Desktop Anki running
- AnkiConnect installed and listening on `http://127.0.0.1:8765`
- Python 3.11+ recommended

### 2. Windows setup

```powershell
git clone https://github.com/yulicccccc/voice-mastery-tutor.git
cd voice-mastery-tutor
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 3. Smoke-test the real Anki connection

Keep Anki open, then run:

```powershell
python smoke_test_anki.py
```

Success means it prints the due count and up to five card IDs/field names from `000-WuCai Inbox`.

### 4. MCP server

The server uses MCP stdio transport by default:

```powershell
python anki_mcp_server.py
```

It should wait silently for an MCP client. For local inspection, use the MCP Inspector:

```powershell
npx -y @modelcontextprotocol/inspector@latest
```

Then configure a stdio server with command `python` and argument `anki_mcp_server.py`, and call `get_due_cards`.

### 5. Connect to ChatGPT

For a server running on a developer machine, ChatGPT cannot connect directly to localhost. Use OpenAI Secure MCP Tunnel and point the tunnel at this stdio command. Keep the tunnel client running while testing the developer-mode app.

MVP acceptance test:

> In ChatGPT, ask to start reviewing `000-WuCai Inbox`; ChatGPT invokes `get_due_cards` and receives current Anki material without copy/paste.

## Safety boundary for this milestone

This version is **read-only**. It does not submit Anki reviews, edit note fields, or manipulate FSRS scheduling state.

## Product documentation

See [PRD.md](./PRD.md). The Google Drive Living PRD remains the product source of truth during discovery.
