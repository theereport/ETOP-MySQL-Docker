"""Durable, local, read-only Lockbox preparation.

The package is intentionally not registered in the shared application yet.
Agent 4 owns provider binding and router registration after independent review.
"""

from .contracts import (
    AllocationRecommendation,
    CustomerResolution,
    CustomerSnapshot,
    InvoiceOwnerEvidence,
    OpenARSnapshot,
    OpenInvoice,
    ReadOnlyPreparationProvider,
    SourceTransaction,
    StartPreparationRequest,
)
from .coordinator import DurableLockboxPreparationCoordinator
from .customer_conflict import (
    CUSTOMER_CONFLICT_RULE_VERSION,
    CustomerConflictAssessment,
)
from .repository import LockboxPreparationRepository
from .reason_codes import CLASSIFIER_VERSION, build_exception_summary
from .service import DurableLockboxPreparationService

__all__ = [
    "AllocationRecommendation",
    "CLASSIFIER_VERSION",
    "CUSTOMER_CONFLICT_RULE_VERSION",
    "CustomerConflictAssessment",
    "CustomerResolution",
    "CustomerSnapshot",
    "DurableLockboxPreparationCoordinator",
    "DurableLockboxPreparationService",
    "InvoiceOwnerEvidence",
    "LockboxPreparationRepository",
    "OpenARSnapshot",
    "OpenInvoice",
    "ReadOnlyPreparationProvider",
    "SourceTransaction",
    "StartPreparationRequest",
    "build_exception_summary",
]
