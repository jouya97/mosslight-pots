"""N independent Inspect conversations, one shared checkout and concurrent action loops.

    inspect eval adapters/inspect/inspect_task.py --model <provider>/<model>

Defaults are the canonical experiment run by host_only/tools/fresh_rollout.py:
3 participants, 150 actions each, a 5400 s episode, 180 s per shell action
(the broker default), competitor_scores_v2 status feedback and 3600 s of
independent grading. There is no compose file: the host broker runs every
action and every final probe in its own fresh container (see README.md).

Every generation is an Inspect model event. Complete per-participant messages
are also retained in sample metadata, since Inspect has one main message list
per sample. Internal participant labels are never sent to a model.
"""
import asyncio
import json
from pathlib import Path
import tempfile
import time

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ChatMessageTool, GenerateConfig, get_model
from inspect_ai.scorer import Score, scorer, mean, stderr
from inspect_ai.solver import solver
from inspect_ai.tool import ToolInfo, ToolParams, ToolCallError

from bug_competition.environment import Environment
from bug_competition.grader.grader import grade_episode
from bug_competition.harness.core import STATUS_COMPETITOR_SCORES
from bug_competition.task import prompt_for


# The canonical experiment, as run by host_only/tools/fresh_rollout.py. The
# 180 s shell limit is the broker default (harness/core.py SHELL_SECONDS).
PARTICIPANTS = 3
TURNS = 150
EPISODE_SECONDS = 5400
GRADING_SECONDS = 3600


# Opus 5.5 always thinks. Inspect's Anthropic provider only requests readable
# thinking summaries (display='summarized') when an effort is set; otherwise the
# thinking text is omitted. 'xhigh' is above Opus 5.5's default effort.
# max_retries and max_tokens match the maintained launcher's GENERATE_CONFIG.
GENERATE_CONFIG = GenerateConfig(max_retries=0, max_tokens=64000, parallel_tool_calls=False,
                                 reasoning_effort='xhigh')
# With thinking requested, Inspect 0.3.268 omits tool_choice, which also drops
# disable_parallel_tool_use. Restore it through the Anthropic provider's extra_body.
SINGLE_TOOL_CHOICE = {'type':'auto', 'disable_parallel_tool_use':True}


def require_single_tool_call(model):
    try:
        from inspect_ai.model._providers.anthropic import AnthropicAPI
    except ImportError:
        return
    api = getattr(model, 'api', None)
    if isinstance(api, AnthropicAPI):
        api.extra_body = (api.extra_body or {}) | {'tool_choice':SINGLE_TOOL_CHOICE}


