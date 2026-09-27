"""Prepare and run a new continuation from an authenticated Mosslight ledger prefix.

Preparation is offline. Execution is explicit and never appends to the source run.
Use python -B -m bug_competition.host_only.tools.branch_rollout --help.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

from bug_competition.harness.core import canonical, tree_hash, recent_action, repair_summary, work_board
from bug_competition.grader.attribution import ATTRIBUTION_POLICY, manifest_files
from bug_competition.grader.weights import DEFAULT_MANIFEST, manifest_weights

REPO = Path(__file__).resolve().parents[3]
FORMAT = 1


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_files():
    """Pin host behavior, probes, and adapter, not the participant's mutable source."""
    files = []
    for folder in ('harness', 'grader', 'adapters/inspect'):
        files.extend((REPO / 'bug_competition' / folder).glob('*.py'))
    files.extend((REPO / 'bug_competition/host_only/tools').glob('branch_*.py'))
    files.extend((REPO / 'bug_competition/grader').rglob('*.json'))
    files.append(DEFAULT_MANIFEST)
    return {str(p.relative_to(REPO)): sha(p) for p in sorted(set(files))}


def protected_path(run):
    choices = list(Path(run).glob('episode_evidence/*/protected/events.jsonl'))
    if len(choices) != 1:
        raise ValueError('Expected exactly one copied episode ledger in the source run')
    return choices[0].parent


def records_from(path):
    records, previous = [], '0' * 64
    for number, line in enumerate(Path(path).read_text().splitlines()):
        record = json.loads(line)
        payload = {k: v for k, v in record.items() if k != 'hash'}
        if (record.get('sequence') != number or record.get('previous') != previous or
                hashlib.sha256(canonical(payload).encode()).hexdigest() != record.get('hash')):
            raise ValueError(f'Ledger integrity failure at sequence {number}')
        previous = record['hash']
        records.append(record)
    if not records or records[0].get('type') != 'baseline':
        raise ValueError('A completed baseline is required')
    if records[0].get('attribution_policy') != ATTRIBUTION_POLICY:
        raise ValueError('Unsupported attribution policy')
    return records


def scan_prefix(records, participants, sequence, weights=None):
    if not 0 <= sequence < len(records):
        raise ValueError('Sequence does not exist')
    baseline = records[0]['oracle']
    if not baseline or any(type(v) is not bool for v in baseline.values()):
        raise ValueError('Invalid baseline verdict')
    state = dict(baseline=baseline.copy(), current=baseline.copy(), owners={},
                 turns_used=dict.fromkeys(participants, 0), claims=[], recent=[],
                 last_observation={}, finished=[], snapshot_hashes=[records[0]['tree']],
                 snapshot_verdicts=[baseline.copy()], responses={a: [] for a in participants})
    pending, rejected = {}, {}
    for e in records[1:sequence + 1]:
        typ, actor = e['type'], e.get('agent')
        if actor is not None and actor not in participants:
            raise ValueError('Unknown ledger participant')
        if typ == 'response_rejected':
            rejected[actor] = e['error']
        elif typ == 'action_started':
            if actor in state['finished'] or any(x['agent'] == actor for x in pending.values()):
                raise ValueError('Invalid overlapping actor actions')
            pending[e['action_id']] = e
        elif typ == 'action_completed':
            started = pending.pop(e['action_id'], None)
            if started is None or started['agent'] != actor or started['action'] != e['action']:
                raise ValueError('Action start/completion mismatch')
            if e['before'] != state['snapshot_hashes'][-1]:
                raise ValueError('Discontinuous committed tree')
            if e['before'] != e['after']:
                for bug, value in e.get('oracle_transitions', {}).items():
                    if bug not in baseline or type(value) is not bool:
                        raise ValueError('Invalid oracle transition')
                    state['current'][bug] = value
                # The ledger records additions/changes, not owners removed on regression.
                state['owners'] = {bug: owner for bug, owner in state['owners'].items()
                                   if state['current'][bug] and not baseline[bug]}
                state['owners'].update(e.get('ownership_transfers', {}))
                state['snapshot_hashes'].append(e['after'])
                state['snapshot_verdicts'].append(state['current'].copy())
            elif e.get('oracle_transitions') or e.get('ownership_transfers'):
                raise ValueError('Transitions without a committed tree change')
            action = e['action']
            if action['tool'] == 'claim' and e.get('rejection') is None:
                state['claims'].append(dict(agent=actor, provisional=True,
                    **{k: v for k, v in action['arguments'].items()
                       if k in ('summary', 'reproduction', 'files')}))
            if weights is not None and e.get('rejection') is None and action['tool'] in ('claim', 'status'):
                expected = (dict(recorded=True, provisional=True,
                                 leaderboard=repair_summary(actor, state['owners'], state['current'], weights))
                            if action['tool'] == 'claim' else
                            work_board(actor, participants, state['owners'], state['current'], weights,
                                       state['claims'], state['recent']))
                recorded = {k: v for k, v in e['observation'].items() if k != 'notice'}
                if recorded != expected:
                    raise ValueError(f'Archived scoring/board protocol differs at sequence {e["sequence"]}; '
                                     'a version-specific continuation adapter is required')
            state['turns_used'][actor] += 1
            state['recent'].append(recent_action(actor, action['tool']))
            state['last_observation'][actor] = e['observation']
            state['responses'][actor].append(dict(response=started.get('provider_response'),
                observation=e['observation'], error=rejected.pop(actor, None)))
        elif typ == 'agent_finished':
            state['finished'].append(actor)
            state['responses'][actor].append(dict(response=e.get('provider_response'),
                                                  observation=None, error=None))
        elif typ in ('status_viewed', 'branch_started'):
            pass
        else:
            raise ValueError(f'Cannot resume across {typ} at sequence {e["sequence"]}')
    if pending or rejected:
        raise ValueError('Cut has an unfinished tool action or rejected response; choose a completed boundary')
    if any(owner not in participants or bug not in baseline or not state['current'][bug] or baseline[bug]
           for bug, owner in state['owners'].items()):
        raise ValueError('Invalid credited owner')
    return state


