# Anki ↔ ChatGPT / OpenAI Agent Connection Runbook

**Validated:** 2026-08-23
**Scope:** local Anki read, durable Tutor/Triage state, private GPT Quick Tunnel recovery, and controlled review sync
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
| Local Tutor policy → JSONL learner state | **UNIT TESTED 2026-08-17** | lightweight/deep decisions, restart recovery, learner override, value skip, and continuity |
| Durable ReviewEvent queue | **UNIT TESTED 2026-08-17** | stable IDs, restart recovery, duplicate-sync protection, conflict handling, and zero-write dry-run |
| One disposable card → Good → Anki scheduler | **VALIDATED 2026-08-17** | `answerCards` returned `[true]`; event became applied; immediate retry found zero pending and did not increment reps again |
| One disposable card → Again → Anki scheduler | **VALIDATED 2026-08-17** | `answerCards` used ease 1 exactly once; Tutor retained `prompted_recall`; immediate retry made no second review |
| Private GPT Action → free Quick Tunnel → local Actions API → durable study session | **VALIDATED 2026-08-19** | GPT editor `getStudySession` reached the Mac as HTTP 200 and recovered the active 10-card batch |
| Candidate StudySession → Teacher Triage → durable derived queue → fresh ChatGPT conversation | **VALIDATED 2026-08-23** | the new conversation recovered effective treatments and learner overrides without re-triage; Reference/Ignore stayed excluded and ReviewEvent count remained zero |
| Daily real review write-back on this personal Mac | **USER-ENABLED 2026-08-19** | LaunchAgent and local/public health report `ANKI_REVIEW_WRITEBACK_ENABLED=true`; enabling the flag itself performed no review |
| Sustained multi-card production review/write-back | **NOT YET VALIDATED** | requires an explicit user “更新 Anki” run with per-event conflict/idempotency evidence |
| ChatGPT custom-app/voice invocation of write tools | **NOT YET VALIDATED** | local scheduler feasibility does not prove product-surface invocation |
| Anki note/content write-back | **DISABLED / OUT OF SCOPE** | no note fields or FSRS internals are edited |
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
models.py
learner_store.py
tutor_engine.py
review_sync.py
study_session.py
actions_api.py
requirements.txt
smoke_test_anki.py
README.md
docs/ANKI_MCP_CONNECTION_RUNBOOK.md
```

Current MCP server behavior:

- Python FastMCP server.
- stdio MCP transport.
- Default AnkiConnect endpoint: `http://127.0.0.1:8765`.
- Due-card reads require an explicitly configured deck; StudySessions preserve
  the decks selected in the Anki add-on.
- Tools: `get_due_cards`, `get_study_session`, `get_tutor_context`,
  `record_triage_results`, `decide_tutor_next_step`, `record_review_result`, and
  `sync_pending_reviews`.
- Calls AnkiConnect `findCards`, then `cardsInfo`.
- Returns `card_id`, `note_id`, model, raw note fields, and scheduling metadata useful to a teacher.
- Omits rendered Anki `question` / `answer` HTML/CSS noise.
- `get_due_cards` remains read-only and never answers cards, edits notes, or
  mutates FSRS state.
- `decide_tutor_next_step` records local Tutor evidence and never calls
  AnkiConnect.
- `record_triage_results` appends durable Teacher/learner-override treatments.
  The immutable StudySession is not rewritten; Reference/Ignore are excluded
  only from the derived active queue. Triage creates no ReviewEvent and never
  calls AnkiConnect.
- `record_review_result` creates one durable ReviewEvent per card/scheduler
  snapshot and does not call AnkiConnect. `not_attempted` creates no fake review.
- `sync_pending_reviews` defaults to dry-run and requires the process-level
  `ANKI_REVIEW_WRITEBACK_ENABLED=true` flag for a real scheduler call.
- Before applying, review sync compares the current scheduler snapshot with the
  durable event snapshot. External changes become conflicts; only confirmed
  AnkiConnect success marks an event applied.
- No code directly updates the Anki database, note fields, due/interval values,
  stability, difficulty, or other FSRS internals.

Installed API investigation on 2026-08-17 found Anki 25.09 with AnkiConnect API
v6. The installed `answerCards` action delegates to Anki's
`scheduler.answerCard(card, ease)`. Good maps to ease 3 and Again to ease 1.
AnkiConnect does not accept an idempotency key or atomically combine the snapshot
precheck with the answer, so a small race window remains. Do not work around that
limitation by editing Anki's database.

