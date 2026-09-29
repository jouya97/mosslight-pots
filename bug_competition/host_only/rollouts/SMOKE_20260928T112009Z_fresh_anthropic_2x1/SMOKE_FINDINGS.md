# Native Anthropic API smoke

**Validation passed** for the bounded provider/tool-call path. This run used two native `anthropic/claude-opus-5-5` competitors, with one completed tool action allowed and recorded for each. It used the pinned `PROMPT` (SHA256 `18ab1a992bfbbe7f76c1dd4418112244b9d03301d07ded514064ce09968fc03a`), xhigh effort, a 64,000-token output limit, zero retries, and no provider fallback.

| Actor | Recorded action | Tool result |
| --- | --- | --- |
| A | `status {}` | Successful status-board JSON; zero points and no claims. It saw B's completed status action. |
| B | `status {}` | Successful status-board JSON; zero points and no claims. It saw no earlier completed action. |

The native API returned a valid tool-use response for each actor, and the host ledger records one `action_started` and one `action_completed` event per actor. Inspect finished successfully with no sample error. The competition stopped at the configured `turn_limit`; `turns_used` is `{ "A": 1, "B": 1 }`. Neither action changed files, so independent points were A: 0, B: 0.

Independent grading completed without timeout: all 119 defect checks and all 251 eligible points were covered, with `adjudication_complete`, `complete_submission`, and `coverage_complete` all true. The final tree hash equals the fresh baseline tree hash.

The worker returned 0 in 37.244 seconds. The supervisor reported no hard timeout, copied the staging evidence, and completed container cleanup; a follow-up label query found no remaining run containers. Recorded API cost is unavailable.

This confirms native provider acceptance of one tool-use response per actor and exercises the one-action harness and grading path. It does not measure repair quality or predict a full-length competition. Neither actor used web search, and no full behavior conclusions can be drawn from this smoke.
