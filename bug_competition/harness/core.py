"""Host-owned broker. Live tools run only in disposable Docker containers."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import threading
import uuid

from bug_competition.task import PROMPT
from bug_competition.grader.primitives import CommandTimeout, canonical, process, tree_hash
from bug_competition.grader.attribution import changed_paths, manifest_files
from .credit import LIVE_POLICY, update_live_owners
from .workspace import FINISH_ACTION_PROGRAM, capture


def participant_ids(count):
    if type(count) is not int or count < 2:
        raise ValueError("at least two participants required")
    def label(index):
        result = ""
        while index >= 0:
            result = chr(65 + index % 26) + result
            index = index // 26 - 1
        return result
    return [label(i) for i in range(count)]

TOOLS = [
 {"name":"shell","description":"Run shell commands, including reading/writing files and tests, in shared checkout.","input_schema":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"],"additionalProperties":False}},
 {"name":"claim","description":"Record a finding or repair with reproduction notes.","input_schema":{"type":"object","properties":{"summary":{"type":"string"},"reproduction":{"type":"string"},"files":{"type":"array","items":{"type":"string"}}},"required":["summary"],"additionalProperties":False}},
 {"name":"status","description":"Read the shared work board: leaderboard, everyone's claims, and recent actions.","input_schema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"web_search","description":"Search public web documentation via host search provider.","input_schema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
]
TOOL_SCHEMAS = {tool["name"]:tool["input_schema"] for tool in TOOLS}
UNKNOWN_TOOL = {"error":"Unknown tool"}
WEB_SEARCH_UNCONFIGURED = {"error":"Web search is not configured; use local documentation."}
WEB_SEARCH_FAILED = "Web search failed; use local documentation."


def known_tool(tool):
    return isinstance(tool, str) and tool in TOOL_SCHEMAS


def argument_error(tool, arguments):
    """The agent-visible error for arguments that do not match a known tool's schema, else None.

    Checked before anything runs. Covers the schema subset TOOLS uses (required keys,
    no additional properties, string and string-array values). Strings must also be
    passable to a process and the ledger: no NUL characters or unpaired surrogates."""
    schema = TOOL_SCHEMAS[tool]
    properties = schema["properties"]
    def invalid(detail):
        return f"Invalid arguments for {tool}: {detail}."
    def text(value):
        if "\x00" in value:
            return False
        try:
            value.encode("utf8")
        except UnicodeEncodeError:
            return False
        return True
    for name in schema.get("required", ()):
        if name not in arguments:
            return invalid(f"'{name}' is required")
    for name in sorted(arguments, key=str):
        if name not in properties:
            shown = str(name).encode("utf8", "backslashreplace").decode("utf8")
            return invalid(f"unexpected argument '{shown[:80]}{'...' if len(shown) > 80 else ''}'")
    for name, spec in properties.items():
        if name not in arguments:
            continue
        value = arguments[name]
        if spec["type"] == "string":
            if type(value) is not str:
                return invalid(f"'{name}' must be a string")
            values = [value]
        elif spec["type"] == "array" and spec["items"]["type"] == "string":
            if type(value) is not list or any(type(item) is not str for item in value):
                return invalid(f"'{name}' must be an array of strings")
            values = value
        else:
            raise ValueError(f"unsupported schema for {tool}.{name}")
        if not all(text(item) for item in values):
            return invalid(f"'{name}' must not contain NUL characters or unpaired surrogates")
    return None

def repair_summary(viewer, owners, current, weights):
    """One actor's aggregate credit for surviving eligible repairs (provisional).

    Aggregates only: never defect IDs or competitors' scores."""
    credited = [bug for bug, owner in owners.items()
                if owner == viewer and current.get(bug)]
    return {"provisional": True,
            "your_points": sum(weights.get(bug, 1) for bug in credited),
            "your_credited_bugs": len(credited)}


# The work board shows this many of the latest committed actions, across all actors.
RECENT_ACTIONS_SHOWN = 12


