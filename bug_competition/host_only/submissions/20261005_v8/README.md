# Version 8 submission package

This package combines the prospective source with the evidence needed to inspect
R1–R3 and replay the frozen October 5 grading. Historical prompts, probes,
snapshots and grades are unchanged. Version 8 changes are described in
[the design](../../../flaw.md); the historical scoring chronology is in
[RESULTS.md](../../RESULTS.md).

The original [RUBRIC.md](../../../../RUBRIC.md) is included verbatim. The grader
still exceeds its 1,000-line target when executable probe programs are counted.
The package manifest records fresh line counts instead of treating JSON programs
as inert data.

## Delivery files

After code freeze, deliver these together:

- `bug_competition/archives/mosslight_v8_20261005.tar.gz`
- `bug_competition/host_only/submissions/20261005_v8/manifest.json`
- `bug_competition/archives/mosslight_historical_cbc65b15_image.tar.gz`
- `bug_competition/archives/mosslight_v8_28e3d6ca_image.tar.gz`
- [submission_bundle.py](../../tools/submission_bundle.py), available separately
  so the recipient can inspect and run verification before extraction.

The manifest stays outside the archive to avoid a self-checksum cycle. It lists
every file's hash, byte count and mode, a complete source snapshot identifier,
the Git base and dirty state, evidence provenance, and the tested image ID.
The archive preserves repository-relative paths. A source checkout alone still
lacks ignored evidence; this archive supplies the three protected runs, the
frozen regrade and the review exports together.

Readable conversation exports are named `submission_readable_summaries.json`
inside each retained run. They preserve supplied readable summaries, text and
tool calls; their original trajectory hashes and transformation are recorded.
Opaque trajectory copies are omitted. Original protected event ledgers contain
provider payloads and are preserved to retain their hashes. Do not decode those
payloads or describe them as known reasoning.

See [plan.json](plan.json) for the delivery scope and
[VALIDATION.md](VALIDATION.md) for the final checks. Until an external manifest
exists, this directory describes a planned package rather than a finished one.

## Create, verify and extract

From the repository root, after the integration checks and code freeze:

```sh
python3 -B -m bug_competition.host_only.tools.submission_bundle create \
  --archive bug_competition/archives/mosslight_v8_20261005.tar.gz \
  --manifest bug_competition/host_only/submissions/20261005_v8/manifest.json
```

The utility refuses existing output files, symlinks in source, unsafe archive
members and archives that exceed its bounds. It rechecks source file hashes
before publishing the archive. Verification reads members without extracting or
executing them. Extraction requires a new directory and preserves file modes,
which are part of the historical snapshot hashes.

A recipient with the source archive, manifest and verifier in one directory can run:

```sh
python3 -B submission_bundle.py verify manifest.json \
  --archive mosslight_v8_20261005.tar.gz
python3 -B submission_bundle.py extract manifest.json \
  --archive mosslight_v8_20261005.tar.gz --destination mosslight-review
cd mosslight-review
python3 -B -m bug_competition.host_only.tools.submission_bundle check-historical-inputs
python3 -B -m bug_competition.host_only.tools.submission_bundle reviewability
```

The historical input check verifies the frozen runtime, runner and original
input hashes, plus every protected snapshot against its recorded tree hash.
It does not execute model code or contact a provider.

## Validate the extracted version 8 source

Use Python 3.12 and an idle Docker daemon. Install the pinned review dependencies
in a virtual environment, then run:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-review.lock.txt
python -B -m pytest -q -p no:cacheprovider -m 'not docker' bug_competition
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --offline-check
```

The tested prospective image is
`sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75`.
The Dockerfile pins its Python base digest, but its Debian packages come from a
mutable repository. Rebuilding it later is not guaranteed to reproduce that
image. Both exact images are delivered as separate compressed `docker save` exports.
Their hashes, byte counts and platform are in [images.json](images.json), also
copied into the source manifest. Both images are Linux arm64; another host
architecture needs compatible emulation. Verify the images against that
manifest before loading them. From the directory containing the delivery files:

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
record = json.loads(Path('manifest.json').read_text())
for image in record['provenance']['image_delivery']['images']:
    path = Path(image['archive']).name
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    assert Path(path).stat().st_size == image['archive_bytes'], path
    assert digest.hexdigest() == image['archive_sha256'], path
    print('Verified', path)
PY
docker image load --input mosslight_historical_cbc65b15_image.tar.gz
docker image load --input mosslight_v8_28e3d6ca_image.tar.gz
```

From the extracted repository, run the Docker tests without model API calls:

```sh
docker image inspect sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75
docker tag sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75 docker.io/library/mosslight-tools:local
python -B -m pytest -q -p no:cacheprovider -m docker bug_competition
```

## Replay the historical grading

The frozen replay used the original image
`sha256:cbc65b1527ad0a79be2643adddf1b2cc3ff7b694ba4cb9d489cc352714e17f36`.
It is separate from the prospective Chromium image. Load that historical image
before running the following from the extracted repository root. This executes
all saved snapshots in Docker and may take tens of minutes; it makes no model
API calls. The output directory must be new.

```sh
python3 -B - <<'PY'
import json
from pathlib import Path
import sys

root = Path.cwd()
saved = root / 'bug_competition/host_only/regrades/20261005T180821Z'
sys.path.insert(0, str(saved / 'runtime'))
from bug_competition.grader.grader import CandidateRunner, FinalOracle, grade_episode

provenance = json.loads((saved / 'provenance.json').read_text())
out = root / 'historical_replay_review'
out.mkdir(exist_ok=False)
for name, inputs in provenance['inputs'].items():
    oracle = FinalOracle(runner=CandidateRunner(inputs['image']))
    oracle.probes = json.loads((root / inputs['source'] / 'grading_probes.json').read_text())
    oracle.covered = {probe['id'] for probe in oracle.probes}
    grade = grade_episode(root / inputs['protected'], oracle=oracle, seconds=10800)
    with (out / (name + '.json')).open('x') as stream:
        json.dump(grade, stream, indent=2)
    assert grade['adjudication_complete'] and grade['coverage_complete'], name
    frozen = json.loads((saved / name / 'grade.json').read_text())
    for key in ('points', 'scores', 'snipe_points', 'sniping_zeroed'):
        assert grade[key] == frozen[key], (name, key)
    print(name, grade['scores'])
PY
```

Do not rerun the archived `run_regrade.py` in place: it correctly refuses to
overwrite its existing runtime and outputs. The command above imports that
runtime and writes a separate result. Comparing historical grades does not
establish how models behave under the new prompt or score policy.
