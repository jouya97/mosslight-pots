# Agent checkout boundary

`build_agent_tree(source: Path, destination: Path) -> dict` stages the current
Mosslight application in a fresh disjoint directory. Import it as
`bug_competition.visibility.build.build_agent_tree` from the repository root.

The explicit file allowlist includes the application, local assets, setup,
feature documentation and examples. All existing public regression tests are
omitted because their case names and precise assertions disclose intended defect
repairs. Two broad smoke tests replace them: a save/artwork workflow and a CLI
workflow. The README describes the staged suite accurately. Original regression
tests remain available to host tooling; hidden grading checks never enter the
staged tree.

The staged field-calibration, workspace-catalog and irrigation guides still use
copies in `templates/`; these now match their source guides. Keep each pair in
sync when APIs change. Ordinary module names and application code are copied
from the current source tree.

The public documentation describes ordinary workflows, public formats and
product promises. It retains facts needed to use or interpret a feature: calendar
meaning, species traits through the public catalog, experiment event offsets,
measurement definitions, release compatibility and identity/conflict behavior.
It avoids internal state-copy timing, transaction and worker-generation recipes,
algorithm walkthroughs and lists of diagnostic edge cases. Source code and its
public catalog remain available for investigation and local testing. No prompt
change accompanies this documentation pass.

The documentation before this pass is retained under
`host_only/docs_before_product_promises/` for contract and grading review. That
archive is outside the application tree and never staged. The behavioral grader
has not changed. Broad public promises intentionally leave implementation choices
and their verification to the maintainer; this editorial boundary alone does not
establish a bug's difficulty.

Function and class docstrings and diagnostic inline comments were removed by the
preceding source pass. This documentation pass changes no executable source.
Archived releases and prior rollouts are outside its scope.

Unknown host files are excluded even within an approved directory. This excludes host
artifacts, manifests, snapshots, patches, archives, environment files and Git
history. Symlinks are neither followed nor copied, including symlinked approved
directories. Arguments containing `..`, overlapping trees and existing
destinations are rejected. New Python modules, static assets, examples or root
documentation cause an explicit allowlist-update error before staging starts.
Add legitimate new application files to the explicit allowlist when the
application grows; this avoids silently shipping an incomplete application.

The returned inventory has `format_version`, `tree_sha256`, and sorted `files`
entries containing `path`, `size`, and `sha256`. Paths are relative; the tree
digest hashes canonical compact JSON of the inventory. It contains no timestamps
or source paths and is never written into the agent checkout.

Run the host checks with:

```sh
python3 -B -m unittest discover -s bug_competition/visibility/tests -v
```

The builder is a packaging boundary. The harness must separately restrict the
agent process to its staged checkout so it cannot browse the original repository
or host artifacts. The source tree is trusted host input and should remain
unchanged while building.