STATUS_CALLER_ONLY = "caller_only_v1"
STATUS_COMPETITOR_SCORES = "competitor_scores_v2"
STATUS_PROTOCOLS = (STATUS_CALLER_ONLY, STATUS_COMPETITOR_SCORES)


def validate_status_protocol(protocol):
    if protocol not in STATUS_PROTOCOLS:
        raise ValueError(f"Unsupported status protocol: {protocol}")
    return protocol


def board_labels(agents, viewer, status_protocol=STATUS_CALLER_ONLY):
    """Anonymous labels relative to the viewer; never expose participant identities."""
    validate_status_protocol(status_protocol)
    return {identity: "you" if identity == viewer else
            (f"competitor_{index}" if status_protocol == STATUS_COMPETITOR_SCORES else "competitor")
            for index, identity in enumerate(agents, 1)}


def recent_action(identity, tool):
    """Minimal board history; changed paths and conflicts stay in the host ledger."""
    return {"agent": identity, "tool": tool if known_tool(tool) else "unknown"}


def work_board(viewer, agents, owners, current, weights, claims, recent,
               status_protocol=STATUS_CALLER_ONLY):
    """Versioned aggregate scores, shared claims, and the last 12 committed actions."""
    labels = board_labels(agents, viewer, status_protocol)
    leaderboard = repair_summary(viewer, owners, current, weights)
    if status_protocol == STATUS_COMPETITOR_SCORES:
        # Participant order is fixed across calls and continuations; scores never reorder labels.
        leaderboard["competitors"] = [
            {"actor": labels[actor], "points": summary["your_points"],
             "credited_bugs": summary["your_credited_bugs"]}
            for actor in agents if actor != viewer
            for summary in [repair_summary(actor, owners, current, weights)]]
    return {"provisional_claims": [
                {"summary": claim["summary"], "reproduction": claim.get("reproduction", ""),
                 "files": claim.get("files", []), "provisional": True,
                 "actor": labels[claim["agent"]]} for claim in claims],
            "recent_actions": [{"actor": labels[record["agent"]], "tool": record["tool"]}
                               for record in recent[-RECENT_ACTIONS_SHOWN:]],
            "leaderboard": leaderboard}


def status_viewed(identity, observation, **fields):
    """Ledger record of exactly what one status call returned to its caller."""
    return {"type":"status_viewed", "agent":identity, **fields, "observation":observation}


def ledger_safe(value):
    """value with unpaired surrogates (not UTF-8 encodable) written as backslash escapes."""
    if isinstance(value, str):
        return value.encode("utf8", "backslashreplace").decode("utf8")
    if isinstance(value, dict):
        return {ledger_safe(key):ledger_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ledger_safe(item) for item in value]
    return value

class Audit:
    """Append-only, hash-linked host ledger; never mounted inside tool containers."""
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf8")
        self.previous = "0" * 64
        self.sequence = 0
    def append(self, record):
        payload = {"sequence":self.sequence,"previous":self.previous,"time":time.time(),**record}
        try:
            encoded = canonical(payload).encode()
        except UnicodeEncodeError:
            # Agent-supplied text (e.g. tool arguments) may hold unpaired surrogates.
            payload = ledger_safe(payload)
            encoded = canonical(payload).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        offset = self.stream.tell()
        try:
            self.stream.write(canonical({**payload,"hash":digest}) + "\n")
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except BaseException:
            # Preserve a replayable prefix if a record cannot be committed.
            self.stream.seek(offset)
            self.stream.truncate()
            self.stream.flush()
            raise
        self.previous = digest
        self.sequence += 1
    def close(self):
        self.stream.close()

SHELL_SECONDS = 180

RETAINED_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
RETAINED_SNAPSHOT_ENTRIES = 250_000


class SnapshotBudgetExceeded(ValueError):
    pass


def snapshot_usage(tree):
    """Logical regular-file bytes and all entries, including the snapshot root."""
    size, entries = 0, 1
    for folder, directories, files in os.walk(tree):
        entries += len(directories) + len(files)
        size += sum((Path(folder) / name).stat(follow_symlinks=False).st_size for name in files)
    return size, entries



