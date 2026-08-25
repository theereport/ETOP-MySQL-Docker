from __future__ import annotations

from typing import Protocol

from .models import (
    CashApplicationDataBundle,
    CustomerResolutionMatch,
    LockboxCustomerIdentity,
)


class CashApplicationDataProvider(Protocol):
    def resolve_customer(
        self,
        identity: LockboxCustomerIdentity,
    ) -> CustomerResolutionMatch | None:
        ...

    def load_customer_data(
        self,
        customer_number: str,
    ) -> CashApplicationDataBundle:
        ...


class UnconfiguredCashApplicationDataProvider:
    def resolve_customer(
        self,
        identity: LockboxCustomerIdentity,
    ) -> CustomerResolutionMatch | None:
        if identity.customer_number:
            return CustomerResolutionMatch(
                customer_number=identity.customer_number,
                customer_name=identity.customer_name,
                confidence=1.0,
                matched_on=["customer number supplied by lockbox transaction"],
            )

        raise RuntimeError(
            "Cash application customer resolution is not connected to the "
            "existing customer lookup service."
        )

    def load_customer_data(
        self,
        customer_number: str,
    ) -> CashApplicationDataBundle:
        raise RuntimeError(
            "Cash application aging and open-invoice retrieval are not connected."
        )
