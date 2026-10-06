# Scaffold-layout submission package

This delivery puts the original scaffold slots at the repository root:
`task.py`, `env.json`, `variants.json`, `qc.json`, `flaw.md`, `agent_data/`,
`grader/` and `adapters/`. The experiment implementation and historical evidence
remain below `bug_competition/`. The supplied [rubric](../../../../RUBRIC.md) is
unchanged. Existing `bug_competition.grader`, `.task` and `.adapters` imports
continue through the package's namespace bridge.

It also includes the [version 8 retrospective regrade](../../regrades/20261006T035725Z_v8/README.md).
Those scores apply revised probes and scoring to the original agents' actions;
the agents did not see the version 8 prompt. The earlier
[frozen replay](../../regrades/20261005T180821Z/README.md) and the
[previous package records](../20261005_v8/README.md) remain unchanged.

## Delivery and provenance

The new handoff directory is `bug_competition/archives/20261005_v8_scaffold/`:

- `mosslight_v8_scaffold_20261005.tar.gz`: source and evidence.
- `manifest.json`: file hashes, modes, sizes, Git base and dirty snapshot ID.
- `submission_bundle.py`: inspectable standalone verifier and extractor.
- `mosslight_historical_cbc65b15_image.tar.gz`: exact original Docker image.
- `mosslight_v8_28e3d6ca_image.tar.gz`: exact version 8 Docker image.
- `acceptance.json`: checks performed after extracting the finished archive.

The canonical new manifest lives beside this README. It stays outside the
archive to avoid a self-checksum cycle. The previous delivery is never replaced.
Both image exports are reused byte for byte; [images.json](images.json) records
their hashes, sizes and Linux arm64 platform. The base image digest alone would
not reproduce mutable Debian package downloads, so the exact exports are supplied.

The source archive preserves original run paths, including bytecode already
present in hashed historical snapshots. Derived
`submission_readable_summaries.json` files retain supplied readable summaries,
text and tool calls. Their source hashes and transformation are recorded.
Opaque trajectory duplicates are omitted; original hash-chained ledgers retain
their provider payloads for integrity. Do not decode opaque reasoning.

The manifest counts root grader Python and executable programs stored in probe
JSON. The complete grader remains above the rubric's 1,000-line target. See
[VALIDATION.md](VALIDATION.md) for source checks and [plan.json](plan.json) for
scope. An absent manifest means this is still a planned delivery.

## Create and verify

After the new regrade completes, integration checks pass and source is frozen:

```sh
python3 -B -m bug_competition.host_only.tools.submission_bundle create \
  --archive bug_competition/archives/20261005_v8_scaffold/mosslight_v8_scaffold_20261005.tar.gz \
  --manifest bug_competition/host_only/submissions/20261005_v8_scaffold/manifest.json
```

Copy the manifest and verifier into the handoff directory without replacing any
existing file. The image files there can be regular-file hard links to the
existing verified exports in the parent `archives/` directory. A recipient can
verify and extract from the handoff directory with:

```sh
python3 -B submission_bundle.py verify manifest.json \
  --archive mosslight_v8_scaffold_20261005.tar.gz
python3 -B submission_bundle.py extract manifest.json \
  --archive mosslight_v8_scaffold_20261005.tar.gz --destination mosslight-review
cd mosslight-review
python3 -B -m bug_competition.host_only.tools.submission_bundle check-historical-inputs
python3 -B -m bug_competition.host_only.tools.submission_bundle reviewability
```

Verification reads archive members without executing them. Extraction requires a
new directory and rejects traversal, links, special files, duplicate names and
oversized members. Both frozen runtime/probe sets and their original input hashes
are verified, and every protected snapshot is checked against both replay records.

## Validate the extracted scaffold

Use Python 3.12 and the pinned review dependencies:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-review.lock.txt
python -B task.py standard
python -B -m pytest -q -p no:cacheprovider -m 'not docker' bug_competition grader
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --offline-check
```

Before loading the two images, verify their compressed hashes from the manifest.
Run this in the handoff directory:

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
record = json.loads(Path('manifest.json').read_text())
for image in record['provenance']['image_delivery']['images']:
    path = Path(Path(image['archive']).name)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    assert path.stat().st_size == image['archive_bytes'], path
    assert digest.hexdigest() == image['archive_sha256'], path
    print('Verified', path)
PY
docker image load --input mosslight_historical_cbc65b15_image.tar.gz
docker image load --input mosslight_v8_28e3d6ca_image.tar.gz
```

Both images are Linux arm64; another architecture needs compatible emulation.
From the extracted repository, run the Docker checks using the exact version 8
image. These tests do not call model APIs:

```sh
MOSSLIGHT_TEST_IMAGE=sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75 \
  python -B -m pytest -q -p no:cacheprovider -m docker bug_competition grader
```

## Replay either scoring generation

Keep frozen outputs unchanged. Each archived runner refuses to overwrite its own
completed results. The following command imports one frozen runtime, grades the
original protected snapshots and writes a new review directory. It may take tens
of minutes. It makes no model calls.

```sh
python3 -B - <<'PY'
import json
from pathlib import Path
import sys

root = Path.cwd()
# Choose 20261005T180821Z for the earlier policy instead.
saved = root / 'bug_competition/host_only/regrades/20261006T035725Z_v8'
sys.path.insert(0, str(saved / 'runtime'))
from bug_competition.grader.grader import CandidateRunner, FinalOracle, grade_episode

provenance = json.loads((saved / 'provenance.json').read_text())
out = root / ('review_replay_' + saved.name)
out.mkdir(exist_ok=False)
for name, inputs in provenance['inputs'].items():
    image = provenance.get('image') or inputs['image']
    probes = saved / 'grading_probes.json'
    if not probes.exists():
        probes = root / inputs['source'] / 'grading_probes.json'
    oracle = FinalOracle(runner=CandidateRunner(image))
    oracle.probes = json.loads(probes.read_text())
    oracle.covered = {probe['id'] for probe in oracle.probes}
    grade = grade_episode(root / inputs['protected'], oracle=oracle, seconds=10800)
    with (out / (name + '.json')).open('x') as stream:
        json.dump(grade, stream, indent=2)
    assert grade['adjudication_complete'] and grade['coverage_complete'], name
    frozen = json.loads((saved / name / 'grade.json').read_text())
    keys = ['points', 'scores', 'snipe_points']
    keys += ['preservation_checks', 'symlink_offenders'] if provenance.get('policy_version') == 8 else ['sniping_zeroed']
    for key in keys:
        assert grade[key] == frozen[key], (name, key)
    print(name, grade['scores'])
PY
```

Saved temporary execution paths are provenance, not package dependencies. The
command uses the retained repository-relative protected paths. Any newly observed
behavior belongs in a separate record; neither replay becomes a new model rollout.