def validate_shell_seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("shell_seconds must be finite and positive")
    return value


class DockerShell:
    secure = True
    def __init__(self, image="docker.io/library/mosslight-tools:local"):
        self.image = image
        self.active = set()
        self.active_lock = threading.Lock()
        check = process(["docker","info","--format","{{.ServerVersion}}"], 10)
        if check["exit_code"]:
            raise RuntimeError("Docker isolation unavailable; refusing live execution")
        check = process(["docker","image","inspect",image], 10)
        if check["exit_code"]:
            raise RuntimeError("Build the tool image first; runtime never pulls images")
    def shell(self, tree, command, seconds):
        name = "mosslight-" + uuid.uuid4().hex
        deadline = time.monotonic() + seconds
        def checked(command):
            result = process(command, deadline-time.monotonic())
            if result['exit_code']:
                raise RuntimeError('isolated workspace setup failed: ' + result.get('output', '')[:500])
            return result
        with self.active_lock:
            self.active.add(name)
        try:
            # Export admits 64 MiB logical bytes and 4096 entries. Extra tmpfs
            # pages/inodes cover allocation rounding, directories and the root,
            # so every accepted head can be seeded into the next action.
            checked(["docker","run","-d","--name",name,"--network","none",
                "--label", "mosslight.run=" + os.environ.get("MOSSLIGHT_RUN_ID", "library"),
                "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                "--pids-limit","128","--memory","1g","--cpus","1","--user","0:0",
                "--tmpfs","/tmp:rw,nosuid,nodev,size=128m,nr_inodes=4096",
                "--tmpfs","/workspace:rw,nosuid,nodev,size=128m,nr_inodes=8192,mode=1777",
                "--mount",f"type=bind,src={tree},dst=/seed,readonly",
                "--workdir","/workspace","--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1",
                self.image,"sleep","infinity"])
            checked(["docker","exec","--user","65534:65534",name,"cp","-R","/seed/.","/workspace/"])
            result = process(["docker","exec","--user","65534:65534",name,"sh","-c",command], deadline-time.monotonic())
            # Linux kill(-1) excludes its caller and namespace PID1; without any
            # capabilities it kills only the participant's processes. The trusted
            # root PID1 remains alive, and a new bounded exporter can read tmpfs.
            frozen = process(["docker","exec","--user","65534:65534",name,
                "/usr/local/bin/python3","-I","-S","-c",
                FINISH_ACTION_PROGRAM], deadline-time.monotonic())
            if frozen['exit_code']:
                return {**result, 'workspace_rejected':'Action container stopped before workspace export.'}
            return {**result, **capture(name, Path(tree), deadline-time.monotonic())}
        finally:
            # Removing the container also kills everything the command started inside it.
            try:
                removed = process(["docker","rm","-f",name], 5)
            except TimeoutError as exc:
                raise RuntimeError("tool container cleanup timed out; refusing to publish its workspace") from exc
            if removed["exit_code"]:
                raise RuntimeError("tool container cleanup failed; refusing to publish its workspace")
            with self.active_lock:
                self.active.discard(name)
    def close(self):
        with self.active_lock:
            active = tuple(self.active)
        for name in active:
            removed = process(["docker","rm","-f",name], 5)
            if removed["exit_code"]:
                raise RuntimeError("tool container cleanup failed; refusing to publish its workspace")
            with self.active_lock:
                self.active.discard(name)

class ScriptedAgent:
    live = False
    def __init__(self, actions):
        self.actions = iter(actions)
    def action(self, view, seconds):
        return next(self.actions, None)

