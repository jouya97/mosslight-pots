"""Scripted offline smoke; paid competitions use the maintained fresh rollout CLI."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from .core import Competition, DockerShell, ScriptedAgent, process, participant_ids
from bug_competition.grader.weights import DEFAULT_MANIFEST, manifest_weights
from bug_competition.task import prompt_for

class OfflineExecutor:
    """Trusted fixed mock actions only; deliberately cannot execute shell."""
    secure=False
    def shell(self,tree,command,seconds):
        raise ValueError("offline demo does not execute shell; use Docker for arbitrary tools")
    def close(self):
        pass

def worker(args):
    from bug_competition.visibility.build import build_agent_tree
    started=time.monotonic()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    inventory=build_agent_tree(args.source.resolve(),output/"shared")
    search=None
    executor=OfflineExecutor()
    oracle=lambda tree,remaining:{}
    oracle.no_oracle=True
    agents={name:ScriptedAgent([{"tool":"claim","arguments":{"summary":"Offline harness smoke only; no fixes claimed."}}]) for name in participant_ids(args.participants)}
    competition=Competition(output/"shared",output/"protected",executor,oracle,agents,search=search, weights=manifest_weights(args.manifest), prompt=prompt_for())
    (output/"protected"/"staging.json").write_text(json.dumps(inventory,indent=2)+"\n")
    result=competition.run(max(.001,args.seconds-(time.monotonic()-started)-min(2,args.seconds*.1)))
    if args.final_grade:
        from bug_competition.grader.grader import grade_episode, FinalOracle
        result['final_grade'] = grade_episode(output/'protected', manifest=args.manifest,
            oracle=FinalOracle(args.image), seconds=args.grading_seconds)
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--source",type=Path,default=root/"mosslight")
    parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST)
    parser.add_argument("--participants",type=int,default=2)
    parser.add_argument("--seconds",type=float,default=30)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--final-grade",action="store_true", help="Independent final scoring after the episode")
    parser.add_argument("--grading-seconds",type=float,default=3600)
    parser.add_argument("--env-file",type=Path,default=Path(__file__).resolve().parents[2]/".env",help="Host-only credential file, loaded only for live execution")
    parser.add_argument("--allow-diagnostic-grading",action="store_true")
    parser.add_argument("--web-search",action="store_true",help="Compatibility flag: live web search is always enabled")
    parser.add_argument("--model",default="claude-opus-5-5")
    parser.add_argument("--image",default="docker.io/library/mosslight-tools:local")
    parser.add_argument("--worker",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    participant_ids(args.participants)
    if not math.isfinite(args.seconds) or args.seconds<=0:
        parser.error("seconds must be finite and positive")
    if not math.isfinite(args.grading_seconds) or args.grading_seconds <= 0:
        parser.error("grading-seconds must be finite and positive")
    if args.final_grade and not args.live:
        parser.error("final-grade requires a real isolated episode; offline demo has no repairs")
    if args.live:
        parser.error("Live competitions run through Inspect; use adapters/inspect/inspect_task.py")
    if args.worker:
        worker(args)
        return
    # Outer supervisor covers staging, API calls, grading and all subprocesses.
    if args.output.exists():
        parser.error("output must not exist")
    run_id=uuid.uuid4().hex
    worker_env={**os.environ,"MOSSLIGHT_RUN_ID":run_id}
    child=subprocess.Popen([sys.executable,"-B","-m","bug_competition.harness.run",*sys.argv[1:],"--worker"],start_new_session=True,env=worker_env)
    try:
        child.wait(timeout=args.seconds + (args.grading_seconds if args.final_grade else 0))
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL)
        child.wait()
        args.output.mkdir(parents=True,exist_ok=True)
        result={"stop_reason":"hard_deadline","verified_score":None,"diagnostic_score":None}
        (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result))
    finally:
        if args.live:
            try:
                containers=process(["docker","ps","-aq","--filter","label=mosslight.run="+run_id],5)
                for container in containers["output"].splitlines():
                    if container and all(c in "0123456789abcdef" for c in container):
                        process(["docker","rm","-f",container],5)
            except (OSError,TimeoutError,subprocess.TimeoutExpired):
                print("WARNING: Docker cleanup unavailable; inspect run label "+run_id,file=sys.stderr)
    if child.returncode and child.returncode != -signal.SIGKILL:
        raise SystemExit(child.returncode)

if __name__=="__main__":
    main()
