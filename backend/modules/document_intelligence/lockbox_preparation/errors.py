"""Domain errors for durable Lockbox preparation."""


class LockboxPreparationError(RuntimeError):
    """Base error for the durable preparation unit."""


class StateTransitionError(LockboxPreparationError):
    """Raised when a file or transaction transition is not permitted."""


class IdempotencyConflictError(LockboxPreparationError):
    """Raised when an idempotency key is reused for different source work."""


class FullCoverageError(LockboxPreparationError):
    """Raised when a file is finalized without terminal transaction coverage."""


class PreparationPolicyError(LockboxPreparationError):
    """Raised when a deterministic allocation/sign rule is violated."""


class ReadOnlyProviderUnavailable(LockboxPreparationError):
    """A read-only ERP dependency is temporarily unavailable."""

