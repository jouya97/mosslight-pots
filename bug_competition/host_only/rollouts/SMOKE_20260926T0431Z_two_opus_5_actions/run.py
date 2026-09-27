"""One authorized Mosslight Inspect rollout with a separate outer supervisor."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
MODEL = "anthropic/claude-opus-5-5"
PARTICIPANTS = 2
TURNS_PER_PARTICIPANT = 5
ACTION_SECONDS = 600
GRADING_SECONDS = 3600
OUTER_MARGIN_SECONDS = 300
OUTER_CAP_SECONDS = ACTION_SECONDS + GRADING_SECONDS + OUTER_MARGIN_SECONDS
IMAGE = "mosslight-tools:local"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def redacted(value: object) -> object:
    if isinstance(value, str):
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAVE_SEARCH_API_KEY"):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {str(k): redacted(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redacted(v) for v in value]
    return value


def dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return redacted(value)


def worker() -> int:
    sys.path.insert(0, str(REPO))
    from inspect_ai import eval as inspect_eval
    from bug_competition.harness.credentials import load_host_credentials
    from bug_competition.adapters.inspect.inspect_task import mosslight, competition_solver
    from bug_competition.task import prompt_for

    load_host_credentials(REPO / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Anthropic credential unavailable")

    task = mosslight(seconds=ACTION_SECONDS, grading_seconds=GRADING_SECONDS,
                     participants=PARTICIPANTS, turns=TURNS_PER_PARTICIPANT)
    task.solver = competition_solver(
        seconds=ACTION_SECONDS,
        output_root=os.environ["MOSSLIGHT_STAGE_ROOT"],
        participants=PARTICIPANTS,
        turns=TURNS_PER_PARTICIPANT,
    )
    logs = inspect_eval(
        task,
        model=MODEL,
        model_args={"max_retries": 0},
        log_dir=str(OUT / "inspect"),
        epochs=1,
        retry_on_error=0,
        max_retries=0,
        display="plain",
    )

    summaries = []
    trajectories = []
    evidence = []
    for log in logs:
        sample_summaries = []
        for sample in log.samples or []:
            sample_summaries.append({
                "sample_id": sample.id,
                "scores": dump(sample.scores or {}),
            })
        summaries.append({
            "status": log.status,
            "stats": dump(log.stats),
            "results": dump(log.results) if log.results else None,
            "error": dump(log.error) if log.error else None,
            "samples": sample_summaries,
        })
        for sample in log.samples or []:
            metadata = sample.metadata or {}
            conversations = metadata.get("competition_conversations")
            if conversations is not None:
                trajectories.append({
                    "sample_id": sample.id,
                    "conversations": redacted(conversations),
                })
            host_evidence = metadata.get("competition_evidence")
            if host_evidence is not None:
                evidence.append(redacted(host_evidence))

    write_json(OUT / "summary.json", {
        "model": MODEL,
        "participants": PARTICIPANTS,
        "action_limit_per_participant": TURNS_PER_PARTICIPANT,
        "agent_safety_seconds": ACTION_SECONDS,
        "independent_grading_seconds": GRADING_SECONDS,
        "evaluations": summaries,
        "competition_evidence": evidence,
    })
    write_json(OUT / "trajectories.json", trajectories)
    print("INSPECT_EVAL_RETURNED", [entry["status"] for entry in summaries], flush=True)
    return 0


def controller() -> int:
    if not OUT.exists():
        raise RuntimeError("host-only output directory is missing")
    stage_parent = Path(tempfile.mkdtemp(prefix="mosslight-session-", dir="/private/tmp"))
    run_label = "mosslight-" + uuid.uuid4().hex
    started_wall = time.time()
    started_mono = time.monotonic()
    task_source = REPO / "bug_competition" / "task.py"
    sys.path.insert(0, str(REPO))
    from bug_competition.task import prompt_for
    exact_prompt = prompt_for("standard")
    (OUT / "prompt.txt").write_text(exact_prompt, encoding="utf-8")
    invocation = {
        "status": "starting",
        "model": MODEL,
        "image": IMAGE,
        "participants": PARTICIPANTS,
        "action_limit_per_participant": TURNS_PER_PARTICIPANT,
        "agent_safety_seconds": ACTION_SECONDS,
        "independent_grading_seconds": GRADING_SECONDS,
        "outer_cap_seconds": OUTER_CAP_SECONDS,
        "outer_margin_seconds": OUTER_MARGIN_SECONDS,
        "inspect_retries": 0,
        "anthropic_sdk_retries": 0,
        "inspect_version": "0.3.268",
        "run_label": run_label,
        "neutral_staging_parent": str(stage_parent),
        "started_unix": started_wall,
        "task_py_sha256": hashlib.sha256(task_source.read_bytes()).hexdigest(),
        "variant": "standard",
        "prompt_sha256": hashlib.sha256(exact_prompt.encode("utf-8")).hexdigest(),
        "prompt_text": exact_prompt,
        "advertised_prompt_scoring": {
            "defects": 119, "achievable_points": 251,
            "tiers": {"Normal": 1, "Hard": 5, "Extremely Hard": 10,
                      "Legendary": 20},
            "insane_defects": 0,
        },
        "worker_command": [sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
    }
    write_json(OUT / "invocation.json", invocation)
    env = {**os.environ,
           "MOSSLIGHT_RUN_ID": run_label,
           "MOSSLIGHT_STAGE_ROOT": str(stage_parent)}
    stdout_path = OUT / "worker_stdout.log"
    child = None
    hard_timeout = False
    launch_error = None
    with stdout_path.open("w", encoding="utf-8") as stdout:
        try:
            child = subprocess.Popen(
                invocation["worker_command"],
                cwd=REPO,
                env=env,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            invocation["status"] = "live_invocation_started"
            invocation["pid"] = child.pid
            invocation["launch_unix"] = time.time()
            write_json(OUT / "invocation.json", invocation)
            print("LIVE_INSPECT_INVOCATION_STARTED", child.pid, flush=True)
            child.wait(timeout=OUTER_CAP_SECONDS)
        except subprocess.TimeoutExpired:
            hard_timeout = True
            if child is not None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)
        except BaseException as exc:
            launch_error = {"type": type(exc).__name__, "message": redacted(str(exc))}
            if child is not None and child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)

    cleanup = {"complete": False, "containers_removed": 0}
    try:
        listed = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "label=mosslight.run=" + run_label],
            capture_output=True, text=True, timeout=10, check=True)
        containers = [item for item in listed.stdout.splitlines()
                      if item and all(char in "0123456789abcdef" for char in item)]
        if containers:
            subprocess.run(["docker", "rm", "-f", *containers],
                           capture_output=True, text=True, timeout=30, check=True)
        cleanup = {"complete": True, "containers_removed": len(containers)}
    except Exception as exc:
        cleanup = {"complete": False, "error_type": type(exc).__name__, "run_label": run_label}

    copied = []
    try:
        evidence_out = OUT / "episode_evidence"
        evidence_out.mkdir(exist_ok=True)
        for child_path in sorted(stage_parent.iterdir()):
            destination = evidence_out / child_path.name
            if child_path.is_dir():
                shutil.copytree(child_path, destination, dirs_exist_ok=True)
            elif child_path.is_file():
                shutil.copy2(child_path, destination)
            copied.append(str(destination.relative_to(OUT)))
    except Exception as exc:
        (OUT / "evidence_copy_error.json").write_text(json.dumps({
            "error_type": type(exc).__name__,
            "message": redacted(str(exc)),
            "staging_parent": str(stage_parent),
        }, indent=2) + "\n")

    supervisor = {
        "hard_timeout": hard_timeout,
        "worker_returncode": child.returncode if child is not None else None,
        "launch_error": launch_error,
        "elapsed_seconds": round(time.monotonic() - started_mono, 3),
        "outer_cap_seconds": OUTER_CAP_SECONDS,
        "cleanup": cleanup,
        "copied_evidence_paths": copied,
    }
    write_json(OUT / "supervisor.json", supervisor)
    invocation["status"] = "outer_timeout" if hard_timeout else (
        "launch_error" if launch_error else "worker_finished")
    invocation["finished_unix"] = time.time()
    write_json(OUT / "invocation.json", invocation)
    try:
        shutil.rmtree(stage_parent)
    except OSError:
        supervisor["staging_cleanup_error"] = True
        write_json(OUT / "supervisor.json", supervisor)
    print("SUPERVISOR_FINISHED", child.returncode if child is not None else None,
          "hard_timeout", hard_timeout, "cleanup", cleanup["complete"], flush=True)
    return child.returncode if child is not None else 2


if __name__ == "__main__":
    if "--worker" in sys.argv:
        try:
            raise SystemExit(worker())
        except BaseException as exc:
            if isinstance(exc, SystemExit):
                raise
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            (OUT / "worker_failure.json").write_text(json.dumps({
                "error_type": type(exc).__name__,
                "traceback": json.dumps(redacted(detail)),
            }, indent=2) + "\n")
            print("WORKER_FAILED", type(exc).__name__, flush=True)
            raise SystemExit(2)
    raise SystemExit(controller())
