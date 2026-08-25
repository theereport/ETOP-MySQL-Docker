from __future__ import annotations

from typing import Any

from core.database import madden_database


class RouteRepository:
    """Read-only MaddenCo (DTA273) evidence for freight & logistics routes.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP. Routes are identified throughout by KMROUTES.RTECODE (the
    two-character route code), which is also the type/length MaddenCo uses
    for INWHLOAD.ROUTE. The WHSIG* family stores ROUTE as varchar(8); this
    repository still filters those tables by exact equality against the
    same route code string, since no other join key is available in the
    current schema (see the module README for this documented assumption).
    """

    def search_routes(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
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
                    TRIM(route.RTECODE) LIKE %s
                    OR TRIM(route.RTEKEY) LIKE %s
                    OR CAST(route.RTEWHSE AS CHAR) LIKE %s
                )
                """
            )
            parameters.extend([wildcard] * 3)

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(route.RTESTATUS), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            TRIM(route.RTEKEY) AS RTEKEY,
            TRIM(route.RTECODE) AS RTECODE,
            route.RTEWHSE,
            TRIM(route.RTESTATUS) AS RTESTATUS,
            TRIM(location.LOCATION_NAME) AS LOCATION_NAME
        FROM KMTDTA.KMROUTES AS route
        LEFT JOIN KMTDTA.WH_DASHBOARD_LOCATIONS AS location
            ON location.LOCATION_NUMBER = route.RTEWHSE
        {where_clause}
        ORDER BY TRIM(route.RTECODE), route.RTEWHSE
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_route(self, route_code: str) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                TRIM(route.RTEKEY) AS RTEKEY,
                TRIM(route.RTECODE) AS RTECODE,
                route.DLVSUN, route.DLVMON, route.DLVTUE, route.DLVWED,
                route.DLVTHU, route.DLVFRI, route.DLVSAT,
                route.NUMSUN, route.NUMMON, route.NUMTUE, route.NUMWED,
                route.NUMTHU, route.NUMFRI, route.NUMSAT,
                route.CRTDATE,
                TRIM(route.CRTUSER) AS CRTUSER,
                route.CHGDATE,
                TRIM(route.CHGUSER) AS CHGUSER,
                route.RTEWHSE,
                TRIM(route.RTESTATUS) AS RTESTATUS,
                TRIM(location.LOCATION_NAME) AS LOCATION_NAME
            FROM KMTDTA.KMROUTES AS route
            LEFT JOIN KMTDTA.WH_DASHBOARD_LOCATIONS AS location
                ON location.LOCATION_NUMBER = route.RTEWHSE
            WHERE TRIM(route.RTECODE) = %s
            LIMIT 1
            """,
            (route_code,),
        )

    def get_warehouse_directions(
        self,
        warehouse_number: int,
        route_code: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(directions.DIRECTION_NAME) AS DIRECTION_NAME,
                directions.MINIMUM_WEIGHT,
                directions.MAXIMUM_WEIGHT,
                directions.QUANTITY_LIMIT,
                TRIM(directions.LIMIT_BY) AS LIMIT_BY,
                TRIM(directions.ACTIVE) AS ACTIVE
            FROM KMTDTA.WH_DASHBOARD_ROUTES AS directions
            WHERE directions.LOCATION_NUMBER = %s
              AND FIND_IN_SET(
                    %s,
                    REPLACE(COALESCE(directions.INCLUDED_ROUTES, ''), ' ', '')
                  ) > 0
            ORDER BY directions.SORT_ORDER, directions.DIRECTION_NAME
            LIMIT %s
            """,
            (warehouse_number, route_code, limit),
        )

    def get_load_lines(
        self,
        route_code: str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                ld.STORENUM,
                TRIM(ld.ROUTE) AS ROUTE,
                TRIM(ld.STATUS) AS STATUS,
                ld.INVNUM,
                ld.CUSTNUM,
                ld.LINENUM,
                ld.SEQ,
                TRIM(ld.PRODNUM) AS PRODNUM,
                TRIM(ld.`DESC`) AS `DESC`,
                ld.WEIGHT,
                ld.QUANTITY,
                ld.CRTSTAMP,
                ld.DLVSTAMP
            FROM KMTDTA.INWHLOAD AS ld
            WHERE TRIM(ld.ROUTE) = %s
            ORDER BY ld.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_cod_payments(
        self,
        route_code: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                payment.ID,
                payment.CUSTNUM,
                TRIM(payment.ROUTE) AS ROUTE,
                TRIM(payment.TYPE) AS TYPE,
                TRIM(payment.CHECKNUM) AS CHECKNUM,
                TRIM(payment.AUTHNUM) AS AUTHNUM,
                payment.AMOUNT,
                TRIM(payment.NOTES) AS NOTES,
                TRIM(payment.INVOICES) AS INVOICES,
                TRIM(payment.RECEIVED) AS RECEIVED,
                payment.RECSTAMP,
                payment.CRTSTAMP
            FROM KMTDTA.WHSIGPAY AS payment
            WHERE TRIM(payment.ROUTE) = %s
            ORDER BY payment.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_payment_corrections(
        self,
        route_code: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                payment.ID AS PAYMENT_ID,
                TRIM(correction.FIELD) AS FIELD,
                TRIM(correction.BEFORE) AS BEFORE_VALUE,
                TRIM(correction.AFTER) AS AFTER_VALUE,
                TRIM(correction.REASON) AS REASON,
                TRIM(correction.CRTUSER) AS CRTUSER,
                correction.CRTSTAMP
            FROM KMTDTA.WHSIGPAYC AS correction
            INNER JOIN KMTDTA.WHSIGPAY AS payment
                ON CAST(payment.ID AS CHAR) COLLATE utf8mb4_0900_ai_ci
                    = TRIM(correction.PAYMENTID)
            WHERE TRIM(payment.ROUTE) = %s
            ORDER BY correction.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_payment_details(
        self,
        route_code: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                payment.ID AS PAYMENT_ID,
                TRIM(detail.NOTES) AS NOTES,
                detail.CRTSTAMP,
                TRIM(detail.CRTUSER) AS CRTUSER
            FROM KMTDTA.WHSIGPAY AS payment STRAIGHT_JOIN KMTDTA.WHSIGPAYD AS detail
                ON detail.PAYMENTID = payment.ID
            WHERE TRIM(payment.ROUTE) = %s
            ORDER BY detail.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_delivery_exceptions(
        self,
        route_code: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                exception_note.CUSTNUM,
                TRIM(exception_note.ROUTE) AS ROUTE,
                exception_note.INVNUM,
                exception_note.LINENUM,
                exception_note.QUANTITY,
                TRIM(exception_note.OPTION) AS OPTION_CODE,
                TRIM(exception_note.NOTES) AS NOTES,
                TRIM(exception_note.APPROVED) AS APPROVED,
                exception_note.CREDITINV,
                TRIM(exception_note.APPNOTES) AS APPNOTES,
                TRIM(exception_note.APPROVBY) AS APPROVBY,
                exception_note.CRTSTAMP,
                exception_note.APPRSTAMP
            FROM KMTDTA.WHSIGNOTE AS exception_note
            WHERE TRIM(exception_note.ROUTE) = %s
            ORDER BY exception_note.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_delivery_adjustments(
        self,
        route_code: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(adjustment.ROUTE) AS ROUTE,
                adjustment.INVNUM,
                adjustment.CUSTNUM,
                adjustment.LINENUM,
                adjustment.SEQ,
                TRIM(adjustment.LINETYPE) AS LINETYPE,
                TRIM(adjustment.PRODNUM) AS PRODNUM,
                TRIM(adjustment.`DESC`) AS `DESC`,
                adjustment.QUANTITY,
                adjustment.CRTSTAMP,
                adjustment.UPLDSTAMP
            FROM KMTDTA.WHSIGADJ AS adjustment
            WHERE TRIM(adjustment.ROUTE) = %s
            ORDER BY adjustment.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_signature_sessions(
        self,
        route_code: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(session.SERIALNUM) AS SERIALNUM,
                TRIM(session.ROUTE) AS ROUTE,
                TRIM(session.RTETYPE) AS RTETYPE,
                session.CRTSTAMP,
                TRIM(session.CRTUSER) AS CRTUSER
            FROM KMTDTA.WHSIGRTE AS session
            WHERE TRIM(session.ROUTE) = %s
            ORDER BY session.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )

    def get_signature_images(
        self,
        route_code: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT DISTINCT
                image.CUSTNUM,
                image.INVNUM,
                TRIM(image.SIGNAME) AS SIGNAME,
                TRIM(image.FILENAME) AS FILENAME,
                image.CRTSTAMP,
                image.UPLDSTAMP
            FROM KMTDTA.INWHLOAD AS ld STRAIGHT_JOIN KMTDTA.WHSIGIMG AS image
                ON image.INVNUM = ld.INVNUM
               AND image.CUSTNUM = ld.CUSTNUM
            WHERE TRIM(ld.ROUTE) = %s
            ORDER BY image.CRTSTAMP DESC
            LIMIT %s
            """,
            (route_code, limit),
        )


route_repository = RouteRepository()
