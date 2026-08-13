# Anki ↔ ChatGPT / OpenAI Agent Connection Runbook

**Validated:** 2026-08-13  
**Scope:** read-only local Anki access  
**Canonical product record:** Living PRD in Google Drive

This document exists so the integration can be rebuilt on a different computer without relying on chat history.

## 0. Current validation matrix

| Link | Status | Evidence |
|---|---|---|
| Desktop Anki → AnkiConnect | **VALIDATED** | real local API responses |
| Local MCP → AnkiConnect → Anki | **VALIDATED** | `smoke_test_anki.py` returned real cards |
| Codex → local MCP → Anki | **VALIDATED** | real `anki-local.get_due_cards` call |
| Secure MCP Tunnel → local MCP readiness | **VALIDATED** | `doctor` passed; `/readyz` returned `ready` |
| Ordinary ChatGPT conversation → custom Anki app → Secure MCP Tunnel → local MCP → Anki | **VALIDATED on 2026-08-13** | a new non-Codex ChatGPT conversation called the Anki tool and returned the same real due-card data (`total_due=8`, `returned=5`) |
| ChatGPT voice mode → Anki tool | **NOT YET VALIDATED** | next product-surface test |
| Anki review/write-back | **NOT YET VALIDATED** | keep disabled until separate safety experiment |
| Automatic Windows background startup | **NOT VALIDATED** | a managed corporate PC triggered endpoint-security intervention; do not reproduce there |

The important product result is now stronger than the original Codex-only test:

```text
ordinary ChatGPT conversation
  -> custom MCP app (Anki Voice Tutor)
  -> Secure MCP Tunnel
  -> local stdio MCP server
  -> AnkiConnect
  -> desktop Anki
```

The learner therefore does not have to copy/paste Anki cards into ChatGPT.

---

## 1. Repository files used

Main bridge:

```text
anki_mcp_server.py
```

Support files:

```text
requirements.txt
smoke_test_anki.py
README.md
docs/ANKI_MCP_CONNECTION_RUNBOOK.md
```

Current MCP server behavior:

- Python FastMCP server.
- stdio MCP transport.
- Default AnkiConnect endpoint: `http://127.0.0.1:8765`.
- Default deck: `000-WuCai Inbox`.
- Tool: `get_due_cards(deck, limit)`.
- Calls AnkiConnect `findCards`, then `cardsInfo`.
- Returns `card_id`, `note_id`, model, raw note fields, and scheduling metadata useful to a teacher.
- Omits rendered Anki `question` / `answer` HTML/CSS noise.
- Read-only: it does not answer cards, edit notes, or mutate FSRS state.
- Declares MCP safety hints: read-only, non-destructive, closed-world.

Why the safety hints matter: during the first ChatGPT app scan, the tool was incorrectly shown as WRITE / OPEN WORLD / DESTRUCTIVE because the server did not declare annotations. That was a metadata problem, not actual behavior. The server now explicitly declares the tool as read-only.

Important ChatGPT behavior: custom app tool definitions may be snapshotted/frozen. After changing MCP annotations or schemas, refresh/re-scan the app tools in ChatGPT rather than assuming the UI updates automatically.

---

## 2. New-computer prerequisites

Install on the personal/test computer:

1. Desktop Anki.
2. AnkiConnect add-on.
3. Git.
4. Python 3.11+ recommended.
5. This repository.
6. OpenAI `tunnel-client` for the ChatGPT path.
7. A ChatGPT account/workspace that currently permits the required custom MCP read access / developer mode.

Codex is **optional**. It was useful for diagnosis but is not the intended day-to-day tutoring surface.

Keep desktop Anki open while the local bridge is being used.

---

## 3. Clone somewhere writable

Do **not** clone under `C:\Windows\System32`. The first attempt there failed with permission denied.

Example:

```powershell
cd $HOME\Documents
git clone https://github.com/yulicccccc/voice-mastery-tutor.git
cd .\voice-mastery-tutor
```

Windows caveat: `Documents` may be redirected into OneDrive. Use the actual path reported by Windows rather than assuming `$HOME\Documents` is where downloaded files live.

---

## 4. Install Python dependencies

```powershell
python -m pip install -r requirements.txt
```

The repository intentionally pins MCP to the v1 line for the current FastMCP implementation:

```text
mcp[cli]>=1.27,<2
```

