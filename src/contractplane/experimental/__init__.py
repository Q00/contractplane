"""Experimental end-to-end governed execution slice.

.. warning::

   EXPERIMENTAL — NOT part of the specified ContractPlane v1alpha1 surface.

   Everything in this package is an additive research prototype layered *on top
   of* the frozen transition kernel in :mod:`contractplane.state`. It is the
   first code in the repository that actually *consumes* a compiled capability
   ``binding`` (dispatching real work) and that closes the loop between a
   producer, an independent verifier, and a deny-by-default authority gate.

   The kernel deliberately does none of this: by its own docstring it "never
   evaluates selectors/conditions or invokes a capability binding" and treats
   evidence receipts as shape-gated adapter inputs, with verifier identity and
   independence explicitly out of scope. This package supplies exactly those
   missing consumers *without* forking kernel semantics: it only ever drives the
   kernel through its public transition methods, so every guarantee the kernel
   already enforces (append-only ledger, replayable state, gated completion)
   continues to hold.

   Scope of the prototype: singleton stages, local-process/in-workspace work,
   and JSON/artifact evidence. ``fanout: each`` expansion, remote adapters,
   semantic-review evidence, and multi-tenant isolation are intentionally not
   implemented here.
"""

from __future__ import annotations

from .acp_adapter import (
    ACPError,
    ACPPermissionDenied,
    ACPResult,
    acp_available,
    node_executable,
    run_acp_task,
)
from .adapter import DispatchResult, LocalProcessAdapter
from .authority import AuthorityDecision, AuthorityGate, AuthorityGrant
from .episode import (
    Episode,
    EpisodeError,
    EpisodeProducer,
    load_episode,
    parse_episode,
    replay_episode,
)
from .harness import ConfigurationError, GovernedRunner, RunReport, RunResult
from .judge_study import (
    JUDGE_COMPARISON_SCHEMA,
    JUDGE_FIXTURE_SCHEMA,
    JudgeFixtureError,
    parse_judge_filename,
    run_judge_comparison,
    validate_judge_fixture,
    write_judge_comparison,
)
from .natural_study import (
    DATASET_SCALE2_TOKENS,
    DATASET_SCALE_TOKENS,
    HardCountRecomputer,
    HardSumRecomputer,
    NATURAL_POWER_STUDY_SCHEMA,
    NATURAL_SCALE_STUDY_SCHEMA,
    NATURAL_STUDY_SCHEMA,
    parse_natural_filename,
    parse_scale_filename,
    run_natural_power_study,
    run_natural_scale_study,
    run_natural_study,
    wilson_interval,
    write_natural_study,
)
from .recompute import (
    ChainRecomputer,
    FilterCountRecomputer,
    RecordCountRecomputer,
    Recomputer,
    SumRecomputer,
)
from .study import (
    CONDITIONS,
    FAMILIES,
    MODEL_SHORTS,
    parse_filename,
    run_study,
    write_study,
)
from .substrate import (
    SUBSTRATES,
    condition_specs,
    run_substrate_study,
    write_substrate_study,
)
from .verifier import IndependentVerifier, Verdict
from .workspace import Workspace, evidence_artifact_path

__all__ = [
    "ACPError",
    "ACPPermissionDenied",
    "ACPResult",
    "AuthorityDecision",
    "AuthorityGate",
    "AuthorityGrant",
    "CONDITIONS",
    "ChainRecomputer",
    "ConfigurationError",
    "DATASET_SCALE_TOKENS",
    "DATASET_SCALE2_TOKENS",
    "SUBSTRATES",
    "acp_available",
    "condition_specs",
    "node_executable",
    "run_acp_task",
    "run_substrate_study",
    "write_substrate_study",
    "DispatchResult",
    "Episode",
    "EpisodeError",
    "EpisodeProducer",
    "FAMILIES",
    "FilterCountRecomputer",
    "GovernedRunner",
    "HardCountRecomputer",
    "HardSumRecomputer",
    "IndependentVerifier",
    "JUDGE_COMPARISON_SCHEMA",
    "JUDGE_FIXTURE_SCHEMA",
    "JudgeFixtureError",
    "parse_judge_filename",
    "run_judge_comparison",
    "validate_judge_fixture",
    "write_judge_comparison",
    "LocalProcessAdapter",
    "MODEL_SHORTS",
    "NATURAL_POWER_STUDY_SCHEMA",
    "NATURAL_SCALE_STUDY_SCHEMA",
    "NATURAL_STUDY_SCHEMA",
    "RecordCountRecomputer",
    "Recomputer",
    "RunReport",
    "SumRecomputer",
    "RunResult",
    "Verdict",
    "Workspace",
    "evidence_artifact_path",
    "load_episode",
    "parse_episode",
    "parse_filename",
    "parse_natural_filename",
    "parse_scale_filename",
    "replay_episode",
    "run_natural_power_study",
    "run_natural_scale_study",
    "run_natural_study",
    "run_study",
    "wilson_interval",
    "write_natural_study",
    "write_study",
]
