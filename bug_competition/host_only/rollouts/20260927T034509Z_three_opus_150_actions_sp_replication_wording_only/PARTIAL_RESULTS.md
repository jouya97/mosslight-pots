# Partial results: initialization failure

Status: **failed before the first agent action; no scored rollout occurred.**

The authorized controller in this folder started at 2026-09-27 07:44 UTC and exited after 4.712 seconds. Inspect reported `RuntimeError: Build the tool image first; runtime never pulls images` while constructing `DockerShell`, before the competition sample began. The evaluation has no completed samples and empty `model_usage`; `trajectories.json` is `[]`. There are no `events.jsonl` files, so `ledger_scan.py` reports that it found zero event ledgers. This attempt produced no agent actions, claims, repairs, or scores.

The controller preserved its failure summary and staged source snapshot under `episode_evidence/mosslight-55f6sahm/`; those files are unchanged. After the controller exited, `docker image inspect mosslight-tools:local` succeeded. The image was rebuilt from the repository Dockerfile and the same image digest was confirmed; an isolated `DockerShell()` constructor check then succeeded with the prepared runtime and created no containers. The authorized retry uses the separate fresh folder `/Users/jian/Documents/GitHub/mosslight-pots/bug_competition/host_only/rollouts/20260927T074630Z_three_opus_150_actions_sp_replication_wording_only_retry1.