Do not casually remove the `<2` bound; MCP Python SDK v2 has breaking changes.

---

## 5. Verify AnkiConnect before debugging MCP

With desktop Anki open, first verify the local AnkiConnect endpoint.

The default endpoint is:

```text
http://127.0.0.1:8765
```

Then run:

```powershell
python .\smoke_test_anki.py
```

Validated output on 2026-08-13 included:

```text
deck=000-WuCai Inbox
total_due=8
returned=5
```

Real card IDs, note IDs, models, and fields were returned.

A Pydantic `IncompleteFieldDefinitionWarning` appeared during one run but did not prevent the read from succeeding. Treat that warning as cleanup, not evidence that Anki access failed.

---

## 6. Due-card query lessons

The first collection-wide query:

```text
is:due
```

returned **1909 cards**. That is technically valid but useless as a Tutor queue.

For tests, scope the query by deck:

```text
deck:"000-WuCai Inbox" is:due
```

Observed on the test deck:

- Anki UI: `Learn 4` + `Due 4`.
- `is:due`: 8 cards.

Therefore the Tutor must later distinguish learning/relearning from ordinary review-due state rather than treating every `is:due` result as equivalent.

---

## 7. Anki data-shape lessons

Use `findCards`, then `cardsInfo`.

Prefer raw `fields` over rendered `question` / `answer` because rendered fields can contain large CSS/style blocks.

Do **not** assume:

```text
Front = question
Back = answer
```

Observed note types included:

```text
Basic-53d93
Cloze-WuCai
```

Some Basic `Back` fields contained only Source/Title metadata.

Always preserve both identities:

- `card_id`: scheduling identity.
- `note_id`: content identity.

One note can generate multiple cards.

---

## 8. Optional Codex direct diagnostic path — validated

This is useful when debugging the local MCP without involving Secure MCP Tunnel or ChatGPT UI.

After installing Codex CLI, open a **new** PowerShell so PATH refreshes.

```powershell
codex --version
```

Register the local stdio MCP:

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

Expected:

```text
anki-local
Tools: get_due_cards
```

Then request an actual call:

```text
Use the anki-local MCP tool get_due_cards with deck="000-WuCai Inbox" and limit=5.
```

Acceptance criterion: Codex must actually call `anki-local.get_due_cards` and return real local Anki card data.

This passed on 2026-08-13.

Pitfall: one launch showed `MCP startup interrupted`, but `/mcp` still listed the tool and the real call succeeded. Actual tool-call evidence outranks a generic startup warning.

A pre-existing unrelated `cloudflare-api` MCP also showed expired OAuth. Do not attribute unrelated MCP startup errors to `anki-local`.

---

## 9. Secure MCP Tunnel setup for ordinary ChatGPT

ChatGPT cannot directly call `127.0.0.1` on the user's computer. The working bridge used OpenAI Secure MCP Tunnel.

### 9.1 Create the tunnel in OpenAI Platform

Create a tunnel in the OpenAI Platform tunnel-management page.

Validated tunnel name:

```text
Anki Voice Mastery Tunnel
```

Associate it with the ChatGPT workspace that will use it. The first successful test used the user's Personal ChatGPT workspace.

Keep the `tunnel_id`; it is not the same thing as the runtime API key.

### 9.2 Download the official Windows tunnel client

On a normal Intel/AMD Windows machine, use the Windows AMD64 build. ARM64 is for Windows-on-ARM devices.

On the original test machine, the downloaded v0.0.11 AMD64 archive hash matched the publisher's release checksum before use.

Do not disable endpoint security to make the binary run.

### 9.3 Create a restricted runtime key

Create a **restricted runtime key** for the tunnel daemon with only the minimum tunnel permissions required by the current OpenAI setup (the successful configuration used Tunnel Read + Use).

Security rules:

- never paste the key into chat;
- never include it in screenshots;
- never commit it to Git;
- avoid storing it in shell history;
- if exposed, revoke it immediately and create a replacement.

During the original test, one key was accidentally visible in a screenshot. It was revoked and replaced. Treat secret rotation as part of the runbook, not an edge case.

### 9.4 Create the local stdio tunnel profile

From the repository directory, create a tunnel-client profile that points to the Python MCP server.

Generic pattern:

