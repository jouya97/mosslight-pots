"""Execution side of branch_rollout; imported only by an explicit run command."""
from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from bug_competition.harness.core import DockerShell, ScriptedAgent, process
from bug_competition.harness.parallel import ParallelCompetition, actions_remaining_text
from bug_competition.grader.weights import DEFAULT_MANIFEST
from bug_competition.host_only.tools.branch_rollout import read_json, write_json, validate_bundle


class ResumedCompetition(ParallelCompetition):
    def restore(self, checkpoint, records, state, config):
        """Recreate broker state without re-baselining the repaired tree or resetting credit."""
        if self.started:
            raise ValueError('competition already started')
        self.started = True
        self.deadline = time.monotonic() + config['seconds']
        self.turn_limit = config['turn_limit']
        self.notice_counts = set(config['notices'])
        self.turns_used = copy.deepcopy(state['turns_used'])
        self.finished = set(state['finished'])
        self.baseline = copy.deepcopy(state['baseline'])
        self.current = copy.deepcopy(state['current'])
        self.owners = copy.deepcopy(state['owners'])
        self.claims = copy.deepcopy(state['claims'])
        self.recent = copy.deepcopy(state['recent'])
        self.last_observation = copy.deepcopy(state['last_observation'])
        self.current_hash = state['snapshot_hashes'][-1]
        self.counter = len(state['snapshot_hashes'])
        self.reason = 'agents_exhausted'
        self.work_root = self.protected / 'work'
        self.work_root.mkdir()
        for index in range(self.counter):
            shutil.copytree(Path(checkpoint) / 'snapshots' / str(index),
                            self.protected / 'snapshots' / str(index))
        for record in records:
            self.audit.append({k: v for k, v in record.items() if k != 'hash'})
            if self.audit.previous != record['hash']:
                raise ValueError('Copied audit prefix changed')
        self.audit.append(dict(type='branch_started', parent=config['parent'],
            parent_sequence=config['source_sequence'], parent_audit_head=config['parent_audit_head'],
            turn_limit=self.turn_limit, notices=config['notices'], oracle_origin=config['oracle_origin']))

    def remaining_notice(self, used_after):
        remaining = self.turn_limit - used_after
        return actions_remaining_text(remaining) if remaining in self.notice_counts and remaining < self.turn_limit else None


def check_historical_verdicts(oracle, checkpoint, state, seconds):
    """Refuse to continue with replacement probes that contradict any recorded snapshot."""
    deadline = time.monotonic() + seconds
    checked = 0
    for index, expected in enumerate(state['snapshot_verdicts']):
        actual = oracle(Path(checkpoint) / 'snapshots' / str(index), deadline - time.monotonic())
        if actual != expected:
            changed = sorted(k for k in set(actual) | set(expected) if actual.get(k) != expected.get(k))
            raise ValueError(f'Oracle history mismatch at snapshot {index}: {changed}; no model continuation permitted')
        checked += 1
        if time.monotonic() >= deadline:
            raise TimeoutError('Historical oracle validation deadline expired')
    return checked