Why the safety hints matter: during the first ChatGPT app scan, the read tool was incorrectly shown as WRITE / OPEN WORLD / DESTRUCTIVE because the server did not declare annotations. That was a metadata problem, not actual behavior. The read tool now explicitly declares read-only behavior; local Tutor/queue writes are declared non-read-only but non-destructive and closed-world.

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
deck=<deck-name>
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
deck:"<deck-name>" is:due
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
Use the anki-local MCP tool get_due_cards with deck="<deck-name>" and limit=5.
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

Open a **new normal ChatGPT conversation**, not Codex, select/enable the Anki app if needed, and ask it to read five due cards from a configured test deck.

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

Read access did not by itself prove safe scheduling write-back. A separate,
approved experiment on 2026-08-17 validated only the Good path on one disposable
card in a dedicated test deck:

```text
completed card
  -> durable pending ReviewEvent
  -> sync_pending_reviews(dry_run=false)
  -> AnkiConnect answerCards(ease=3)
  -> Anki scheduler
  -> confirmed [true]
  -> ReviewEvent applied
```

Observed scheduler behavior was consistent with a new-card Good review: the card
moved from new to learning, `reps` changed from 0 to 1, and Anki updated its own
scheduler fields. Repeating sync immediately returned `pending_found=0`, made no
second `answerCards` call, and left `reps` at 1.

The feature flag was enabled only for the experiment process and was disabled
again immediately afterward. Its repository default remains false.

Still separate experiments requiring explicit approval:

- one disposable Again review;
- batch or production review write-back;
- concurrent multi-client behavior and AnkiWeb sync;
- ordinary ChatGPT custom-app write invocation;
- ChatGPT voice-mode write invocation;
- note/Tutor Overlay content updates.

Keep production write-back disabled. The validated experiment does not authorize
real learning-card writes, batch synchronization, or note/content mutation.

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

This is the historical official OpenAI workspace-tunnel route. It may require workspace/organization permissions. For the current free personal-Mac path, use Section 16 instead.

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
- [ ] Ask for five due cards from a configured test deck.
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

---

## 16. Current personal-Mac path — free Quick Tunnel + private GPT Action

This is the current daily operating path. It avoids a paid OpenAI Business workspace/organization tunnel while keeping ChatGPT as the learner-facing classroom.

```text
Desktop Anki
  -> local Anki access on 127.0.0.1:28765
  -> Tutor Actions API on 127.0.0.1:28766
  -> Cloudflare Quick Tunnel (*.trycloudflare.com)
  -> private GPT Action
  -> ordinary ChatGPT desktop/mobile conversation
```

### 16.1 Persistent services

- The Actions API LaunchAgent runs the private Actions API.
- The tunnel LaunchAgent runs `cloudflared`.
- The tunnel LaunchAgent must call `scripts/run_quick_tunnel.zsh`. Do not use `scripts/run_gateway_tunnel.zsh` merely to restart the free tunnel because that script also updates the separate Worker origin.
- The public tunnel forwards only to `127.0.0.1:28766`; it must never become a general proxy for arbitrary AnkiConnect methods.

### 16.2 Authentication

The GPT Action credential is a Tutor-specific Bearer token, not an OpenAI API key. It does not call OpenAI models or create OpenAI API charges.

- macOS Keychain service: `voice-mastery-tutor-actions`
- GPT Authentication type: `API Key`
- Auth type: `Bearer`
- Never print, paste into logs, commit, screenshot, or document the token value.

Important: the GPT editor’s hidden API Key field can be empty after the Action hostname is changed or Authentication is reopened. Saving that empty field removes the credential. Re-enter the Keychain-backed Tutor token before clicking Save, then click Update on the GPT.

### 16.3 Quick Tunnel hostname recovery

A Quick Tunnel hostname belongs to the current `cloudflared` process. The LaunchAgent restarts the process automatically, but a restart can generate a new random hostname. Durable Tutor learner state, study sessions, and ReviewEvents remain intact; only the transport address changes.

Recovery checklist:

1. Confirm local `http://127.0.0.1:28766/health` returns HTTP 200.
2. Read the new `https://<random>.trycloudflare.com` URL from the tunnel log.
3. Confirm public `/health` returns HTTP 200.
4. Confirm public `/openapi.json` uses that exact URL in `servers[0].url` and exposes exactly seven operations:
   - `getDueCards`
   - `getStudySession`
   - `getTutorContext`
   - `recordTriageResults`
   - `decideTutorNextStep`
   - `recordReviewResult`
   - `syncPendingReviews`
