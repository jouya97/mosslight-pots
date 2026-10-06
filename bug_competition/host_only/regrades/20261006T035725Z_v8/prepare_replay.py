"""Prepare a fresh output directory for reproducing this frozen v8 replay."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve(); source_root=args.source_root.resolve()
    if output.exists(): raise ValueError('Output must be a new directory')
    metadata=json.loads((HERE/'provenance.json').read_text())
    assert metadata['status']=='completed'
    for relative,digest in metadata['runtime_files_sha256'].items():
        assert hashlib.sha256((HERE/'runtime'/relative).read_bytes()).hexdigest()==digest,relative
    assert hashlib.sha256((HERE/'grading_probes.json').read_bytes()).hexdigest()==metadata['grading_probes_sha256']
    for source in metadata['inputs'].values():
        for relative,digest in source['input_sha256'].items():
            assert hashlib.sha256((source_root/relative).read_bytes()).hexdigest()==digest,relative
        source['stable_protected']=str(source_root/source['protected'])
    output.mkdir(parents=True)
    shutil.copytree(HERE/'runtime',output/'runtime')
    for name in ('run_regrade.py','grading_probes.json'):
        shutil.copy2(HERE/name,output/name)
    for name in metadata['inputs']:
        (output/name/'verdicts').mkdir(parents=True)
        for artifact in ('original_grade.json','original_invocation.json','original_grading_probes.json',
                         'october5_grade.json','october5_final_bug_owners.json','events.jsonl','result.json'):
            shutil.copy2(HERE/name/artifact,output/name/artifact)
    for key in ('results','failures','started_utc','finished_utc'):
        metadata.pop(key,None)
    metadata.update(status='frozen',reproduces=str(HERE),reproduced_provenance_sha256=hashlib.sha256((HERE/'provenance.json').read_bytes()).hexdigest())
    (output/'provenance.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    print(output/'run_regrade.py')

if __name__=='__main__':
    main()
