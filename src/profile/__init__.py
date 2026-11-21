"""Client profile: who the person is financially, what they want, and the rules they agreed to invest by."""

from src.profile.schema import (
    ASSET_CLASSES,
    SCHEMA_VERSION,
    AllocationTarget,
    ClientProfile,
    Goal,
    InvestmentPolicy,
    merge_profile,
)

__all__ = [
    "ASSET_CLASSES",
    "SCHEMA_VERSION",
    "AllocationTarget",
    "ClientProfile",
    "Goal",
    "InvestmentPolicy",
    "merge_profile",
]
