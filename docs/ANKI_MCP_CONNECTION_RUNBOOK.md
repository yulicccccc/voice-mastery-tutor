# Anki ↔ OpenAI Agent Connection Runbook

**Validated:** 2026-08-13  
**Scope:** read-only local Anki access  
**Canonical product record:** Living PRD in Google Drive, v1.0

## What was validated

An OpenAI Codex agent successfully called a local MCP tool and received real cards from desktop Anki:

`Codex -> anki-local.get_due_cards -> anki_mcp_server.py -> AnkiConnect -> desktop Anki`

The successful live call returned real `card_id`, `note_id`, note model, and raw note fields from deck `000-WuCai Inbox`.

A Secure MCP Tunnel also reached local ready state, but attaching that tunnel into the current ChatGPT conversation was not completed because the ChatGPT UI/workspace did not expose a custom MCP / Tunnel attachment control. Do not claim ChatGPT-conversation integration until ChatGPT itself executes a real Anki tool call.

## 1. Prerequisites

1. Install desktop Anki.
2. Install and enable AnkiConnect.
3. Keep desktop Anki open during tests.
4. Install Python and make sure `python` works from PowerShell.
5. Clone this repository.
6. Install `requirements.txt`.
7. For direct agent validation, install Codex CLI.
8. For ChatGPT Tunnel experiments, install the official OpenAI `tunnel-client` and create a Secure MCP Tunnel in OpenAI Platform.

## 2. Verify AnkiConnect first

Open in a browser:

```text
http://127.0.0.1:8765
```

Expected response resembles:

```json
{"apiVersion":"AnkiConnect v.6"}
```

Do this before debugging MCP.

## 3. Scope the due-card query

The first broad query, `is:due`, returned 1909 cards. That is technically valid but useless as a Tutor queue.

Use deck scoping for tests, for example:

```text
deck:"000-WuCai Inbox" is:due
```

Important observation from the validated deck:

- Anki UI showed `Learn 4` + `Due 4`.
- `is:due` returned 8 cards.

Therefore Tutor logic must distinguish learning/relearning cards from ordinary review-due cards.

## 4. Prefer raw note fields over rendered question/answer HTML

Use AnkiConnect `findCards`, then `cardsInfo`.

Observed behavior:

- `question` and `answer` can contain large CSS/style/rendered HTML blocks.
- `fields` is much cleaner teacher input.
- Do **not** assume `Front = question` and `Back = answer`.
- At least two note models were observed: `Basic-53d93` and `Cloze-WuCai`.
- Some Basic `Back` fields contain only Source/Title metadata.
- Preserve both `card_id` and `note_id`: scheduling belongs to cards, note content belongs to notes.

## 5. Current MCP implementation

Main file:

```text
anki_mcp_server.py
```

Current design:

- Python FastMCP server.
- stdio MCP transport.
- Default AnkiConnect endpoint: `http://127.0.0.1:8765`.
- Default deck: `000-WuCai Inbox`.
- Tool: `get_due_cards(deck, limit)`.
- Internally calls `findCards`, then `cardsInfo`.
- Returns teacher-relevant raw data, including card/note identity, model, raw fields, due/queue/type/reps/lapses/interval and related scheduler metadata.
- Deliberately omits rendered `question` / `answer` HTML noise.
- Read-only: no note changes, review answers, or FSRS/scheduling mutation.
- Current per-call limit cap: 100 cards.

Related files:

```text
requirements.txt
smoke_test_anki.py
README.md
```

## 6. Clone and smoke-test on Windows

Do **not** clone under `C:\Windows\System32`; that first attempt failed with permission denied.

Example:

```powershell
cd $HOME\Documents
git clone https://github.com/yulicccccc/voice-mastery-tutor.git
cd .\voice-mastery-tutor
python -m pip install -r requirements.txt
python .\smoke_test_anki.py
```

Validated smoke-test output:

```text
deck=000-WuCai Inbox
total_due=8
returned=5
```

Real card IDs, note IDs, models, and field names were returned.

A Pydantic `IncompleteFieldDefinitionWarning` appeared but did not prevent the read test from succeeding. Treat it as cleanup, not a blocker.

## 7. Codex CLI path — validated end to end

After installing Codex CLI, open a **new** PowerShell window so PATH refreshes.

Confirm:

```powershell
codex --version
```

Register the local MCP globally:

```powershell
codex mcp add anki-local -- python C:/Users/<WINDOWS_USER>/Documents/voice-mastery-tutor/anki_mcp_server.py
```

Start Codex:

```powershell
codex
```

Inside Codex:

```text
/mcp
```

Expected evidence:

```text
anki-local
Tools: get_due_cards
```

Then make an actual tool request:

```text
Use the anki-local MCP tool get_due_cards with deck="000-WuCai Inbox" and limit=5. Return the card_id, note_id, model, and fields for each card.
```