5. Make one authenticated, read-only `POST /v1/study-session` preflight without printing the Bearer token. Verify the expected active durable session/card count.
6. In the private GPT editor, replace only the Action schema server URL.
7. Restore the Tutor Bearer token, Save Authentication, and Update the GPT.
8. Run the editor `getStudySession` Test. Select `Always allow` for the new hostname.
9. Accept the recovery only when the local Actions log contains `POST /v1/study-session HTTP/1.1` 200 and the GPT result contains the expected durable `session_id`.

Do not call `recordReviewResult` or `syncPendingReviews` just to test transport.

### 16.4 Error interpretation

| Symptom | Boundary | Next check |
|---|---|---|
| `ClientResponseError` and no local POST | ChatGPT Action domain/auth/approval, before the Mac | hostname saved, Bearer restored, new domain allowed |
| HTTP 401 `missing_or_invalid_bearer_token` | request reached the adapter without the correct Tutor credential | restore Keychain-backed Bearer token |
| HTTP 502 | request reached the adapter but downstream Tutor/Anki was unavailable | Actions API logs and identity-verified Anki endpoint |
| HTTP 200 + expected durable session | read path operational | proceed to the normal study flow |

Port responsiveness is not identity proof. Before a real review write, verify the configured local Anki endpoint represents the intended collection/decks rather than an unrelated service impersonating AnkiConnect.

### 16.5 Teacher Triage and cross-conversation recovery

`getStudySession` keeps the candidate material immutable and derives the current
learning queues from durable triage events:

```text
immutable Candidate StudySession
  -> untriaged cards
  -> Teacher Triage
  -> durable triage_result events
  -> derived active/reference/ignored queues
```

For every untriaged batch, the Teacher calls `recordTriageResults` once with all
decisions, then reloads `getStudySession`. The active treatments are
`understand`, `remember`, `apply`, and `practice`; `reference` and `ignore` stay
in the candidate manifest but do not enter active learning. Effective treatment
uses the latest `learner_override` when present, otherwise the latest Teacher
result. A newer learner override may replace an older one while the append-only
history remains intact.

Triage does not create a ReviewEvent, answer an Anki card, or change the Anki
scheduler. A fresh ChatGPT conversation recovers the same durable triage state,
derived queues, and learner overrides. It does not classify already-triaged
cards again.

### 16.6 Mobile Voice handoff

1. Select the desired decks and 1–20 cards in the Anki add-on.
2. In the private GPT, say `开始复习我刚刚在 Anki 选择的批次`.
3. Complete Teacher Triage for any `untriaged_cards`, persist it once, and reload `getStudySession`.
4. `getStudySession` must embed only the derived active learning cards in the complete voice handoff packet before Voice Mode starts.
5. Continue the same conversation on the phone in Voice Mode. Per-card Actions are not required while the complete packet is already in the conversation.
6. When back in text mode, say `保存本次学习` to create durable Tutor/ReviewEvent records.
7. Say `更新 Anki` only when a real scheduler sync is intended.

The Mac, Actions API, and tunnel must be online for start/save/update Action calls. Once the complete packet is embedded, the spoken teaching portion can continue on the phone without a new Action for every card.

### 16.7 Daily write-back mode

The code remains fail-closed when no environment override is present. On this personal Mac, the user has explicitly approved the LaunchAgent setting:

```text
ANKI_REVIEW_WRITEBACK_ENABLED=true
```

Enabling the flag does not review a card. A scheduler write occurs only after the user explicitly says `更新 Anki` and the GPT calls `syncPendingReviews(dry_run=false)` for the active `session_id`.

After changing the flag, restart only the Actions API service. Do not restart the tunnel. Verify the effective value from both local and public `/health`; do not rely on the plist text alone.

All real writes remain subject to:

- current-session scoping;
- first-attempt rating semantics;
- durable event idempotency protection;
- scheduler snapshot conflict detection;
- confirmed-success-only `pending -> applied` transition;
- no direct Anki DB, due, interval, stability, difficulty, or FSRS edits;
- no Anki note/content write through the review-sync path;
- no fake review for a low-value skip without retrieval.

The private GPT read path is validated. Good and Again scheduler writes are validated on disposable cards. Sustained real multi-card synchronization through the GPT Action is still an acceptance test, not yet a production claim.
