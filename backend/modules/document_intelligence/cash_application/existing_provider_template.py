from __future__ import annotations

from .data_provider import CashApplicationDataProvider
from .models import (
    CashApplicationDataBundle,
    CustomerResolutionMatch,
    LockboxCustomerIdentity,
)


class ExistingCashApplicationProvider(CashApplicationDataProvider):
    """
    Adapter for the existing ERP customer/open-invoice connection.

    Replace only the repository method names below with the exact method names
    already used elsewhere in ETOP.
    """

    def __init__(
        self,
        customer_repository,
        cash_application_repository,
    ):
        self.customer_repository = customer_repository
        self.cash_application_repository = cash_application_repository

    def resolve_customer(
        self,
        identity: LockboxCustomerIdentity,
    ) -> CustomerResolutionMatch | None:
        if identity.customer_number:
            customer = self.customer_repository.get_customer(
                identity.customer_number
            )
            if customer:
                return CustomerResolutionMatch(
                    customer_number=str(customer.customer_number),
                    customer_name=str(customer.customer_name or ""),
                    confidence=1.0,
                    matched_on=["customer number"],
                )

        candidates = self.customer_repository.search_customers(
            name=identity.customer_name,
            phone=identity.customer_phone,
            address_line_1=identity.customer_address_line_1,
            city=identity.customer_city,
            state=identity.customer_state,
            postal_code=identity.customer_postal_code,
            aba_routing=identity.aba_routing,
            account_number=identity.account_number,
        )

        if not candidates:
            return None

        best = candidates[0]

        return CustomerResolutionMatch(
            customer_number=str(best.customer_number),
            customer_name=str(best.customer_name or ""),
            confidence=float(getattr(best, "confidence", 0.90)),
            matched_on=list(
                getattr(best, "matched_on", ["existing customer lookup"])
            ),
        )

    def load_customer_data(
        self,
        customer_number: str,
    ) -> CashApplicationDataBundle:
        aging = self.cash_application_repository.get_customer_aging(
            customer_number
        )
        invoices = self.cash_application_repository.get_open_invoices(
            customer_number
        )

        return CashApplicationDataBundle(
            customer_number=customer_number,
            aging=aging,
            invoices=invoices,
        )
