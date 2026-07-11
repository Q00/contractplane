"""ContractPlane reference kernel."""

from .compiler import ExecutionPlan, compile_plan
from .ledger import JsonlLedger
from .loader import load_domain_pack, parse_domain_pack
from .models import (
    Capability,
    CapabilityBinding,
    CapabilityKind,
    DomainPack,
    EntryPoint,
    Evidence,
    EvidenceKind,
    Fanout,
    FanoutMode,
    Flow,
    HumanApproval,
    Metadata,
    Policy,
    Role,
    SideEffect,
    Stage,
)
from .state import ExecutionMachine, ExecutionStatus, StageStatus, UnitRef, UnitStatus

__all__ = [
    "DomainPack",
    "Capability",
    "CapabilityBinding",
    "CapabilityKind",
    "EntryPoint",
    "Evidence",
    "EvidenceKind",
    "ExecutionMachine",
    "ExecutionPlan",
    "ExecutionStatus",
    "JsonlLedger",
    "Fanout",
    "FanoutMode",
    "Flow",
    "HumanApproval",
    "Metadata",
    "Policy",
    "Role",
    "SideEffect",
    "Stage",
    "StageStatus",
    "UnitRef",
    "UnitStatus",
    "compile_plan",
    "load_domain_pack",
    "parse_domain_pack",
]

__version__ = "0.1.0a1"