def conversation_prefixes(conversations, state):
    """Retain exact archived messages, including opaque payloads and tool-call IDs."""
    result = {}
    for actor, steps in state['responses'].items():
        history = conversations[actor]
        if not history or history[0]['role'] != 'user':
            raise ValueError('Expected the original user prompt at the start')
        index = 1
        for step in steps:
            response = step['response']
            try:
                expected = response['choices'][0]['message']
            except (KeyError, IndexError, TypeError):
                raise ValueError('Missing full provider response; summaries alone cannot resume') from None
            if index >= len(history) or history[index] != expected:
                raise ValueError(f'{actor}: conversation/ledger assistant mismatch')
            index += 1
            calls = expected.get('tool_calls') or []
            if step['observation'] is None:
                if calls:
                    raise ValueError('Finished response contains an unresolved tool call')
                continue
            if not calls:
                raise ValueError('Completed action lacks tool calls')
            for position, call in enumerate(calls):
                if index >= len(history):
                    raise ValueError('Missing tool result')
                message = history[index]
                if (message['role'] != 'tool' or message.get('tool_call_id') != call['id'] or
                        message.get('function') != call['function']):
                    raise ValueError('Tool result identity mismatch')
                if step['error']:
                    expected_text = step['error']
                    if position == len(calls) - 1 and 'notice' in step['observation']:
                        expected_text += '\n' + step['observation']['notice']
                    if message['content'] != expected_text:
                        raise ValueError('Rejected-response result mismatch')
                elif len(calls) != 1 or json.loads(message['content']) != step['observation']:
                    raise ValueError('Tool observation differs from authenticated ledger')
                index += 1
        result[actor] = copy.deepcopy(history[:index])
    return result


def archived_contract(run):
    """Read the actual tools and generation settings; never infer them from today's code."""
    saved = Path(run) / 'branch.json'
    if saved.exists():
        return read_json(saved)['contract']
    from inspect_ai.log import read_eval_log
    logs = list((Path(run) / 'inspect').glob('*.eval'))
    if len(logs) != 1:
        raise ValueError('Expected one Inspect log to recover original tools/config')
    log = read_eval_log(str(logs[0]))
    contract = None
    for sample in log.samples or []:
        for event in sample.events:
            if event.event != 'model':
                continue
            value = dict(model=event.model,
                         tools=[t.model_dump(mode='json') for t in event.tools],
                         config=event.config.model_dump(mode='json', exclude_none=True))
            if contract is None:
                contract = value
            elif contract != value:
                raise ValueError('Model/tool/config changes within source run require a custom continuation')
    if contract is None:
        raise ValueError('No archived model contract')
    return contract