```powershell
& "<PATH_TO_TUNNEL_CLIENT_EXE>" init `
  --sample sample_mcp_stdio_local `
  --profile anki-local `
  --tunnel-id <YOUR_TUNNEL_ID> `
  --mcp-command "python C:/Users/<WINDOWS_USER>/Documents/voice-mastery-tutor/anki_mcp_server.py"
```

### Windows path pitfall

The first attempt used backslashes inside the MCP command and tunnel preflight effectively saw a broken path resembling:

```text
C:Users...
```

Using forward slashes fixed it:

```text
python C:/Users/<WINDOWS_USER>/Documents/voice-mastery-tutor/anki_mcp_server.py
```

Observed profile location on Windows:

```text
C:\Users\<WINDOWS_USER>\AppData\Roaming\tunnel-client\anki-local.yaml
```

### 9.5 Run tunnel preflight

Set the runtime credential for the **current PowerShell process** using a secure local method, then run:

```powershell
& "<PATH_TO_TUNNEL_CLIENT_EXE>" doctor --profile anki-local --explain
```

Validated result:

```text
RESULT ok
```

### 9.6 Start the foreground tunnel

```powershell
& "<PATH_TO_TUNNEL_CLIENT_EXE>" run --profile anki-local
```

The process stays in the foreground. That is expected; do not close the terminal while testing.

Validated local readiness endpoint:

```text
http://127.0.0.1:8080/readyz
```

Expected response:

```text
ready
```

`ready` validates the local runtime path; it is not by itself proof that ChatGPT has attached the app.

---

## 10. Attach the tunnel-backed MCP to ChatGPT — validated

UI naming changed during this experiment: Connectors / Apps / Plugins / Developer mode were in transition. Do not depend on old screenshots or one exact label.

Current OpenAI guidance uses ChatGPT developer mode and custom MCP apps. The Plugins directory is primarily a discovery/container surface; the underlying custom MCP integration is still an app.

The successful 2026-08-13 test had these prerequisites already true:

- Developer mode enabled in ChatGPT.
- `Anki Voice Mastery Tunnel` existed and was associated with the Personal ChatGPT workspace.
- local `tunnel-client run --profile anki-local` was active.
- `/readyz` returned `ready`.

Then the custom ChatGPT app was configured against that tunnel and its tools were scanned. ChatGPT discovered:

```text
get_due_cards
```

The app was presented as **Anki Voice Tutor** in the successful test conversation.

### Tool-risk classification pitfall

On the first scan, ChatGPT showed this genuinely read-only tool as high-risk (WRITE / OPEN WORLD / DESTRUCTIVE) because MCP tool annotations were missing.

The repository now declares:

```text
readOnlyHint = true
destructiveHint = false
openWorldHint = false
```

After changing annotations, refresh/re-scan the custom app tools. ChatGPT may keep a frozen snapshot of an app's tool definitions until explicitly refreshed.

### Acceptance test inside ordinary ChatGPT

Open a **new normal ChatGPT conversation**, not Codex, select/enable the Anki app if needed, and ask it to read five due cards from `000-WuCai Inbox`.

The successful 2026-08-13 ChatGPT test returned:

```text
total_due: 8
returned: 5
```

and the first card ID matched the same card returned locally/Codex.

This is the acceptance criterion that upgrades the status from "Tunnel ready" to **ordinary ChatGPT → local Anki VALIDATED**.

---

## 11. What is still NOT proven

### 11.1 ChatGPT voice mode

Text-chat tool use succeeded. We still need to verify whether the desired ChatGPT voice experience can invoke the same custom MCP app while the user is speaking hands-free.

Do not claim the voice product loop is solved until a real voice session triggers `get_due_cards`.

### 11.2 Review/write-back

Read access does **not** prove safe scheduling write-back.

Still separate experiments:

- submit first-attempt Again/Good through Anki scheduler;
- preserve revlog / FSRS semantics;
- idempotency;
- offline queue;
- conflict detection;
- note/Tutor Overlay updates.

Keep the current MCP read-only until those are deliberately tested.

### 11.3 Automatic startup

Do not make background persistence the first goal on a new computer. First prove manual startup and ChatGPT read access.

An attempt to make the tunnel automatically persist on the original **company-managed PC** coincided with endpoint-security escalation. The company security team contacted the user. Work on that machine stopped.

On a personal machine, treat automatic startup as a later convenience experiment only after the manual flow is stable.

---

## 12. Corporate endpoint-security lesson — hard boundary

