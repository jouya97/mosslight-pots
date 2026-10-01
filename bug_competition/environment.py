"""Host lifecycle for N competitors, with concurrent Inspect and serial compatibility APIs.

The identity in a broker view is routing metadata, never model input.
"""
from pathlib import Path
from .harness.core import Competition, DockerShell, ScriptedAgent, participant_ids, STATUS_CALLER_ONLY
from .harness.parallel import ParallelCompetition
from .harness.adapters import OpenAISearch, BraveSearch
from .harness.oracle import DockerOracle
from .grader.weights import manifest_weights, DEFAULT_MANIFEST
from .task import prompt_for
from .visibility.build import build_agent_tree

# Canonical experiment, matching host_only/tools/fresh_rollout.py and the Inspect task.
PARTICIPANTS, SECONDS, TURNS = 3, 5400, 150


class Environment:
    def __init__(self, variant='standard', parameters=None, *, executor=None, oracle=None, search=None):
        prompt_for(variant)  # Reject unsupported variants before creating evidence.
        self.variant, self.parameters = variant, parameters or {}
        self.identities = participant_ids(self.parameters.get('participants', PARTICIPANTS))
        self.executor, self.oracle, self.search = executor, oracle, search
        self.session = self.result = self.current = None

    def _prepare(self, workdir, parallel=False):
        if hasattr(self, "competition"):
            raise ValueError('environment already started')
        root = Path(workdir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        package = Path(__file__).resolve().parent
        source = Path(self.parameters.get('source', package / 'mosslight'))
        build_agent_tree(source, root / 'shared')
        image = self.parameters.get('image', 'docker.io/library/mosslight-tools:local')
        if self.executor is None and self.search is None:
            import os
            self.search = BraveSearch() if os.environ.get('BRAVE_SEARCH_API_KEY') else OpenAISearch()
        broker = ParallelCompetition if parallel else Competition
        self.competition = broker(root / 'shared', root / 'protected',
            self.executor or DockerShell(image), self.oracle or DockerOracle(DEFAULT_MANIFEST, image),
            {identity:ScriptedAgent([]) for identity in self.identities}, weights=manifest_weights(),
            search=self.search, prompt=prompt_for(self.variant),
            status_protocol=self.parameters.get('status_protocol', STATUS_CALLER_ONLY))
    def reset_parallel(self, workdir):
        self._prepare(workdir, parallel=True)
        self.competition.begin(float(self.parameters.get('seconds', SECONDS)),
                               turn_limit=self.parameters.get('turns', TURNS))
        return {identity:self.competition.view(identity) for identity in self.identities}

    def reset(self, workdir):
        """Serial compatibility interface; Inspect uses reset_parallel/act instead."""
        self._prepare(workdir)
        self.session = self.competition.session(float(self.parameters.get('seconds', SECONDS)),
            turn_limit=self.parameters.get('turns', TURNS))
        return self._advance()

    def _advance(self, action=None, initial=True):
        try:
            self.current = next(self.session) if initial else self.session.send(action)
            return {**self.current, 'terminal':False}
        except StopIteration as done:
            self.result, self.current = done.value, None
            return {'observation':{'message':'Maintenance window closed.'}, 'terminal':True}

    def step(self, action, remaining_seconds):
        if self.current is None:
            raise ValueError('reset before step; cannot step a terminal environment')
        if remaining_seconds <= 0:
            try:
                self.session.throw(TimeoutError('adapter deadline'))
            except StopIteration as done:
                self.result = done.value
            self.current = None
            return {'observation':{'message':'Maintenance window closed.'}, 'terminal':True}
        return self._advance(action, initial=False)

    def evidence(self):
        return {'protected':str(self.competition.protected), 'result':self.result,
                'participants':self.identities}

    def close(self):
        if isinstance(getattr(self, 'competition', None), ParallelCompetition):
            self.result = self.competition.finish()
        if self.session is not None:
            self.session.close()
            self.session = None


def create_environment(variant, parameters):
    return Environment(variant, parameters)