def load_source(run, sequence=None, after=None):
    run = Path(run).resolve()
    protected = protected_path(run)
    records = records_from(protected / 'events.jsonl')
    trajectories = read_json(run / 'trajectories.json')
    if len(trajectories) != 1:
        raise ValueError('Select a run with exactly one competition sample')
    conversations = trajectories[0]['conversations']
    if after is not None:
        actor, number = after.split(':')
        number = int(number)
        matches = [e for e in records if e['type'] == 'action_completed' and e['agent'] == actor]
        if number < 1 or number > len(matches):
            raise ValueError('Actor/action does not exist')
        sequence = matches[number - 1]['sequence']
    if sequence is None:
        raise ValueError('Choose --sequence or --after ACTOR:ACTION')
    state = scan_prefix(records, list(conversations), sequence)
    histories = conversation_prefixes(conversations, state)
    for index, digest in enumerate(state['snapshot_hashes']):
        if tree_hash(protected / 'snapshots' / str(index)) != digest:
            raise ValueError(f'Snapshot {index} integrity failure')
    return run, protected, records[:sequence + 1], state, histories


def preview(state, sequence, weights=None):
    weights = weights or manifest_weights()
    return dict(sequence=sequence, completed_actions=state['turns_used'],
                snapshot=len(state['snapshot_hashes']) - 1, tree_hash=state['snapshot_hashes'][-1],
                finished=state['finished'], provisional_points={
                    actor: sum(weights[bug] for bug, owner in state['owners'].items()
                               if owner == actor and state['current'][bug])
                    for actor in state['turns_used']},
                boundary='completed tools; pending model generations restart from exact prefixes')


def available_cuts(run, around=None, limit=12):
    """List safe global boundaries; no provider or Docker calls and no history edits."""
    if limit < 1:
        raise ValueError('Cut limit must be positive')
    records = records_from(protected_path(run) / 'events.jsonl')
    trajectories = read_json(Path(run) / 'trajectories.json')
    if len(trajectories) != 1:
        raise ValueError('Select a single-sample run')
    participants = list(trajectories[0]['conversations'])
    cuts = []
    for e in records:
        if e['type'] not in ('baseline', 'action_completed', 'agent_finished'):
            continue
        try:
            state = scan_prefix(records, participants, e['sequence'])
        except ValueError:
            continue
        cuts.append(dict(sequence=e['sequence'], completed_actions=state['turns_used'],
                         snapshot=len(state['snapshot_hashes']) - 1, finished=state['finished']))
    if around is not None:
        cuts = sorted(sorted(cuts, key=lambda e: (abs(e['sequence'] - around), e['sequence']))[:limit],
                      key=lambda e: e['sequence'])
    else:
        cuts = cuts[-limit:]
    return cuts


