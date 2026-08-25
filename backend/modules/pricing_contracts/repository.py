from __future__ import annotations

from typing import Any

from core.database import madden_database


# TMDISC lives in the connected DTA273 schema. CLASSES and CUCLASSES, per the
# MYSQL Dictionary extract, live in a separate KMTDTA schema on the same
# MySQL server. The join below therefore uses a fully-qualified
# `KMTDTA.CLASSES` / `KMTDTA.CUCLASSES` reference rather than an unqualified
# table name. This assumes the read-only application login has SELECT grants
# on KMTDTA in addition to DTA273 — that has not been independently verified
# against the live server and should be confirmed before relying on
# `product_class_label` in production. If the grant is missing, MySQL raises
# an access-denied error for the join, which surfaces as a 400 through the
# shared `madden_database` error handling rather than a silent wrong answer.
CLASSES_TABLE = "KMTDTA.CLASSES"
CUCLASSES_TABLE = "KMTDTA.CUCLASSES"


class PricingContractsRepository:
    """Read-only MaddenCo (DTA273 + KMTDTA) evidence for pricing overrides.

    Every method issues a parameterized SELECT through the shared read-only
    `madden_database` gateway. This repository never writes to the ERP.
    """

    def search_discounts(
        self,
        *,
        customer_number: int | None = None,
        product_number: str = "",
        product_class: str = "",
        vendor_code: str = "",
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        if customer_number is not None:
            conditions.append("DCCUSTNO = %s")
            parameters.append(customer_number)

        product_number_value = product_number.strip()
        if product_number_value:
            conditions.append("TRIM(DCPRODNO) LIKE %s")
            parameters.append(f"%{product_number_value}%")

        product_class_value = product_class.strip()
        if product_class_value:
            conditions.append("TRIM(DCPRODCLAS) = %s")
            parameters.append(product_class_value)

        vendor_code_value = vendor_code.strip()
        if vendor_code_value:
            conditions.append("TRIM(DCVENDOR) = %s")
            parameters.append(vendor_code_value)

        if active_only:
            conditions.append("COALESCE(NULLIF(TRIM(DCDELETE), ''), '') = ''")

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            discount.DCCUSTNO,
            discount.DCVENDOR,
            discount.DCPRODCLAS,
            discount.DCPRODNO,
            discount.DCPRODTYPE,
            discount.DCDELETE,
            discount.DCAMTFIX,
            discount.DCCHAIN,
            discount.DCFACTOR,
            discount.DCPRICE,
            discount.DCPRICECD,
            discount.DCDTEADD,
            discount.DCDTECHG,
            discount.DCTIMADD,
            discount.DCTIMCHG,
            discount.DCUSRADD,
            discount.DCUSRCHG,
            TRIM(product_class.CLASSNAME) AS PRODCLASSNAME,
            TRIM(product_class.ITEMTYPE) AS PRODCLASSITEMTYPE,
            TRIM(product_class.ACTIVE) AS PRODCLASSACTIVE
        FROM TMDISC AS discount
        LEFT JOIN {CLASSES_TABLE} AS product_class
            ON TRIM(product_class.CLASSNUM) = TRIM(discount.DCPRODCLAS)
        {where_clause}
        ORDER BY
            discount.DCCUSTNO,
            discount.DCPRODCLAS,
            discount.DCPRODNO,
            discount.DCPRODTYPE,
            discount.DCVENDOR
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_discount(
        self,
        *,
        customer_number: int,
        vendor_code: str,
        product_class: str,
        product_number: str,
        product_type: str,
    ) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            f"""
            SELECT
                discount.DCCUSTNO,
                discount.DCVENDOR,
                discount.DCPRODCLAS,
                discount.DCPRODNO,
                discount.DCPRODTYPE,
                discount.DCDELETE,
                discount.DCAMTFIX,
                discount.DCCHAIN,
                discount.DCFACTOR,
                discount.DCPRICE,
                discount.DCPRICECD,
                discount.DCDTEADD,
                discount.DCDTECHG,
                discount.DCTIMADD,
                discount.DCTIMCHG,
                discount.DCUSRADD,
                discount.DCUSRCHG,
                TRIM(product_class.CLASSNAME) AS PRODCLASSNAME,
                TRIM(product_class.ITEMTYPE) AS PRODCLASSITEMTYPE,
                TRIM(product_class.ACTIVE) AS PRODCLASSACTIVE
            FROM TMDISC AS discount
            LEFT JOIN {CLASSES_TABLE} AS product_class
                ON TRIM(product_class.CLASSNUM) = TRIM(discount.DCPRODCLAS)
            WHERE discount.DCCUSTNO = %s
              AND TRIM(discount.DCVENDOR) = %s
              AND TRIM(discount.DCPRODCLAS) = %s
              AND TRIM(discount.DCPRODNO) = %s
              AND TRIM(discount.DCPRODTYPE) = %s
            LIMIT 1
            """,
            (
                customer_number,
                vendor_code.strip(),
                product_class.strip(),
                product_number.strip(),
                product_type.strip(),
            ),
        )

    def get_customer_classes(
        self,
        *,
        search: str = "",
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        search_value = search.strip()
        if search_value:
            wildcard = f"%{search_value}%"
            conditions.append(
                """
                (
                    TRIM(CLASSNUM) LIKE %s
                    OR TRIM(CLASSNAME) LIKE %s
                )
                """
            )
            parameters.extend([wildcard, wildcard])

        if active_only:
            conditions.append("TRIM(ACTIVE) = 'Y'")

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            ID,
            TRIM(CLASSNUM) AS CLASSNUM,
            TRIM(CLASSNAME) AS CLASSNAME,
            TRIM(ACTIVE) AS ACTIVE,
            CRTSTAMP,
            TRIM(CRTUSER) AS CRTUSER,
            CHGSTAMP,
            TRIM(CHGUSER) AS CHGUSER
        FROM {CUCLASSES_TABLE}
        {where_clause}
        ORDER BY TRIM(CLASSNUM)
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)


pricing_contracts_repository = PricingContractsRepository()