async def continue_participants(competition, histories, generate, tools, config):
    """Dependency-injected model boundary allows offline end-to-end continuation tests."""
    from inspect_ai.model import ChatMessageTool
    from inspect_ai.tool import ToolCallError
    allowed = {t.name for t in tools}

    async def action(identity, value):
        operation = asyncio.create_task(asyncio.to_thread(competition.act, identity, value))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            competition.stop(TimeoutError('continuation cancelled'))
            await asyncio.gather(operation, return_exceptions=True)
            raise

    async def participant(identity):
        messages = histories[identity]
        try:
            while not competition.view(identity)['terminal']:
                output = await asyncio.wait_for(generate(messages, tools=tools, tool_choice='auto', config=config),
                                                competition.remaining())
                messages.append(output.message)
                raw = output.model_dump(mode='json')
                competition.agents[identity].last_response = raw
                transformations = ((raw.get('metadata') or {}).get('extra_body') or {}).get('input_transformations')
                if transformations:
                    competition.audit.append(dict(type='continuation_input_transformed', agent=identity,
                                                   transformations=transformations))
                    raise ValueError('Provider transformed restored input; stop to review continuation fidelity')
                calls = output.message.tool_calls or []
                error = ('Use exactly one action per response.' if len(calls) > 1 else
                         calls[0].parse_error if calls else None)
                if calls and (calls[0].type != 'function' or calls[0].function not in allowed):
                    error = 'Only declared function tools are available.'
                if error:
                    competition.reject_response(identity, raw, error)
                    for call in calls:
                        messages.append(ChatMessageTool(content=error, tool_call_id=call.id, function=call.function,
                            error=ToolCallError(type='parsing', message=error)))
                    value = dict(tool='invalid_response', arguments={})
                else:
                    value = dict(tool=calls[0].function, arguments=calls[0].arguments) if calls else None
                try:
                    observation = await action(identity, value)
                except InterruptedError:
                    ended = competition.ended_observation()
                    if ended is None:
                        raise
                    if calls and not error:
                        messages.append(ChatMessageTool(content=json.dumps(ended), tool_call_id=calls[0].id,
                                                        function=calls[0].function))
                    return
                if calls and not error and observation is not None:
                    messages.append(ChatMessageTool(content=json.dumps(observation), tool_call_id=calls[0].id,
                                                    function=calls[0].function))
                elif error and isinstance(observation, dict) and 'notice' in observation:
                    messages[-1] = messages[-1].model_copy(update={'content': f"{error}\n{observation['notice']}"})
        except BaseException as exc:
            competition.stop(TimeoutError('continuation cancelled') if isinstance(exc, asyncio.CancelledError) else exc)
            raise

    workers = [asyncio.create_task(participant(a)) for a in histories]
    try:
        _, pending = await asyncio.wait(workers, return_when=asyncio.FIRST_EXCEPTION)
        for worker in pending:
            worker.cancel()
        outcomes = await asyncio.gather(*workers, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
    finally:
        for worker in workers:
            if not worker.done():
                worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


def run(folder, env_file=None):
    """One attempt only. Failures retain evidence and require a new prepared folder."""
    import inspect_ai
    from inspect_ai import Task, eval as inspect_eval
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ChatMessage, GenerateConfig, get_model
    from inspect_ai.solver import solver
    from inspect_ai.tool import ToolInfo, ToolParams
    from pydantic import TypeAdapter
    from bug_competition.adapters.inspect.inspect_task import require_single_tool_call
    from bug_competition.harness.core import TOOL_SCHEMAS
    from bug_competition.harness.credentials import load_host_credentials
    from bug_competition.harness.adapters import BraveSearch, OpenAISearch
    from bug_competition.harness.oracle import DockerOracle
    from bug_competition.grader.grader import FinalOracle, grade_episode

    folder = Path(folder).resolve()
    config, records, state, saved_histories = validate_bundle(folder)
    tools = [ToolInfo.model_validate(t) for t in config['contract']['tools']]
    for tool in tools:
        if tool.name not in TOOL_SCHEMAS or tool.parameters != ToolParams.model_validate(TOOL_SCHEMAS[tool.name]):
            raise ValueError(f'Archived tool schema is unsupported: {tool.name}')
    # O_EXCL is the one-attempt lock; even failed preflights cannot overwrite a prior attempt.
    with (folder / 'invocation.json').open('x') as stream:
        json.dump(dict(status='starting', model=config['contract']['model'], image=config['image'],
            participants=len(saved_histories), action_limit_per_participant=config['turn_limit'],
            actions_remaining_notices=config['notices'], inspect_version=inspect_ai.__version__,
            parent=config['parent'], parent_sequence=config['source_sequence'], pid=os.getpid()), stream, indent=2)
    stage = Path(tempfile.mkdtemp(prefix='mosslight-branch-'))
    competition = executor = None
    histories = {a: TypeAdapter(list[ChatMessage]).validate_python(m) for a, m in saved_histories.items()}
    success = False
    try:
        if env_file:
            load_host_credentials(Path(env_file))
        if config['contract']['model'].startswith('anthropic/') and not os.environ.get('ANTHROPIC_API_KEY'):
            raise ValueError('Anthropic credential unavailable; set host environment or --env-file')
        image_result = process(['docker', 'image', 'inspect', '--format', '{{.Id}}', config['image']], 30)
        if image_result['exit_code'] or not image_result['output'].strip().startswith('sha256:'):
            raise ValueError('Configured Docker image is unavailable')
        image_id = image_result['output'].strip()
        executor = DockerShell(image_id)
        oracle = DockerOracle(DEFAULT_MANIFEST, image_id, probes=read_json(folder / 'live_probes.json'))
        checked = check_historical_verdicts(oracle, folder / 'checkpoint', state, config['grading_seconds'])
        write_json(folder / 'preflight.json', dict(historical_snapshots_checked=checked, verdicts_match=True,
                                                  image_id=image_id, oracle_origin=config['oracle_origin']))
        tree = stage / 'shared'
        shutil.copytree(folder / 'checkpoint/snapshots' / str(len(state['snapshot_hashes']) - 1), tree)
        search = BraveSearch() if os.environ.get('BRAVE_SEARCH_API_KEY') else OpenAISearch()
        prompt = next(iter(histories.values()))[0].content
        competition = ResumedCompetition(tree, stage / 'protected', executor, oracle,
            {a: ScriptedAgent([]) for a in histories}, weights=config['weights'], search=search,
            prompt=prompt, relevance={k: set(v) for k, v in config['relevance'].items()})
        competition.restore(folder / 'checkpoint', records, state, config)

        @solver
        def resumed_solver():
            async def solve(task_state, generate):
                model = get_model()
                require_single_tool_call(model)
                try:
                    await continue_participants(competition, histories, model.generate, tools,
                                                GenerateConfig(**config['contract']['config']))
                finally:
                    competition.finish()
                    task_state.messages = histories[next(iter(histories))]
                    task_state.metadata['competition_conversations'] = {
                        a: [m.model_dump(mode='json') for m in h] for a, h in histories.items()}
                task_state.completed = True
                return task_state
            return solve

        logs = inspect_eval(Task(dataset=[Sample(input=prompt, id='competition')], solver=resumed_solver()),
            model=config['contract']['model'], model_args={'max_retries': 0}, log_dir=str(folder / 'inspect'),
            retry_on_error=0, max_retries=0, epochs=1, display='plain')
        if not logs or any(log.status != 'success' for log in logs):
            raise ValueError('Inspect continuation did not complete successfully; preserved partial evidence')
        final_oracle = FinalOracle(image=image_id)
        final_oracle.probes = read_json(folder / 'grading_probes.json')
        final_oracle.covered = {p['id'] for p in final_oracle.probes}
        graded = grade_episode(competition.protected, oracle=final_oracle, seconds=config['grading_seconds'])
        write_json(folder / 'independent_grade.json', graded)
        success = graded['adjudication_complete'] and graded['complete_submission']
        if not success:
            raise ValueError('Independent grading incomplete; no completed-result claim permitted')
        return dict(status='complete', points=graded['points'], output=str(folder))
    except BaseException as exc:
        message = str(exc)
        for key, secret in os.environ.items():
            if secret and any(word in key for word in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
                message = message.replace(secret, '[REDACTED]')
        write_json(folder / 'failure.json', dict(error_type=type(exc).__name__, message=message))
        raise
    finally:
        try:
            if competition is not None:
                competition.finish()
            elif executor is not None:
                executor.close()
        finally:
            write_json(folder / 'trajectories.json', [dict(sample_id='competition', conversations={
                a: [m.model_dump(mode='json') for m in h] for a, h in histories.items()})])
            if (stage / 'protected').exists():
                destination = folder / 'episode_evidence' / stage.name
                shutil.copytree(stage, destination)
            # Only remove our neutral staging directory after a successful evidence copy.
            shutil.rmtree(stage)
            invocation = read_json(folder / 'invocation.json')
            invocation.update(status='complete' if success else 'failed', finished_unix=time.time())
            write_json(folder / 'invocation.json', invocation)