def prepare(run, output, *, sequence=None, after=None, notices=None, turn_limit=None,
            oracle_policy='require-saved', seconds=5400, grading_seconds=3600, probes_from=None, image=None):
    import inspect_ai
    from pydantic import TypeAdapter
    from inspect_ai.model import ChatMessage
    run, protected, records, state, histories = load_source(run, sequence, after)
    invocation = read_json(run / 'invocation.json')
    contract = archived_contract(run)
    # Structural validation only: the future provider must also accept the saved opaque payloads.
    adapter = TypeAdapter(list[ChatMessage])
    for history in histories.values():
        adapter.validate_python(history)
    weights, relevance = manifest_weights(), manifest_files()
    if set(state['baseline']) != set(weights):
        raise ValueError('Current manifest differs from the source defect set')
    scan_prefix(records, list(histories), len(records) - 1, weights=weights)
    previous_limit = invocation['action_limit_per_participant']
    limit = previous_limit if turn_limit is None else turn_limit
    if type(limit) is not int or limit < max(state['turns_used'].values()):
        raise ValueError('Total turn limit cannot precede already-completed actions')
    if not any(a not in state['finished'] and n < limit for a, n in state['turns_used'].items()):
        raise ValueError('No unfinished participant has actions remaining')
    if seconds <= 0 or grading_seconds <= 0:
        raise ValueError('Time budgets must be positive')
    original_notices = invocation.get('actions_remaining_notices')
    if notices is None and original_notices is None:
        raise ValueError('Original countdown unavailable; provide --notices explicitly')
    chosen_notices = list(original_notices if notices is None else notices)
    if any(type(n) is not int or n <= 0 for n in chosen_notices):
        raise ValueError('Notice values must be positive remaining-action counts')
    probe_file = (Path(probes_from) if probes_from is not None else run) / 'live_probes.json'
    if probe_file.exists():
        probes = read_json(probe_file)
        origin = 'shared branch probes; historical replay required' if probes_from else 'saved'
    elif probes_from is not None:
        raise ValueError('Shared branch probe file is missing')
    elif oracle_policy == 'fresh-checked':
        from bug_competition.grader.grader import FinalOracle
        probes, origin = FinalOracle(runner=object()).probes, 'replacement; historical replay required'
    else:
        raise ValueError('Original oracle inputs were not saved. Select --oracle-policy fresh-checked '
                         'to pin replacement probes and verify every historical snapshot before model calls.')
    from bug_competition.grader.grader import FinalOracle
    grading_file = Path(probes_from) / 'grading_probes.json' if probes_from else None
    grading_probes = read_json(grading_file) if grading_file else FinalOracle(runner=object()).probes
    for collection in (probes, grading_probes):
        if len(collection) != len(weights) or {p['id'] for p in collection} != set(weights):
            raise ValueError('Probe set must cover every eligible defect exactly once')
    output = Path(output).resolve()
    if output == run or run in output.parents:
        raise ValueError('Branch output must be outside the source evidence folder')
    if output.exists():
        raise ValueError('Output already exists; choose a new folder')
    config = dict(format=FORMAT, parent=str(run), source_sequence=records[-1]['sequence'],
                  parent_audit_head=records[-1]['hash'], contract=contract,
                  inspect_version=inspect_ai.__version__, source_inspect_version=invocation.get('inspect_version'),
                  python_version=sys.version.split()[0], runtime_files=runtime_files(),
                  image=image or invocation.get('image', 'mosslight-tools:local'),
                  original_turn_limit=previous_limit, turn_limit=limit,
                  original_notices=original_notices, notices=sorted(set(chosen_notices), reverse=True),
                  seconds=seconds, grading_seconds=grading_seconds, oracle_origin=origin,
                  model_generations_in_flight='discarded and regenerated; tool-in-flight cuts refused',
                  weights=weights, relevance={k: sorted(v) for k, v in relevance.items()},
                  checkpoint=preview(state, records[-1]['sequence'], weights))
    output.mkdir(parents=True)
    try:
        checkpoint = output / 'checkpoint'
        checkpoint.mkdir()
        (checkpoint / 'events.jsonl').write_text(''.join(canonical(e) + '\n' for e in records))
        for index in range(len(state['snapshot_hashes'])):
            shutil.copytree(protected / 'snapshots' / str(index), checkpoint / 'snapshots' / str(index))
        write_json(checkpoint / 'histories.json', histories)
        write_json(output / 'live_probes.json', probes)
        write_json(output / 'grading_probes.json', grading_probes)
        config['checkpoint_files'] = {'events.jsonl': sha(checkpoint / 'events.jsonl'),
                                      'histories.json': sha(checkpoint / 'histories.json')}
        config['probe_files'] = {name: sha(output / name)
                                for name in ('live_probes.json', 'grading_probes.json')}
        write_json(output / 'branch.json', config)
    except BaseException:
        # Keep any partial output inspectable; never retry into or overwrite it.
        (output / 'PREPARATION_FAILED.txt').write_text('Preparation incomplete; choose a fresh output directory.\n')
        raise
    return config


