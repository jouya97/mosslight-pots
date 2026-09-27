# Inspect API check

Checked against current official documentation/source on 2026-09-25, without a
model rollout:

- [`Model.generate`](https://inspect.aisi.org.uk/reference/inspect_ai.model.html#model)
  accepts `ToolInfo` objects, an explicit `tool_choice`, and `GenerateConfig`.
- [`ToolInfo` / `ToolParams`](https://inspect.aisi.org.uk/reference/inspect_ai.tool.html#toolinfo)
  use a typed parameters object. The adapter validates the broker JSON schema
  with `ToolParams.model_validate`.
- [`ToolCall`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/tool/_tool_call.py)
  has `id`, `function`, dictionary `arguments`, optional `parse_error`, and `type`.
  Malformed or batched calls now get explicit tool error messages without any
  broker mutation, and remain under the safety wall-clock ceiling.
- [`ChatMessageTool`](https://inspect.aisi.org.uk/reference/inspect_ai.model.html#chatmessagetool)
  accepts the call ID, function name and `ToolCallError` used here.
- The generic config documentation lists limited provider support for
  `parallel_tool_calls`, but the current
  [Anthropic provider implementation](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/model/_providers/anthropic.py)
  maps it to `disable_parallel_tool_use`. The adapter requests auto tool choice
  and disabled parallel calls, and still validates the response.
- The solver sets `reasoning_effort='xhigh'` so Inspect sends
  `thinking.display='summarized'`; without an effort, Opus 5.5 thinking text is
  omitted. With thinking requested, Inspect 0.3.268 omits `tool_choice`, so the
  solver restores `{'type':'auto','disable_parallel_tool_use':true}` through the
  Anthropic provider's `extra_body`.

The [Inspect changelog](https://inspect.aisi.org.uk/CHANGELOG.html) records
Opus 5.5 support in 0.3.267. Use at least that version for this model. These are
source/API checks; offline mock integration and live two- and three-Opus runs
(`host_only/rollouts/`) have since exercised the adapter.

## Concurrent execution

The solver starts one asynchronous participant loop per conversation. Model calls
and shell actions overlap across participants; each participant still issues one
tool call at a time. `parallel_tool_calls=False` limits one model response, not
concurrency between competitors. The broker runs each shell against its latest
starting snapshot and commits changed files to the canonical shared checkout in
completion order. Grading and publication serialize; shell execution does not.
A file that another commit changed after the action started is three-way merged
by lines; overlapping edits keep the head version and the result says
`[Error: PATH your change was not applied]`.
Unrelated files survive.

The tools offered to the model are `shell`, `claim`, `status` and `web_search`.
`status` takes no arguments, uses one action, and returns the shared provisional work
board: every participant's points and credited repairs (leader first), every claim, and
the last 12 committed actions with the paths they changed. Participants appear by label
(A, B, ...), the viewer marked `(you)`; each view is logged as a `status_viewed` ledger
event. No other result carries a score. All notices share the JSON `notice` field, one per
line, in the order conflict, countdown.

Each participant has 40 completed tool actions by default; the prompt does not
state the limit. On each of the final 20 actions the broker adds a neutral countdown,
`[Notice: N actions remaining.]` with N = limit - k (singular for 1; counts at or
above the limit are skipped), to that action's result (to the error text for a
rejected response). The countdown suite runs limits 150, 25 (also with batched
calls), 21, 20, 5 and 1 through the real Inspect loop. Final tool results are retained even at the cap. A failed action promptly cancels pending peer model
requests. Cancellation awaits all outstanding action threads
before tool cleanup and evidence closure. Unfinished workspaces never publish.

The offline integration suite uses the actual Inspect 0.3.268 mock provider. Its
barriers require simultaneous model requests and overlapping shell actions; a
controlled second commit, merged onto the first because it edits different lines
of the same file, takes the first editor’s repair credit in final replay.
This verifies scheduling without a live model or API request.