The original test PC ran SentinelOne and repeatedly flagged `tunnel-client.exe` as suspicious. Later, corporate security intervened.

Rules:

1. Do not disable, bypass, evade, or whitelist corporate security controls yourself.
2. Stop development on the managed machine when security policy blocks it.
3. Move experimentation to an approved personal/test computer or obtain IT approval.
4. Keep all credentials out of company logs/screenshots where practical.

Observed effects on the managed machine included:

- tunnel-client could initially run and reach `/readyz`;
- `tunnel-client codex plugin install` reported that the binary was not executable;
- attempts around background/persistent startup were not reliable;
- security escalation made further testing inappropriate.

This is an environment/policy constraint, not evidence that the architecture is invalid.

---

## 13. Other pitfalls captured from the experiment

1. `C:\Windows\System32` is a bad clone/work directory for this project.
2. Windows OneDrive folder redirection can make paths surprising.
3. When a publisher supplies hashes, verify the downloaded release archive before blaming security software or architecture mismatch.
4. `windows-amd64` was correct for the tested Intel/AMD Windows PC; do not switch to ARM64 just because security software objects.
5. A PowerShell opened before installing Codex did not see `codex`; a new terminal refreshed PATH.
6. `question`/`answer` HTML is poor teacher input; use source note `fields`.
7. Anki card count can be enormous; do not equate “all due cards” with “what should be taught now.”
8. A ChatGPT UI may move or rename Apps/Plugins/Connectors. Test actual app/tool discovery instead of assuming a missing label means MCP is impossible.
9. Tool annotations materially affect ChatGPT's safety UI. A read-only implementation should say so explicitly.
10. Changes to an MCP tool may require a ChatGPT app refresh/re-scan; do not assume the approved snapshot auto-updates.
11. Codex is a useful diagnostic client, but it is not the intended learner-facing surface for this product.

---

## 14. Personal-computer rebuild checklist

Use this order. Do not skip ahead to ChatGPT until the lower layer passes.

### Layer A — Anki

- [ ] Install Anki.
- [ ] Install AnkiConnect.
- [ ] Open Anki.
- [ ] Confirm AnkiConnect responds.

### Layer B — repository/local MCP

- [ ] Clone `voice-mastery-tutor`.
- [ ] Install `requirements.txt`.
- [ ] Run `python smoke_test_anki.py`.
- [ ] Confirm real cards are returned.

### Layer C — optional direct MCP diagnostic

- [ ] If useful, register `anki-local` in Codex.
- [ ] Confirm a real `get_due_cards` call succeeds.

### Layer D — Secure MCP Tunnel

- [ ] Download official tunnel-client for the machine architecture.
- [ ] Create/reuse a Platform tunnel associated with the correct ChatGPT workspace.
- [ ] Create a restricted runtime key; store it safely.
- [ ] Create `anki-local` tunnel profile using forward-slash Python path.
- [ ] Run `doctor --explain` and get `RESULT ok`.
- [ ] Start `run --profile anki-local`.
- [ ] Confirm `/readyz` says `ready`.

### Layer E — ordinary ChatGPT

- [ ] Enable Developer mode if required by the current plan/UI.
- [ ] Create/configure the custom MCP app against the tunnel.
- [ ] Scan/refresh tools.
- [ ] Confirm `get_due_cards` is classified as read-only/non-destructive.
- [ ] Open a new normal ChatGPT conversation.
- [ ] Ask for five due cards from `000-WuCai Inbox`.
- [ ] Confirm the tool really runs and returns the same real card IDs/data.

### Layer F — product-specific next test

- [ ] Start a ChatGPT **voice** conversation.
- [ ] Verify the Anki app/tool can be invoked from voice.
- [ ] If yes, begin the real tutor-loop experiment: one atomic oral question at a time.

---

## 15. Product interpretation

The technical proof now supports the intended architecture:

```text
Capture / WuCai
  -> Anki (teacher-facing material + scheduler)
  -> ChatGPT custom MCP app
  -> AI Tutor reads due/source material directly
  -> learner only needs to speak
```

The next bottleneck is no longer “Can ChatGPT see local Anki at all?”

The next bottlenecks are:

1. Can the desired **voice** surface use the app reliably?
2. Can the Tutor transform messy teacher-facing cards into good atomic oral Tutor Units?
3. Can learner progress / insights persist safely?
4. Can review outcomes later be written back without corrupting Anki/FSRS semantics?