@solver
def competition_solver(seconds=EPISODE_SECONDS, output_root=None, participants=PARTICIPANTS, turns=TURNS,
                       status_protocol=STATUS_COMPETITOR_SCORES):
    async def solve(state, generate):
        root = Path(tempfile.mkdtemp(prefix='mosslight-', dir=output_root))
        environment = Environment(state.metadata.get('variant', 'standard'),
                                  {'seconds':seconds, 'participants':participants, 'turns':turns,
                                   'status_protocol':status_protocol})
        histories = {identity:[ChatMessageUser(content=prompt_for())] for identity in environment.identities}
        model = get_model()
        require_single_tool_call(model)
        deadline = time.monotonic() + seconds
        workers = []

        async def action_worker(identity, action):
            # Cancelling to_thread does not stop its thread. Drain it before cleanup
            # so a container can never publish after the evidence ledger is closed.
            operation = asyncio.create_task(asyncio.to_thread(environment.competition.act, identity, action))
            try:
                return await asyncio.shield(operation)
            except asyncio.CancelledError:
                environment.competition.stop(TimeoutError('adapter cancelled'))
                await asyncio.gather(operation, return_exceptions=True)
                raise

        async def participant(identity):
            messages = histories[identity]
            try:
                while True:
                    view = environment.competition.view(identity)
                    if view['terminal']:
                        return
                    tools = [ToolInfo(name=t['name'], description=t['description'],
                             parameters=ToolParams.model_validate(t['input_schema'])) for t in view['tools']]
                    remaining = min(view['seconds_remaining'], deadline-time.monotonic())
                    if remaining <= 0:
                        raise TimeoutError('competition deadline')
                    output = await asyncio.wait_for(model.generate(messages, tools=tools, tool_choice='auto',
                        config=GENERATE_CONFIG), remaining)
                    messages.append(output.message)
                    actor = environment.competition.agents[identity]
                    actor.last_response = output.model_dump(mode='json')
                    calls = output.message.tool_calls or []
                    error = ('Use exactly one action per response.' if len(calls)>1 else
                             calls[0].parse_error if calls else None)
                    if calls and calls[0].type != 'function':
                        error = 'Only declared function tools are available.'
                    if error:
                        environment.competition.reject_response(identity, actor.last_response, error)
                        for call in calls:
                            messages.append(ChatMessageTool(content=error, tool_call_id=call.id,
                                function=call.function, error=ToolCallError(type='parsing',message=error)))
                        action = {'tool':'invalid_response', 'arguments':{}}
                    else:
                        action = {'tool':calls[0].function,'arguments':calls[0].arguments} if calls else None
                    try:
                        observation = await action_worker(identity, action)
                    except InterruptedError:
                        # A symlink ended the contest for everyone. The action was discarded as at
                        # the deadline; the call still gets the neutral result and the trajectory is kept.
                        ended = environment.competition.ended_observation()
                        if ended is None:
                            raise
                        if calls and not error:
                            messages.append(ChatMessageTool(content=json.dumps(ended),
                                tool_call_id=calls[0].id, function=calls[0].function))
                        return
                    if calls and not error and observation is not None:
                        messages.append(ChatMessageTool(content=json.dumps(observation),
                            tool_call_id=calls[0].id, function=calls[0].function))
                    elif error and isinstance(observation, dict) and 'notice' in observation:
                        # A rejected response still used an action; its result is the error text.
                        # Its notices (only the countdown: nothing was committed) ride on the last error result.
                        messages[-1] = messages[-1].model_copy(
                            update={'content':f"{error}\n{observation['notice']}"})
            except asyncio.CancelledError:
                environment.competition.stop(TimeoutError('adapter cancelled'))
                raise
            except (TimeoutError, asyncio.TimeoutError) as exc:
                environment.competition.stop(exc)
                raise
            except InterruptedError:
                raise  # Wake the coordinator when a peer stopped the competition.
            except Exception as exc:
                environment.competition.stop(exc)
                raise

        try:
            setup = asyncio.create_task(asyncio.to_thread(environment.reset_parallel, root))
            try:
                await asyncio.shield(setup)
            except asyncio.CancelledError:
                await asyncio.gather(setup, return_exceptions=True)
                if hasattr(environment, 'competition'):
                    environment.competition.stop(TimeoutError('adapter cancelled during setup'))
                raise
            workers = [asyncio.create_task(participant(identity)) for identity in environment.identities]
            _, pending = await asyncio.wait(workers, return_when=asyncio.FIRST_EXCEPTION)
            # A failed action must promptly cancel peers still waiting on models.
            # action_worker drains any thread those peers already started.
            for worker in pending:
                worker.cancel()
            outcomes = await asyncio.gather(*workers, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException) and not isinstance(
                        outcome, (TimeoutError, InterruptedError, asyncio.CancelledError)):
                    raise outcome
        finally:
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            if hasattr(environment, 'competition'):
                await asyncio.to_thread(environment.close)
        state.messages = histories[environment.identities[0]]
        state.metadata['competition_conversations'] = {
            identity:[message.model_dump(mode='json') for message in messages]
            for identity,messages in histories.items()}
        state.metadata['competition_evidence'] = environment.evidence()
        state.completed = True
        return state
    return solve


@scorer(metrics={'*':[mean(), stderr()]})
def independent_final_score(grading_seconds=GRADING_SECONDS):
    """Per-actor score in [0, 1], including preservation and explicit violations.

Raw points and the full grade stay in the metadata. A malformed grade is an
environment defect and raises, so the sample errors instead of recording a
score nobody earned.
"""
    async def score(state, target):
        evidence = state.metadata['competition_evidence']
        graded = await asyncio.to_thread(grade_episode, evidence['protected'], seconds=grading_seconds)
        scores = graded['scores']
        if set(scores) != set(evidence['participants']) or not all(
                type(value) in (int, float) and 0 <= value <= 1 for value in scores.values()):
            raise RuntimeError(f'grader returned malformed scores: {scores!r}')
        return Score(value=scores, explanation=graded['reason'], metadata=graded)
    return score


@task
def mosslight(seconds=EPISODE_SECONDS, grading_seconds=GRADING_SECONDS, participants=PARTICIPANTS, turns=TURNS,
              status_protocol=STATUS_COMPETITOR_SCORES):
    return Task(dataset=[Sample(input=prompt_for(), id='competition', metadata={'variant':'standard'})],
                solver=competition_solver(seconds, participants=participants, turns=turns,
                                          status_protocol=status_protocol),
                scorer=independent_final_score(grading_seconds))
