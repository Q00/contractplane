from __future__ import annotations

from dataclasses import dataclass


class ContractPlaneError(Exception):
    """Base class for expected, user-actionable kernel errors."""


@dataclass(frozen=True, order=True)
class ValidationIssue:
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


class DomainPackValidationError(ContractPlaneError):
    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]):
        self.issues = tuple(sorted(issues))
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(summary or "DomainPack is invalid")


class CompileError(ContractPlaneError):
    pass


class TransitionError(ContractPlaneError):
    pass


class LedgerError(ContractPlaneError):
    pass