Acceptance criterion: Codex must actually call `anki-local.get_due_cards` and return real local Anki card data.

This passed on 2026-08-13.

Note: one Codex launch showed `MCP startup interrupted`, but `/mcp` still listed `anki-local` and the actual tool call succeeded. Real tool-call evidence outranks the generic startup warning.

## 8. Secure MCP Tunnel path — local readiness validated

Validated architecture:

`OpenAI control plane -> Secure MCP Tunnel -> local tunnel-client -> stdio MCP server -> AnkiConnect -> Anki`

Tunnel created in OpenAI Platform:

```text
Name: Anki Voice Mastery Tunnel
```

Use a restricted runtime credential with only the minimum Tunnel permissions required by the current OpenAI setup. Never put credentials in chat, screenshots, Git, or persistent shell history. If exposed, revoke immediately.

Create a local profile using `sample_mcp_stdio_local` and point the MCP command to `anki_mcp_server.py`.

### Windows path pitfall

The first MCP command used Windows backslashes. The tunnel preflight stripped/interpreted them and looked for a broken path like `C:Users...`.

Using forward slashes fixed it:

```text
python C:/Users/<WINDOWS_USER>/Documents/voice-mastery-tutor/anki_mcp_server.py
```

Observed profile location:

```text
C:\Users\<WINDOWS_USER>\AppData\Roaming\tunnel-client\anki-local.yaml
```

Preflight:

```powershell
tunnel-client doctor --profile anki-local --explain
```

Validated result:

```text
RESULT ok
```

Run foreground daemon:

```powershell
tunnel-client run --profile anki-local
```

Keep that terminal open.

Validated readiness endpoint:

```text
http://127.0.0.1:8080/readyz
```

Response:

```text
ready
```

## 9. Current ChatGPT-conversation status

**Not yet validated.**

Developer mode was enabled, but the current ChatGPT UI/workspace showed Plugins and Developer mode without a visible custom MCP / Tunnel creation or attachment control. The legacy connector URL redirected to the Plugins surface.

Current status:

- local Anki read: **VALIDATED**
- Codex -> local MCP -> Anki: **VALIDATED**
- Secure Tunnel daemon -> local MCP readiness: **VALIDATED**
- current ChatGPT conversation -> Tunnel -> Anki: **BLOCKED / UNVALIDATED**

Do not claim ChatGPT integration until ChatGPT itself executes the tool and returns real Anki data.

## 10. Corporate endpoint-security pitfall

The test PC runs SentinelOne. It repeatedly flagged `tunnel-client.exe` as suspicious.

Rules:

- Do not disable, bypass, or evade corporate endpoint security.
- Verify official release hashes.
- If blocked, use an approved personal/test machine or obtain IT approval.

Observed effect:

- `tunnel-client` itself ran and reached `/readyz`.
- `tunnel-client codex plugin install` failed with `tunnel-client binary is not executable`.

Therefore the tunnel Codex-plugin path is not a reliable reproduction method on this corporate PC.

## 11. Other pitfalls from the experiment

1. Cloning under `C:\Windows\System32` failed with permission denied.
2. Windows Documents may be redirected into OneDrive; do not assume downloaded tools are under `$HOME\Documents`.
3. Verify the official release archive hash when the publisher provides checksums.
4. A runtime credential was once exposed in a screenshot; it was revoked and replaced. Secret handling is a formal acceptance criterion.
5. After Codex CLI installation, an already-open PowerShell did not see `codex`; opening a new terminal refreshed PATH.
6. A pre-existing unrelated `cloudflare-api` MCP had expired OAuth and produced startup warnings. Do not attribute unrelated MCP failures to `anki-local`.
7. `is:due` across the whole collection can be enormous; Teacher selection must use deck, learner state, prerequisites, priority, and session budget.
8. Read success does **not** validate write-back safety. Review/content write operations remain a separate experiment.

## 12. Acceptance checklist for a new computer

The read-only setup is successfully recreated only when:

1. AnkiConnect root responds while Anki is open.
2. `smoke_test_anki.py` returns real `000-WuCai Inbox` cards.
3. Codex `/mcp` lists `anki-local` and `get_due_cards`.
4. A real `get_due_cards(deck="000-WuCai Inbox", limit=5)` call returns actual local Anki data.

Optional Tunnel readiness:

5. `tunnel-client doctor` passes and `/readyz` returns `ready`.

ChatGPT integration has a separate acceptance criterion: ChatGPT itself must invoke the custom MCP/Tunnel and return real Anki data.

## 13. Next technical experiment

Prefer a client surface that can see `anki-local`—ideally Codex desktop if it inherits the same MCP config—and run an actual teacher interaction over returned cards.

Validate that the Tutor can turn raw teacher-facing Anki material into useful oral Tutor Units without forcing the learner to read or edit the raw cards.

Keep all review/content write-back disabled until read-only teaching quality is proven.
