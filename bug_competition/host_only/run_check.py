#!/usr/bin/env python3
"""Run one documented contract check against a chosen app tree."""
import argparse
from pathlib import Path
import verify
parser=argparse.ArgumentParser();parser.add_argument('id');parser.add_argument('--tree',type=Path,required=True)
args=parser.parse_args();root=args.tree.resolve()
result=verify.check({'id':args.id},root)
print(result['stdout'],end='');print(result['stderr'],end='')
raise SystemExit(result['returncode'])
