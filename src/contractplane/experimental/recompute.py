"""Recomputation-based ground-truth checks for the independent verifier.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

A schema check only proves an artifact is *well-shaped*; it cannot prove the
artifact tells the truth, because the artifact was authored by the producer. A
recomputer closes that gap for *mechanically recomputable* evidence: it derives
the checked quantity **from the raw input data itself**, never from the
producer's artifact, so the verifier can compare the producer's claim against an
independently computed ground truth.

Three reference recomputers cover three mechanically recomputable task families
over the caller-owned datasets: :class:`RecordCountRecomputer` (a record count),
:class:`SumRecomputer` (a numeric column total), and
:class:`FilterCountRecomputer` (a count of values above a flow-defined
threshold). :class:`ChainRecomputer` composes them so one verifier can serve
several flows, dispatching by evidence id.

Honesty boundary: this demonstrates recomputation-based independence for evidence
that a deterministic function can re-derive. The broader *typed independence
spectrum* — distinct-model verifiers, human verifiers, and evidence that is not
mechanically recomputable — remains specified-only and is deliberately out of
scope for this prototype.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..compiler import CompiledStage


@runtime_checkable
class Recomputer(Protocol):
    """Recompute the expected value of checked fields from raw input data.

    Returns a mapping of ``{artifact_field: expected_value}`` that the verifier
    must find in the producer's artifact, or ``None`` when this evidence is not
    mechanically recomputable (the verifier then falls back to schema-only and
    says so in its verdict).
    """

    def recompute(
        self, stage: CompiledStage, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class RecordCountRecomputer:
    """Reference recomputer for the governed-run demo's report evidence.

    Ground truth for ``rows`` is the number of records in the caller-owned,
    read-only dataset named by the flow input — a source the producer does not
    author. The verifier counts those records itself and rejects any artifact
    whose ``rows`` disagrees, even if that artifact passes schema validation.
    """

    datasets_dir: Path
    evidence_ids: frozenset[str] = frozenset({"report-artifact"})
    dataset_key: str = "dataset"
    records_key: str = "records"
    expect_field: str = "rows"

    def recompute(
        self, stage: CompiledStage, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        dataset = (inputs or {}).get(self.dataset_key)
        if not isinstance(dataset, str) or not dataset:
            return None
        source = Path(self.datasets_dir) / f"{dataset}.json"
        if not source.is_file():
            return None
        data = json.loads(source.read_text(encoding="utf-8"))
        records = data.get(self.records_key, [])
        if not isinstance(records, list):
            return None
        return {self.expect_field: len(records)}


def _numeric_values(datasets_dir: Path, dataset: Any, values_key: str) -> list[float] | None:
    """Load the caller-owned numeric column for ``dataset``, or ``None``."""
    if not isinstance(dataset, str) or not dataset:
        return None
    source = Path(datasets_dir) / f"{dataset}.json"
    if not source.is_file():
        return None
    values = json.loads(source.read_text(encoding="utf-8")).get(values_key, [])
    if not isinstance(values, list):
        return None
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return None
    return values


@dataclass(frozen=True)
class SumRecomputer:
    """Recompute the total of a numeric column from the caller-owned dataset.

    Ground truth for ``total`` is the sum of the dataset's ``values`` column,
    computed here rather than trusted from the producer's artifact.
    """

    datasets_dir: Path
    evidence_ids: frozenset[str] = frozenset({"aggregate-artifact"})
    dataset_key: str = "dataset"
    values_key: str = "values"
    expect_field: str = "total"

    def recompute(
        self, stage: CompiledStage, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        values = _numeric_values(self.datasets_dir, (inputs or {}).get(self.dataset_key), self.values_key)
        if values is None:
            return None
        total = sum(values)
        # Sums over integer columns stay integers; keep the type stable.
        if all(isinstance(value, int) for value in values):
            total = int(total)
        return {self.expect_field: total}


@dataclass(frozen=True)
class FilterCountRecomputer:
    """Recompute the count of values above a flow-defined threshold.

    The predicate threshold is defined by the flow, read here from the stage's
    compiled binding config (``config.threshold``). Ground truth for ``matches``
    is recomputed from the dataset's ``values`` column, never trusted from the
    producer's artifact.
    """

    datasets_dir: Path
    evidence_ids: frozenset[str] = frozenset({"filter-count-artifact"})
    dataset_key: str = "dataset"
    values_key: str = "values"
    expect_field: str = "matches"
    threshold_config_key: str = "threshold"
    default_threshold: float = 0

    def _threshold(self, stage: CompiledStage) -> float:
        binding = getattr(stage, "binding", None) or {}
        config = binding.get("config") or {}
        threshold = config.get(self.threshold_config_key, self.default_threshold)
        return threshold if isinstance(threshold, (int, float)) else self.default_threshold

    def recompute(
        self, stage: CompiledStage, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        values = _numeric_values(self.datasets_dir, (inputs or {}).get(self.dataset_key), self.values_key)
        if values is None:
            return None
        threshold = self._threshold(stage)
        return {self.expect_field: sum(1 for value in values if value > threshold)}


class ChainRecomputer:
    """Compose several recomputers; the first to claim an evidence id wins.

    Each member returns ``None`` for evidence it does not own, so a single
    verifier can serve multiple task families by trying them in order.
    """

    def __init__(self, recomputers: Any):
        self._recomputers = tuple(recomputers)

    def recompute(
        self, stage: CompiledStage, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        for recomputer in self._recomputers:
            result = recomputer.recompute(stage, evidence_id, inputs)
            if result is not None:
                return result
        return None
