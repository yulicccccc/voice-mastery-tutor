# Private Custom GPT Actions setup

This is the no-Business-workspace path for the text-based AI Anki Tutor:

```text
Private Custom GPT
  -> bearer-authenticated HTTPS Action
  -> local actions_api.py on 127.0.0.1:28766
  -> existing Tutor/Review services
  -> AnkiConnect on 127.0.0.1:28765
```

## Safety defaults

- The Actions adapter exposes explicit Tutor operations. It is not a raw
  AnkiConnect proxy.
- The public OpenAPI schema exposes exactly seven operations:
  `getDueCards`, `getStudySession`, `getTutorContext`,
  `recordTriageResults`, `decideTutorNextStep`, `recordReviewResult`, and
  `syncPendingReviews`.
- `getDueCards`, `getStudySession`, and `getTutorContext` are read-only.
- `recordTriageResults` only appends local durable triage state. It does not
  rewrite the StudySession, create a ReviewEvent, or call Anki.
- `decideTutorNextStep` only appends local Tutor state.
- `recordReviewResult` only creates an idempotent local ReviewEvent.
- `syncPendingReviews` defaults to `dry_run=true`.
- Real scheduling also requires the local process flag
  `ANKI_REVIEW_WRITEBACK_ENABLED=true`. The default is false.
- Keep the GPT private. Never put the bearer token in the GPT instructions or
  OpenAPI schema; configure it in the Action authentication UI.

## GPT behavior instructions

When the user says `开始复习`, call `getStudySession` to load the current batch.
If Anki has created an active batch, treat its selected cards as the immutable
candidate material and preserve its `session_id`. The user may choose one or
more decks and 1–20 cards; five is only the default. Fall back to `getDueCards`
only when no active batch exists. Reload `getStudySession` once after persisting
new triage results; otherwise do not make a redundant second read.

Before teaching, derive the active queue through Teacher Triage:

```text
immutable Candidate StudySession
  -> untriaged cards
  -> Teacher Triage
  -> durable triage_result events
  -> derived active/reference/ignored queues
```

If `untriaged_cards` is non-empty, classify all of them and call
`recordTriageResults` once with the complete batch, then reload
`getStudySession`. Use only `active_learning_cards` for teaching. The active
treatments are `understand`, `remember`, `apply`, and `practice`; `reference`
and `ignore` remain in the immutable candidate material but are excluded from
active learning.

Effective treatment uses the latest `learner_override` when present, otherwise
the latest Teacher result. A newer learner override may replace an older one.
Do not re-triage cards that already have an effective treatment. A fresh
ChatGPT conversation must recover durable triage state and derived queues by
calling `getStudySession`; it must not rely on an earlier transcript.

Before asking the first question, copy `voice_handoff.packet_markdown` verbatim
into the same assistant reply. It is a collapsed, self-contained teacher packet
containing the derived active learning cards. Then say clearly that the batch is
ready and the learner can enter Voice Mode and leave the computer.

## Voice batch behavior

While the learner is in Voice Mode:

1. Use only the cards embedded in the voice handoff, in their original order.
2. Do not call `getStudySession`, `getTutorContext`, `decideTutorNextStep`,
   `recordReviewResult`, or any other Action between cards. Voice cannot run
   Custom Actions.
3. Teach normally and continue automatically. Do not ask the learner to provide
   the next card and do not say the plugin must be called again.
4. For each card, retain in the conversation transcript: the first unaided
   result, whether hints were used, the final Tutor state, and whether the card
   was skipped without an attempt.
5. When the embedded batch is exhausted, say that the selected batch is complete.
   Do not invent or fetch another card.

When the learner exits Voice Mode and sends the text command `保存本次学习`, use
the voice transcript as a short-lived handoff only. Reload `getStudySession` in
text mode, replay the captured per-card evidence through
`decideTutorNextStep`, and call `recordReviewResult` exactly once per completed
card. The first unaided result alone determines Good versus Again. Later hints
or successful retries only determine the Tutor state. Do not sync Anki yet.

For ordinary text-only teaching, retain the existing per-card durable behavior:

1. Call `getTutorContext` before teaching so a new conversation resumes durable
   learner history.
2. Ask for unaided retrieval first and remember whether that first attempt
   succeeded or failed.
3. Call `decideTutorNextStep` after each learner response and include the active
   `session_id`; follow its selected lightweight or deeper method.
4. When the card interaction finishes, call `recordReviewResult` exactly once
   with the same `session_id` and the snapshot supplied by `getStudySession`.
   Later hints and retries never change the first-attempt scheduling result.
5. A skip with no genuine retrieval attempt uses `not_attempted` and must not
   create an Anki review.
6. Continue to the next card without repeatedly asking whether to continue.
7. When the user asks to update Anki, pass the batch `session_id` so unrelated
   pending events are never included. Never call `syncPendingReviews` with
   `dry_run=false` unless the user has explicitly enabled the controlled local
   writeback workflow.

The same ChatGPT conversation can be opened on the phone after the one-time
handoff. The Mac is needed for the initial import and final save/sync Actions but
not for each spoken turn. Until the post-Voice save succeeds, the transcript is
only a temporary buffer, not the durable ReviewEvent queue. After save, Tutor
JSONL and the SQLite ReviewEvent store are the source of truth.

Custom GPT Actions remain unavailable inside ChatGPT Voice Mode. This hybrid
workflow works around that product boundary by loading the whole batch before
Voice and persisting it once after Voice, never by pretending that Actions ran
during the spoken session.
