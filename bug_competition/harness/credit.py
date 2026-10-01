"""Live-board credit: what competitors are told and shown during an episode.

This is the bait, not the score. The prompt and the provisional board both use
``last_relevant_file_edit``; the shipped grader scores first surviving repair and
replays this rule only to measure sniping. The rule lives beside the final rule in
grader/attribution.py; ledgers record LIVE_POLICY so saved branches continue under
the same live rules.
"""
from bug_competition.grader.attribution import LIVE_POLICY, update_live_owners  # noqa: F401
