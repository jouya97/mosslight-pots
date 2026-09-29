"""Prepare and run a new continuation from an authenticated Mosslight ledger prefix.

Preparation is offline. Execution is explicit and never appends to the source run.
Shell actions default to 180 seconds (--shell-seconds), capped by the remaining
contest budget (--seconds). An action timeout discards its workspace; a global
deadline or container cleanup failure still stops the contest.
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

from bug_competition.harness.core import (canonical, tree_hash, recent_action, repair_summary, work_board,
    STATUS_CALLER_ONLY, STATUS_PROTOCOLS, validate_status_protocol, SHELL_SECONDS, validate_shell_seconds)
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


def text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def opening_content(history):
    if not history or history[0].get('role') != 'user' or not isinstance(history[0].get('content'), str):
        raise ValueError('Expected a text opening user prompt')
    return history[0]['content']


def require_canonical_openings(histories):
    """Archived histories remain readable; only the canonical experiment can resume."""
    from bug_competition.task import PROMPT
    if not histories:
        raise ValueError('Continuation requires participant histories')
    for actor, history in histories.items():
        if opening_content(history) != PROMPT:
            raise ValueError(f'{actor}: historical opening prompt differs from PROMPT; '
                             'start a fresh run instead of rewriting archived context')


def provider_connection(model):
    """The supported provider transport settings, kept separate from generation config."""
    if model == 'anthropic/claude-opus-5-5':
        return dict(model_args={'max_retries': 0}, model_base_url='https://api.anthropic.com')
    if model == 'openrouter/anthropic/claude-opus-5.5':
        return dict(model_args={'max_retries': 0, 'stream': False, 'reasoning_enabled': True},
                    model_base_url='https://openrouter.ai/api/v1')
    if model.startswith('mock'):
        return dict(model_args={'max_retries': 0}, model_base_url=None)
    raise ValueError('Unsupported continuation model')


def reasoning_omission_counts(records, histories):
    """Recover the outbound-context policy without removing anything from saved history."""
    counts = {}
    for event in records:
        if event['type'] == 'historical_reasoning_omitted':
            counts = dict(event['through_message_counts'])
    validate_reasoning_omission(histories, counts)
    return counts


def validate_reasoning_omission(histories, counts):
    if counts and set(counts) != set(histories):
        raise ValueError('Reasoning omission must identify every participant')
    for actor, count in counts.items():
        if type(count) is not int or not 0 <= count <= len(histories[actor]):
            raise ValueError('Reasoning omission exceeds the saved conversation prefix')


def outbound_history(history, through=0):
    """Omit only historical reasoning blocks; keep text, tool calls and new reasoning."""
    if type(through) is not int or not 0 <= through <= len(history):
        raise ValueError('Invalid reasoning omission boundary')
    messages = copy.deepcopy(history)
    for message in messages[:through]:
        if message.get('role') == 'assistant' and isinstance(message.get('content'), list):
            message['content'] = [block for block in message['content'] if block.get('type') != 'reasoning']
    return messages


OPENROUTER_REASONING_PREFIX = 'reasoning-details://'
PROVIDER_MODEL_SWITCH = {'openrouter/anthropic/claude-opus-5.5': 'anthropic/claude-opus-5-5'}


def convert_openrouter_history(history, through):
    """Unwrap Inspect transport envelopes only; opaque native signatures are never decoded.

    Conversion is outbound-only and bounded to the archived OpenRouter prefix.
    Unknown/unsigned blocks fail closed rather than becoming text or disappearing.
    """
    if type(through) is not int or not 0 <= through <= len(history):
        raise ValueError('Invalid provider conversion boundary')
    changed = copy.deepcopy(history)
    for index, message in enumerate(changed):
        content = message.get('content')
        if not isinstance(content, list):
            continue
        blocks = []
        for block in content:
            if block.get('type') != 'reasoning':
                blocks.append(block)
                continue
            signature = block.get('signature') or ''
            wrapped = isinstance(signature, str) and signature.startswith(OPENROUTER_REASONING_PREFIX)
            if index >= through:
                if wrapped:
                    raise ValueError('OpenRouter reasoning outside the audited conversion boundary')
                blocks.append(block)
                continue
            if message.get('role') != 'assistant' or not wrapped:
                raise ValueError('Expected wrapped OpenRouter assistant reasoning in conversion prefix')
            try:
                details = json.loads(signature[len(OPENROUTER_REASONING_PREFIX):])
            except (ValueError, TypeError):
                raise ValueError('Invalid OpenRouter reasoning envelope') from None
            if not isinstance(details, list) or not details:
                raise ValueError('Empty or unsupported OpenRouter reasoning envelope')
            for detail in details:
                if not isinstance(detail, dict) or detail.get('format') != 'anthropic-claude-v1':
                    raise ValueError('Unsupported native reasoning format')
                kind = detail.get('type')
                if kind == 'reasoning.text':
                    if not isinstance(detail.get('text'), str) or not isinstance(detail.get('signature'), str) or not detail['signature']:
                        raise ValueError('Unsigned or malformed OpenRouter reasoning text')
                    blocks.append(dict(type='reasoning', summary=detail['text'],
                                       reasoning=detail['signature'], redacted=True))
                elif kind == 'reasoning.encrypted':
                    if not isinstance(detail.get('data'), str) or not detail['data']:
                        raise ValueError('Malformed redacted OpenRouter reasoning')
                    blocks.append(dict(type='reasoning', reasoning=detail['data'],
                                       signature=detail['data'], redacted=True))
                else:
                    raise ValueError('Unsupported OpenRouter reasoning detail type')
        message['content'] = blocks
    return changed


def inherited_provider_conversion(records, histories):
    conversion = None
    for event in records:
        if event['type'] == 'provider_changed':
            conversion = copy.deepcopy(event['reasoning_conversion'])
    if conversion:
        conversion_audit(histories, conversion)
    return conversion


def conversion_audit(histories, conversion):
    if (conversion.get('source_model') not in PROVIDER_MODEL_SWITCH or
            conversion.get('target_model') != PROVIDER_MODEL_SWITCH[conversion['source_model']]):
        raise ValueError('Unsupported provider conversion model pair')
    counts = conversion.get('through_message_counts', {})
    validate_reasoning_omission(histories, counts)
    if set(counts) != set(histories):
        raise ValueError('Provider conversion must identify every actor')
    return {actor: dict(through_messages=counts[actor],
                source_sha256=text_sha(canonical(history[:counts[actor]])),
                outbound_sha256=text_sha(canonical(convert_openrouter_history(history, counts[actor])[:counts[actor]])),
                reasoning_blocks=sum(b.get('type') == 'reasoning' for m in history[:counts[actor]]
                    if isinstance(m.get('content'), list) for b in m['content']))
            for actor, history in histories.items()}


def provider_configuration(source_contract, histories, records, provider=None):
    """Only the explicit same-model OpenRouter -> native Anthropic switch is supported."""
    contract = copy.deepcopy(source_contract)
    connection = provider_connection(contract['model'])
    for key, value in connection.items():
        if key in contract and contract[key] != value:
            raise ValueError(f'Archived provider setting is unsupported: {key}')
        contract[key] = value
    conversion = inherited_provider_conversion(records, histories)
    intervention = None
    if provider is not None:
        source = contract['model']
        if provider != 'anthropic' or source not in PROVIDER_MODEL_SWITCH or conversion:
            raise ValueError('Provider switch requires an unconverted OpenRouter Opus 5.5 source')
        contract['model'] = PROVIDER_MODEL_SWITCH[source]
        contract.update(provider_connection(contract['model']))
        conversion = dict(source_model=source, target_model=contract['model'],
                          through_message_counts={a: len(h) for a, h in histories.items()})
        intervention = dict(type='same_model_provider_switch', provider=provider,
                            source_model=source, target_model=contract['model'])
    if conversion and contract['model'] != conversion['target_model']:
        raise ValueError('Inherited provider conversion does not match current model')
    audit = conversion_audit(histories, conversion) if conversion else None
    return contract, intervention, conversion, audit


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
    state = dict(status_protocol=validate_status_protocol(records[0].get('status_protocol', STATUS_CALLER_ONLY)),
                 baseline=baseline.copy(), current=baseline.copy(), owners={},
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
                                       state['claims'], state['recent'], state['status_protocol']))
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
        elif typ == 'status_protocol_changed':
            if pending or e.get('previous_protocol') != state['status_protocol']:
                raise ValueError('Invalid status protocol transition')
            state['status_protocol'] = validate_status_protocol(e.get('status_protocol'))
        elif typ in ('status_viewed', 'branch_started', 'opening_prompt_replaced', 'historical_reasoning_omitted', 'provider_changed'):
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
    invocation = read_json(Path(run) / 'invocation.json')
    connection = provider_connection(contract['model'])
    for key, default in connection.items():
        contract[key] = invocation.get(key, default)
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
    if any(e['type'] in ('opening_prompt_replaced', 'historical_reasoning_omitted', 'provider_changed')
           and e['sequence'] > sequence for e in records):
        raise ValueError('Cut precedes an opening-prompt intervention recorded in later trajectories; '
                         'choose a cut after that event')
    state = scan_prefix(records, list(conversations), sequence)
    histories = conversation_prefixes(conversations, state)
    prompt_events = [e for e in records[:sequence + 1] if e['type'] == 'opening_prompt_replaced']
    if prompt_events:
        for actor, history in histories.items():
            if text_sha(opening_content(history)) != prompt_events[-1]['new_prompt_sha256']:
                raise ValueError(f'{actor}: trajectory opening prompt differs from audit event')
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
    minimum_sequence = max((e['sequence'] for e in records
                            if e['type'] in ('opening_prompt_replaced', 'historical_reasoning_omitted', 'provider_changed')), default=0)
    cuts = []
    for e in records:
        if e['sequence'] < minimum_sequence or e['type'] not in (
                'baseline', 'action_completed', 'agent_finished', 'opening_prompt_replaced', 'historical_reasoning_omitted', 'provider_changed'):
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
            oracle_policy='require-saved', seconds=5400, grading_seconds=3600, probes_from=None, image=None,
            status_protocol=None, provider=None, shell_seconds=SHELL_SECONDS):
    import inspect_ai
    from pydantic import TypeAdapter
    from inspect_ai.model import ChatMessage
    run, protected, records, state, histories = load_source(run, sequence, after)
    require_canonical_openings(histories)
    chosen_status_protocol = validate_status_protocol(state['status_protocol'] if status_protocol is None else status_protocol)
    invocation = read_json(run / 'invocation.json')
    source_contract = archived_contract(run)
    contract, provider_intervention, reasoning_conversion, provider_audit = provider_configuration(
        source_contract, histories, records, provider)
    # Structural validation only: the future provider must also accept the saved opaque payloads.
    adapter = TypeAdapter(list[ChatMessage])
    for history in histories.values():
        adapter.validate_python(history)
    omission = reasoning_omission_counts(records, histories)
    for actor, history in histories.items():
        adapter.validate_python(outbound_history(history, omission.get(actor, 0)))
    if reasoning_conversion and omission:
        raise ValueError('Provider conversion cannot omit historical reasoning')
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
    shell_seconds = validate_shell_seconds(shell_seconds)
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
    grading_file = (Path(probes_from) if probes_from else run) / 'grading_probes.json'
    if probes_from or grading_file.is_file():
        grading_probes = read_json(grading_file)
    else:
        grading_probes = FinalOracle(runner=object()).probes
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
                  source_contract=source_contract, provider_intervention=provider_intervention,
                  reasoning_conversion=reasoning_conversion, provider_conversion_audit=provider_audit,
                  inspect_version=inspect_ai.__version__, source_inspect_version=invocation.get('inspect_version'),
                  python_version=sys.version.split()[0], runtime_files=runtime_files(),
                  image=image or invocation.get('image', 'docker.io/library/mosslight-tools:local'),
                  original_turn_limit=previous_limit, turn_limit=limit,
                  original_notices=original_notices, notices=sorted(set(chosen_notices), reverse=True),
                  seconds=seconds, shell_seconds=shell_seconds, grading_seconds=grading_seconds, oracle_origin=origin,
                  model_generations_in_flight='discarded and regenerated; tool-in-flight cuts refused',
                  status_protocol=chosen_status_protocol,
                  intervention=None,
                  reasoning_omission=omission,
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
        if reasoning_conversion:
            write_json(output / 'provider_intervention.json', dict(source_contract=source_contract,
                effective_contract=contract, intervention=provider_intervention,
                reasoning_conversion=reasoning_conversion))
            write_json(output / 'provider_conversion_audit.json', provider_audit)
            config['provider_files'] = {name: sha(output / name) for name in
                ('provider_intervention.json', 'provider_conversion_audit.json')}
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
    validate_shell_seconds(config.get('shell_seconds', SHELL_SECONDS))
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
    for name, digest in config.get('provider_files', {}).items():
        if sha(folder / name) != digest:
            raise ValueError('Provider intervention evidence changed')
    records = records_from(folder / 'checkpoint/events.jsonl')
    if records[-1]['hash'] != config['parent_audit_head']:
        raise ValueError('Parent audit head mismatch')
    histories = read_json(folder / 'checkpoint/histories.json')
    require_canonical_openings(histories)
    if config.get('intervention'):
        raise ValueError('Opening prompt interventions are no longer launchable; prepare a canonical continuation')
    state = scan_prefix(records, list(histories), len(records) - 1, weights=config['weights'])
    if conversation_prefixes(histories, state) != histories:
        raise ValueError('Checkpoint contains future conversation messages')
    provider_intervention = config.get('provider_intervention')
    expected = provider_configuration(config.get('source_contract', config['contract']), histories, records,
        provider_intervention.get('provider') if provider_intervention else None)
    actual = (config['contract'], provider_intervention, config.get('reasoning_conversion'),
              config.get('provider_conversion_audit'))
    if actual != expected:
        raise ValueError('Provider conversion contract or boundary audit changed')
    if config.get('reasoning_conversion') and (config.get('intervention') or config.get('reasoning_omission')):
        raise ValueError('Provider conversion must preserve all original context and reasoning')
    validate_status_protocol(config.get('status_protocol', state['status_protocol']))
    omission = config.get('reasoning_omission', {})
    validate_reasoning_omission(histories, omission)
    inherited = reasoning_omission_counts(records, histories)
    if omission != inherited:
        raise ValueError('Historical reasoning policy changed')
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
            p.add_argument('--provider', choices=['anthropic'], help='Explicit same-model OpenRouter Opus 5.5 to direct Anthropic continuation')
            p.add_argument('--probes-from', type=Path, help='Reuse live/grading probes from a prepared control branch')
            p.add_argument('--image', help='Explicit tool image tag or immutable ID; default is the archived image')
            p.add_argument('--status-protocol', choices=STATUS_PROTOCOLS,
                           help='Future status feedback protocol; default inherits source, archives stay unchanged')
            p.add_argument('--shell-seconds', type=float, default=SHELL_SECONDS)
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
                             oracle_policy=args.oracle_policy, seconds=args.seconds, shell_seconds=args.shell_seconds,
                             grading_seconds=args.grading_seconds, probes_from=args.probes_from, image=args.image,
                             status_protocol=args.status_protocol, provider=args.provider)
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
