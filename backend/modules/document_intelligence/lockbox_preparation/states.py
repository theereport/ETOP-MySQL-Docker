"""Explicit file and transaction state machines."""

from __future__ import annotations

from enum import StrEnum

from .errors import StateTransitionError


class FileState(StrEnum):
    REGISTERED = "registered"
    QUEUED = "queued"
    RUNNING = "running"
    RECOVERING = "recovering"
    COMPLETE = "complete"


class TransactionState(StrEnum):
    IDENTIFIED = "identified"
    QUEUED = "queued"
    RESOLVING_CUSTOMER = "resolving_customer"
    LOADING_OPEN_AR = "loading_open_ar"
    EVALUATING_ALLOCATION = "evaluating_allocation"
    RETRY_PENDING = "retry_pending"
    PREPARED_BALANCED = "prepared_balanced"
    PREPARED_EXCEPTION = "prepared_exception"
    PREEXISTING_HUMAN_DISPOSITION = "preexisting_human_disposition"


TERMINAL_TRANSACTION_STATES = frozenset(
    {
        TransactionState.PREPARED_BALANCED,
        TransactionState.PREPARED_EXCEPTION,
        TransactionState.PREEXISTING_HUMAN_DISPOSITION,
    }
)

ACTIVE_TRANSACTION_STATES = frozenset(
    {
        TransactionState.QUEUED,
        TransactionState.RESOLVING_CUSTOMER,
        TransactionState.LOADING_OPEN_AR,
        TransactionState.EVALUATING_ALLOCATION,
    }
)

_FILE_TRANSITIONS: dict[FileState, frozenset[FileState]] = {
    FileState.REGISTERED: frozenset({FileState.QUEUED}),
    FileState.QUEUED: frozenset({FileState.RUNNING, FileState.RECOVERING}),
    FileState.RUNNING: frozenset({FileState.RECOVERING, FileState.COMPLETE}),
    FileState.RECOVERING: frozenset({FileState.RUNNING, FileState.COMPLETE}),
    FileState.COMPLETE: frozenset({FileState.QUEUED}),
}

_TRANSACTION_TRANSITIONS: dict[
    TransactionState,
    frozenset[TransactionState],
] = {
    TransactionState.IDENTIFIED: frozenset(
        {
            TransactionState.QUEUED,
            TransactionState.PREEXISTING_HUMAN_DISPOSITION,
        }
    ),
    TransactionState.QUEUED: frozenset(
        {
            TransactionState.RESOLVING_CUSTOMER,
            TransactionState.PREPARED_EXCEPTION,
            TransactionState.RETRY_PENDING,
        }
    ),
    TransactionState.RESOLVING_CUSTOMER: frozenset(
        {
            TransactionState.LOADING_OPEN_AR,
            TransactionState.PREPARED_EXCEPTION,
            TransactionState.RETRY_PENDING,
        }
    ),
    TransactionState.LOADING_OPEN_AR: frozenset(
        {
            TransactionState.EVALUATING_ALLOCATION,
            TransactionState.PREPARED_EXCEPTION,
            TransactionState.RETRY_PENDING,
        }
    ),
    TransactionState.EVALUATING_ALLOCATION: frozenset(
        {
            TransactionState.PREPARED_BALANCED,
            TransactionState.PREPARED_EXCEPTION,
            TransactionState.RETRY_PENDING,
        }
    ),
    TransactionState.RETRY_PENDING: frozenset(
        {
            TransactionState.QUEUED,
            TransactionState.PREPARED_EXCEPTION,
        }
    ),
    TransactionState.PREPARED_EXCEPTION: frozenset(
        {TransactionState.RETRY_PENDING}
    ),
    TransactionState.PREPARED_BALANCED: frozenset(),
    TransactionState.PREEXISTING_HUMAN_DISPOSITION: frozenset(),
}


def validate_file_transition(
    current: FileState | str,
    target: FileState | str,
) -> bool:
    """Validate a file transition; a repeated state is idempotent."""

    current_state = FileState(current)
    target_state = FileState(target)
    if current_state == target_state:
        return False
    if target_state not in _FILE_TRANSITIONS[current_state]:
        raise StateTransitionError(
            f"Invalid file transition: {current_state.value} -> "
            f"{target_state.value}."
        )
    return True


def validate_transaction_transition(
    current: TransactionState | str,
    target: TransactionState | str,
) -> bool:
    """Validate a transaction transition; a repeated state is idempotent."""

    current_state = TransactionState(current)
    target_state = TransactionState(target)
    if current_state == target_state:
        return False
    if target_state not in _TRANSACTION_TRANSITIONS[current_state]:
        raise StateTransitionError(
            f"Invalid transaction transition: {current_state.value} -> "
            f"{target_state.value}."
        )
    return True


def is_terminal_transaction(state: TransactionState | str) -> bool:
    return TransactionState(state) in TERMINAL_TRANSACTION_STATES

