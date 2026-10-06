# Agent checkout boundary

`build_agent_tree(source: Path, destination: Path) -> dict` stages the
Mosslight application from `bug_competition/mosslight/` into a fresh, disjoint
directory. That directory becomes the agent-visible `/workspace`. Import it as
`bug_competition.visibility.build.build_agent_tree` from the repository root.

What is staged:

- An explicit allowlist of application modules, static web assets, examples,
  `pyproject.toml`, `LICENSE` and the product guides.
- [`agent_data/SUBMISSION.md`](../../agent_data/SUBMISSION.md), which states the
  submission rules.
- `tests/test_smoke.py`, two broad smoke tests (a save and artwork workflow, and
  a CLI workflow). It replaces the application's public regression tests, whose
  case names and assertions would point at the intended repairs. The staged
  `README.md` has its test section rewritten to describe this suite.
- `FIELD_CALIBRATION.md`, `WORKSPACE_CATALOG.md` and `IRRIGATION.md`, taken
  from `templates/` instead of the source. Keep each template in sync with its
  source guide when APIs change.

The guides describe ordinary workflows, public formats and product promises. They
keep the facts needed to use a feature, such as calendar meaning, species traits,
event offsets, measurement definitions, compatibility, and identity and conflict
behavior. They leave out internal timing, transaction recipes, algorithm
walkthroughs and lists of edge cases. The application source has no function or
class docstrings and no diagnostic comments; they were removed from the source
itself, not at staging time.

Everything else is excluded, including unknown files inside approved
directories. In particular, nothing under `host_only/` or `grader/` is staged:
manifests, checks, patches, snapshots, archives, environment files and Git
history stay on the host. Symlinks are neither followed nor copied, including
symlinked approved directories. Arguments containing `..`, overlapping trees and
existing destinations are rejected. Any new Python module, static asset, example
or root document raises an allowlist-update error before staging starts, so the
application can never ship half-staged.

The returned inventory has `format_version`, `tree_sha256` and sorted `files`
entries containing `path`, `size` and `sha256`. Paths are relative. The tree
digest hashes the canonical compact JSON of the inventory. It contains no
timestamps or source paths, and it is never written into the agent checkout.

```sh
python3 -B -m unittest discover -s bug_competition/visibility/tests -v
```

The builder is only a packaging boundary. The harness separately confines each
action to its staged checkout, so an agent cannot browse the repository or host
artifacts ([harness/README.md](../harness/README.md)).
