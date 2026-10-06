# Mosslight implementation and evidence

The environment's canonical scaffold files are at the repository root. Start
with the [main README](../README.md), [design](../flaw.md), and
[grader](../grader/README.md).

This directory contains the parts specific to the shared-codebase experiment:

- `environment.py`: the lifecycle joining the task, broker and grader.
- [harness/](harness/README.md): disposable tool containers, merges, protected
  evidence and the provisional checker and leaderboard.
- [visibility/](visibility/README.md): builds the allowed agent-visible checkout
  from `mosslight/` and the root `agent_data/` files.
- `mosslight/`: the application seeded with 119 bugs.
- [host_only/](host_only/README.md): fixtures, checks, launchers and retained runs.
- [results](host_only/RESULTS.md) and [evidence](host_only/EVIDENCE.md): original
  scores, retrospective regrades and their provenance.
- `tests/`: tests spanning the environment, launchers and adapters.
- `archives/`: local delivery and evidence archives.

`__init__.py` keeps the established `bug_competition.task`,
`bug_competition.grader` and `bug_competition.adapters` imports working with the
canonical files at root. There are no duplicate task or grader implementations.
Historical paths within this directory are preserved.