def validate_bundle(folder):
    import inspect_ai
    folder = Path(folder).resolve()
    config = read_json(folder / 'branch.json')
    if config['format'] != FORMAT or runtime_files() != config['runtime_files']:
        raise ValueError('Runtime changed since preparation; prepare a fresh branch')
    if inspect_ai.__version__ != config['inspect_version'] or sys.version.split()[0] != config['python_version']:
        raise ValueError('Python/Inspect version changed since preparation')
    for name, digest in config['checkpoint_files'].items():
        if sha(folder / 'checkpoint' / name) != digest:
            raise ValueError(f'Checkpoint content changed: {name}')
    for name, digest in config['probe_files'].items():
        if sha(folder / name) != digest:
            raise ValueError('Pinned probe inputs changed')
    records = records_from(folder / 'checkpoint/events.jsonl')
    if records[-1]['hash'] != config['parent_audit_head']:
        raise ValueError('Parent audit head mismatch')
    histories = read_json(folder / 'checkpoint/histories.json')
    state = scan_prefix(records, list(histories), len(records) - 1, weights=config['weights'])
    if conversation_prefixes(histories, state) != histories:
        raise ValueError('Checkpoint contains future conversation messages')
    for index, digest in enumerate(state['snapshot_hashes']):
        if tree_hash(folder / 'checkpoint/snapshots' / str(index)) != digest:
            raise ValueError(f'Checkpoint snapshot {index} changed')
    if set(config['weights']) != set(state['baseline']):
        raise ValueError('Checkpoint manifest mismatch')
    if (config['weights'] != manifest_weights() or
            config['relevance'] != {k: sorted(v) for k, v in manifest_files().items()}):
        raise ValueError('Checkpoint attribution configuration changed')
    return config, records, state, histories


def parse_notices(text):
    if text == 'none':
        return []
    if text == 'countdown':
        return list(range(20, 0, -1))
    if text == '20-then-10':
        return [20, *range(10, 0, -1)]
    try:
        numbers = [int(x) for x in text.split(',')]
        if not numbers or any(n <= 0 for n in numbers):
            raise ValueError()
        return numbers
    except ValueError:
        raise argparse.ArgumentTypeError('Use 20-then-10, countdown, none, or positive counts such as 20,10') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('cuts', help='List completed-tool boundaries, optionally near an event')
    p.add_argument('source', type=Path)
    p.add_argument('--around', type=int)
    p.add_argument('--limit', type=int, default=12)
    for verb in ('inspect', 'prepare'):
        p = sub.add_parser(verb)
        p.add_argument('source', type=Path)
        choice = p.add_mutually_exclusive_group(required=True)
        choice.add_argument('--sequence', type=int)
        choice.add_argument('--after', help='Global cut after ACTOR:ACTION, e.g. A:130')
        if verb == 'prepare':
            p.add_argument('--output', type=Path, required=True)
            p.add_argument('--notices', type=parse_notices,
                           help='20-then-10, countdown (20..1), none, or comma-separated counts; default preserves source')
            p.add_argument('--turn-limit', type=int, help='Total actions per actor, including the prefix')
            p.add_argument('--oracle-policy', choices=['require-saved', 'fresh-checked'], default='require-saved')
            p.add_argument('--probes-from', type=Path, help='Reuse live/grading probes from a prepared control branch')
            p.add_argument('--image', help='Explicit tool image tag or immutable ID; default is the archived image')
            p.add_argument('--seconds', type=float, default=5400)
            p.add_argument('--grading-seconds', type=float, default=3600)
    p = sub.add_parser('validate')
    p.add_argument('branch', type=Path)
    p = sub.add_parser('run', help='Run a prepared branch (Docker + paid model calls)')
    p.add_argument('branch', type=Path)
    p.add_argument('--execute', action='store_true', help='Required to start actual execution')
    p.add_argument('--env-file', type=Path, help='Optional host credential file; never copied into evidence')
    args = parser.parse_args(argv)
    try:
        if args.command == 'cuts':
            result = available_cuts(args.source, args.around, args.limit)
        elif args.command == 'inspect':
            _, _, records, state, _ = load_source(args.source, args.sequence, args.after)
            result = preview(state, records[-1]['sequence'])
        elif args.command == 'prepare':
            config = prepare(args.source, args.output, sequence=args.sequence, after=args.after,
                             notices=args.notices, turn_limit=args.turn_limit,
                             oracle_policy=args.oracle_policy, seconds=args.seconds,
                             grading_seconds=args.grading_seconds, probes_from=args.probes_from, image=args.image)
            result = dict(prepared=str(args.output.resolve()), checkpoint=config['checkpoint'],
                          notices=config['notices'], turn_limit=config['turn_limit'],
                          oracle_origin=config['oracle_origin'], model_calls=0)
        elif args.command == 'validate':
            config, _, _, _ = validate_bundle(args.branch)
            result = dict(valid=True, checkpoint=config['checkpoint'], model_calls=0)
        else:
            if not args.execute:
                raise ValueError('Execution requires --execute; inspect/prepare/validate are offline')
            from bug_competition.host_only.tools.branch_runtime import run
            result = run(args.branch, env_file=args.env_file)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f'branch_rollout: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