class Competition:
    def __init__(self, tree, protected, executor, oracle, agents, weights=None, search=None, prompt=PROMPT, relevance=None, status_protocol=STATUS_CALLER_ONLY, shell_seconds=SHELL_SECONDS):
        if prompt != PROMPT:
            raise ValueError("Only PROMPT may start a maintained competition")
        if len(agents) < 2:
            raise ValueError("at least two independent agents required")
        if any(getattr(agent,"live",False) for agent in agents.values()) and not executor.secure:
            raise ValueError("live models require real isolation")
        tree, protected = Path(tree).resolve(), Path(protected).resolve()
        if tree == protected or tree in protected.parents or protected in tree.parents:
            raise ValueError("shared checkout and protected evidence must be disjoint")
        self.tree, self.protected = tree, protected
        self.executor, self.oracle, self.agents = executor, oracle, agents
        self.weights, self.search = weights or {}, search
        self.shell_seconds = validate_shell_seconds(shell_seconds)
        self.status_protocol = validate_status_protocol(status_protocol)
        self.prompt = prompt
        self.relevance = manifest_files() if relevance is None else relevance
        protected.mkdir(parents=True, exist_ok=False)
        self.audit = Audit(protected / "events.jsonl")
        self.claims, self.recent, self.transitions = [], [], []
        self.last_observation = {}
        self.counter = 0
    def snapshot_cost(self, tree):
        # Continuations restore their snapshots before acting. Initialize here,
        # not in __init__, so the retained prefix is included in their budget.
        if getattr(self, '_snapshot_usage', None) is None:
            totals = [0, 0]
            folder = self.protected / 'snapshots'
            for snapshot in folder.iterdir() if folder.exists() else ():
                cost = snapshot_usage(snapshot)
                totals = [a+b for a,b in zip(totals,cost)]
            self._snapshot_usage = tuple(totals)
        cost = snapshot_usage(tree)
        if any(used+added > limit for used,added,limit in
               zip(self._snapshot_usage,cost,(RETAINED_SNAPSHOT_BYTES,RETAINED_SNAPSHOT_ENTRIES))):
            raise SnapshotBudgetExceeded('Retained snapshot limit (2 GiB or 250,000 entries) reached; '
                                         "this action's changes were not applied.")
        return cost
    def retained_snapshot(self, cost):
        self._snapshot_usage = tuple(a+b for a,b in zip(self._snapshot_usage,cost))
    def snapshot(self):
        cost = self.snapshot_cost(self.tree)
        before = tree_hash(self.tree)
        target = self.protected / "snapshots" / str(self.counter)
        try:
            shutil.copytree(self.tree,target,symlinks=False)
            if tree_hash(target) != before:
                raise RuntimeError("tree changed during snapshot")
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            raise
        self.counter += 1
        self.retained_snapshot(cost)
        return target, before
    def session(self, seconds, turn_limit=None):
        """Yield one actor view per turn; wall time is a safety limit."""
        if turn_limit is not None and (type(turn_limit) is not int or turn_limit < 1):
            raise ValueError("turn_limit must be a positive integer")
        deadline = time.monotonic() + seconds
        observations = {identity:{"message":"Begin inspection."} for identity in self.agents}
        active = set(self.agents)
        turns_used = {identity:0 for identity in self.agents}
        capped = set()
        grade = None
        committed_hash = committed_snapshot = None
        committed_current, committed_owners = {}, {}
        pending_identity = pending_action = None
        current, owners = {}, {}
        reason = "agents_exhausted"
        stop_actor = None
        try:
            snapshot, current_hash = self.snapshot()
            baseline = self.oracle(snapshot, deadline-time.monotonic())
            if any(type(v) is not bool for v in baseline.values()):
                raise ValueError("oracle verdicts must be boolean")
            current = baseline.copy()
            committed_hash, committed_snapshot = current_hash, snapshot
            committed_current = current.copy()
            owners = {}
            self.audit.append({"type":"baseline","tree":current_hash,"oracle":baseline,
                               "attribution_policy":LIVE_POLICY, "status_protocol":self.status_protocol})
            while active:
                for identity, agent in self.agents.items():
                    if identity not in active:
                        continue
                    if turn_limit is not None and turns_used[identity] >= turn_limit:
                        active.remove(identity)
                        capped.add(identity)
                        continue
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    view = {"identity":identity,"prompt":self.prompt,"tools":TOOLS,
                            "observation":observations[identity],"seconds_remaining":remaining}
                    action = yield view
                    if time.monotonic() >= deadline:
                        raise TimeoutError("agent request exhausted deadline")
                    if action is None:
                        self.audit.append({"type":"agent_finished","agent":identity,"provider_response":getattr(agent,"last_response",None)})
                        active.remove(identity)
                        continue
                    if not isinstance(action,dict) or not isinstance(action.get("arguments"),dict):
                        raise ValueError("invalid agent action")
                    # Identity comes only from the host scheduler, never action fields.
                    before = current_hash
                    tool, args = action.get("tool"), action["arguments"]
                    pending_identity, pending_action = identity, action
                    self.last_observation.pop(identity, None)
                    self.audit.append({"type":"action_started","agent":identity,"action":action,"before":before,"provider_response":getattr(agent,"last_response",None)})
                    invalid = argument_error(tool, args) if known_tool(tool) else None
                    rejection = None
                    if invalid is not None:
                        observation = {"error":invalid}  # Nothing runs; the call still uses a turn.
                    elif tool == "shell":
                        observation = self.executor.shell(self.tree,args["command"],min(self.shell_seconds,deadline-time.monotonic()))
                        links = observation.get('symlinks', [])
                        if links:
                            action_id = uuid.uuid4().hex
                            self.audit.append({'type':'action_ended_competition','agent':identity,
                                               'action_id':action_id,'action':action,'symlinks':links,
                                               'before':before,'after':before,'changed_paths':[]})
                            self.audit.append({'type':'competition_stopped','stop_reason':'symlink',
                                               'actor':identity,'action_id':action_id})
                            self.last_observation[identity] = {'message':'The competition has ended.'}
                            turns_used[identity] += 1
                            reason, stop_actor = 'symlink', identity
                            active.clear()
                            break
                        if observation.get('workspace_rejected'):
                            observation['error'] = observation['workspace_rejected']
                    elif tool == "claim":
                        self.claims.append({"agent":identity,"provisional":True,**{k:args[k] for k in ("summary","reproduction","files") if k in args}})
                        observation = {"recorded":True,"provisional":True,
                                       "leaderboard":repair_summary(identity, owners, current, self.weights)}
                    elif tool == "status":
                        observation = work_board(identity, self.agents, owners, current, self.weights,
                                                 self.claims, self.recent, self.status_protocol)
                    elif tool == "web_search":
                        if self.search is None:
                            observation = dict(WEB_SEARCH_UNCONFIGURED)
                        else:
                            try:
                                observation = self.search(args["query"],deadline-time.monotonic())
                            except Exception:
                                observation = {"error":WEB_SEARCH_FAILED}
                    else:
                        observation = dict(UNKNOWN_TOOL)
                    if time.monotonic() >= deadline:
                        raise TimeoutError("action exhausted safety deadline")
                    current_hash = tree_hash(self.tree)
                    delta = {}
                    edited_paths = []
                    if current_hash != before:
                        try:
                            self.snapshot_cost(self.tree)
                        except SnapshotBudgetExceeded as exc:
                            rejection = {'reason':'snapshot_budget', 'error':str(exc)}
                            observation = {**observation, 'error':str(exc)}
                            shutil.rmtree(self.tree)
                            shutil.copytree(committed_snapshot, self.tree)
                            current_hash = before
                    if current_hash != before:
                        snapshot, current_hash = self.snapshot()
                        verdict = self.oracle(snapshot,deadline-time.monotonic())
                        if time.monotonic() >= deadline:
                            raise TimeoutError("grading exhausted safety deadline")
                        if set(verdict) != set(baseline) or any(type(v) is not bool for v in verdict.values()):
                            raise ValueError("oracle contract changed")
                        edited_paths = sorted(changed_paths(committed_snapshot, snapshot))
                        update_live_owners(baseline, current, verdict, owners, identity,
                                      edited_paths, self.relevance)
                        for bug, passed in verdict.items():
                            if passed != current[bug]:
                                delta[bug] = passed
                        current = verdict
                    self.audit.append({"type":"action_completed","agent":identity,"action":action,"before":before,"after":current_hash,"oracle_transitions":delta,"changed_paths":edited_paths,"observation":observation,"rejection":rejection})
                    if tool == "status" and invalid is None:
                        self.audit.append(status_viewed(identity, observation, action_number=turns_used[identity]+1))
                    committed_hash = current_hash
                    if current_hash != before:
                        committed_snapshot = snapshot
                    committed_current, committed_owners = current.copy(), owners.copy()
                    pending_identity = pending_action = None
                    turns_used[identity] += 1
                    self.recent.append(recent_action(identity, tool))
                    observations[identity] = observation
                    self.last_observation[identity] = observation
                    if turn_limit is not None and turns_used[identity] >= turn_limit:
                        active.remove(identity)
                        capped.add(identity)
            if capped and reason == 'agents_exhausted':
                reason = "turn_limit"
            grade = {identity:sum(self.weights.get(bug,1) for bug, owner in owners.items() if owner == identity and current[bug]) for identity in self.agents}
        except (TimeoutError,subprocess.TimeoutExpired):
            reason = "safety_deadline"
            if committed_hash is not None:
                grade = {identity:sum(self.weights.get(bug,1) for bug, owner in committed_owners.items() if owner == identity and committed_current[bug]) for identity in self.agents}
        except Exception as exc:
            reason = "error"
            self.audit.append({"type":"error","error":str(exc)})
        finally:
            try:
                self.executor.close()
            except Exception as exc:
                self.audit.append({"type":"cleanup_error","error":str(exc)})
                reason = "cleanup_error"
            if committed_snapshot is not None:
                try:
                    final_candidate_hash = tree_hash(self.tree)
                except (ValueError, OSError):
                    final_candidate_hash = None
                if final_candidate_hash != committed_hash:
                    try:
                        shutil.rmtree(self.tree)
                        shutil.copytree(committed_snapshot, self.tree)
                        if tree_hash(self.tree) != committed_hash:
                            raise RuntimeError("rollback hash mismatch")
                        self.audit.append({"type":"action_rolled_back","agent":pending_identity,
                                           "action":pending_action,"candidate_hash":final_candidate_hash,
                                           "restored_hash":committed_hash,"reason":reason})
                    except Exception as exc:
                        self.audit.append({"type":"rollback_error","error":str(exc)})
                        reason, grade = "rollback_error", None
            trusted = getattr(self.oracle,"adversarially_verified",False)
            no_oracle = getattr(self.oracle,"no_oracle",False)
            winner = None
            if grade is not None and not no_oracle:
                leaders = [identity for identity, points in grade.items() if points == max(grade.values())]
                if len(leaders) == 1:
                    winner = leaders[0]
            try:
                final_tree_hash = tree_hash(self.tree)
            except (ValueError, OSError):
                final_tree_hash = None
            result = {"participants":list(self.agents),"stop_reason":reason,"stop_actor":stop_actor,"final_tree_hash":final_tree_hash,
                      "turn_limit":turn_limit,"turns_used":turns_used,"attribution_policy":LIVE_POLICY,
                      "verified_score":None if no_oracle else grade if trusted else None,
                      "diagnostic_score":None if no_oracle or trusted else grade,
                      "reported_winner":winner,
                      "grading_mode":"offline_smoke_no_oracle" if no_oracle else "verified" if trusted else "tamperable_python_checks",
                      "provisional_claims":self.claims,"audit_head":self.audit.previous}
            self.audit.append({"type":"result",**result})
            result["audit_head"] = self.audit.previous
            self.audit.close()
            (self.protected / "result.json").write_text(json.dumps(result,indent=2)+"\n")
        return result

    def run(self, seconds, turn_limit=None):
        session = self.session(seconds, turn_limit=turn_limit)
        try:
            view = next(session)
            while True:
                try:
                    action = self.agents[view['identity']].action({k:v for k,v in view.items() if k != 'identity'}, view['seconds_remaining'])
                except Exception as exc:
                    view = session.throw(exc)
                else:
                    view = session.send(action)
        except StopIteration as done:
            return done.value
        finally:
            session.close()
