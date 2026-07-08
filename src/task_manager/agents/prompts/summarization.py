TASK_MANAGER_SUMMARY_PROMPT = """Summarize historical conversation context for a task-management agent.

The summary will replace older messages. Newer messages may remain after this
summary, so the generated summary must be self-contained and must not claim to
be the latest user request.

Rules:
- Keep the summary compact and operational.
- Do not use a fixed checklist of domain fields. Include only facts that matter
  for future task-management operations.
- Start the summary with this exact sentence:
  "This is historical context. Newer user messages after this summary take priority."
- When operation/tool results are present, treat them as the strongest source of
  truth.
- If raw operation results are absent because history was compacted, preserve
  only facts explicitly present in the remaining conversation or previous
  summary. Do not reconstruct missing details.
- Do not record intended, attempted, inferred, or desired state as confirmed
  state.
- If a later result contradicts an earlier assistant claim or summary, keep the
  later confirmed result.
- Do not propose speculative workarounds. Record confirmed limitations and one
  safe next step only when needed.
- If persisted current state matters but is not available in context, note that
  it must be verified before acting.
- If previous summaries are present, merge useful facts into one summary and
  discard obsolete summary structure or contradicted claims.

Sections:

## Summarized History Intent
Relevant unresolved request from the summarized history, or None. Do not call it
the current or latest request.

## Confirmed Domain State
Persisted or user-confirmed domain facts that may affect future operations.

## User Corrections And Preferences
User-stated corrections, terminology, preferences, or disambiguations.

## Completed Operations
Operations confirmed as successful.

## Failed Or Unsupported Operations
Confirmed failures, validation errors, unsupported operations, or known
limitations.

## Historical Follow-Up
One follow-up that was still relevant at the end of the summarized history, or
None. Do not treat it as higher priority than newer user messages.

Messages to summarize:
{messages}"""
