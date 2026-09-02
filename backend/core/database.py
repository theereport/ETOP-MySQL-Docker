from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, time as datetime_time
from decimal import Decimal
from typing import Any, Iterator, Mapping, Sequence

import mysql.connector
from dotenv import load_dotenv
from fastapi import HTTPException
from mysql.connector import MySQLConnection
from mysql.connector.cursor import MySQLCursorDict


# Loads backend/.env when the application starts.
load_dotenv()


SQL_TIMEOUT_SECONDS = int(
    os.getenv("SQL_TIMEOUT_SECONDS", "60")
)

logger = logging.getLogger(__name__)


class MaddenSnapshotReader:
    """Query-only reader bound to one consistent read-only transaction."""

    def __init__(self, cursor: MySQLCursorDict, snapshot_opened_at: str) -> None:
        self.cursor = cursor
        self.snapshot_opened_at = snapshot_opened_at

    def fetch_all(
        self,
        sql: str,
        parameters: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.cursor.execute(sql, parameters or ())
        return [
            {
                key: MaddenDatabase._serialize_value(value)
                for key, value in row.items()
            }
            for row in self.cursor.fetchall()
        ]

    def fetch_one(
        self,
        sql: str,
        parameters: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> dict[str, Any] | None:
        self.cursor.execute(sql, parameters or ())
        row = self.cursor.fetchone()
        if row is None:
            return None
        return {
            key: MaddenDatabase._serialize_value(value)
            for key, value in row.items()
        }


class MaddenDatabase:
    """
    Shared read-only connection service for the MaddenCo MySQL database.

    Available methods:
        fetch_all()
        fetch_one()
        fetch_scalar()
        load_schema_catalog()
        test_connection()

    This service intentionally does not provide INSERT, UPDATE, DELETE,
    or other write methods.
    """

    def __init__(self) -> None:
        self.config = self._get_mysql_config()

    @contextmanager
    def _cursor(
        self,
    ) -> Iterator[MySQLCursorDict]:
        """
        Opens a MySQL connection and dictionary cursor, applies the
        shared read-only session protections, and guarantees cleanup.
        """

        connection: MySQLConnection | None = None
        cursor: MySQLCursorDict | None = None

        try:
            connection = self._create_connection()
            cursor = connection.cursor(dictionary=True)

            self._configure_read_only_session(cursor)

            yield cursor

        except mysql.connector.Error as database_error:
            # This detail is deliberately still surfaced to the client, not
            # just logged: sql_workspace.py's whole point is showing a user
            # exactly why their own query failed (str(database_error.detail)
            # becomes the query's error message in query_history), and
            # schema_explorer.py already reveals this same table/column
            # metadata to any authorized user by design - genericizing this
            # message would break that debugging feature without actually
            # hiding anything schema_explorer doesn't already show. Logged
            # here too so a real operational failure (not a bad user query)
            # is visible server-side without needing to reproduce it.
            logger.exception("Madden database query failed.")
            raise HTTPException(
                status_code=400,
                detail=(
                    "Madden database query failed: "
                    f"{database_error}"
                ),
            ) from database_error

        finally:
            if cursor is not None:
                cursor.close()

            if (
                connection is not None
                and connection.is_connected()
            ):
                connection.close()

    def fetch_all(
        self,
        sql: str,
        parameters: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Executes a read-only query and returns every result as a dictionary.

        Named parameter example:

            WHERE TARONUMCST = %(customer_number)s

            {
                "customer_number": "123456"
            }

        Positional parameter example:

            WHERE TARONUMCST = %s

            ("123456",)
        """

        with self._cursor() as cursor:
            cursor.execute(
                sql,
                parameters or (),
            )

            rows = cursor.fetchall()

        return [
            {
                key: self._serialize_value(value)
                for key, value in row.items()
            }
            for row in rows
        ]

    def fetch_one(
        self,
        sql: str,
        parameters: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Executes a read-only query and returns the first row.
        """

        with self._cursor() as cursor:
            cursor.execute(
                sql,
                parameters or (),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return {
            key: self._serialize_value(value)
            for key, value in row.items()
        }

    def fetch_scalar(
        self,
        sql: str,
        parameters: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> Any:
        """
        Executes a read-only query and returns the first value
        from the first row.
        """

        row = self.fetch_one(
            sql=sql,
            parameters=parameters,
        )

        if not row:
            return None

        return next(iter(row.values()))

    @contextmanager
    def read_consistent_snapshot(self) -> Iterator[MaddenSnapshotReader]:
        """Run related reads in one bounded, read-only consistent snapshot.

        Snapshot setup is fail-closed: callers never silently fall back to
        unrelated autocommit reads and then label them a coherent packet.
        """

        connection: MySQLConnection | None = None
        cursor: MySQLCursorDict | None = None
        try:
            connection = self._create_connection()
            cursor = connection.cursor(dictionary=True)
            self._configure_read_only_session(cursor)
            connection.start_transaction(
                consistent_snapshot=True,
                readonly=True,
            )
            yield MaddenSnapshotReader(
                cursor,
                datetime.now(UTC).isoformat(),
            )
        except (mysql.connector.Error, ValueError) as database_error:
            logger.exception("Madden consistent read-only snapshot failed.")
            raise HTTPException(
                status_code=400,
                detail=(
                    "Madden consistent read-only snapshot failed: "
                    f"{database_error}"
                ),
            ) from database_error
        finally:
            if connection is not None and connection.is_connected():
                try:
                    connection.rollback()
                except mysql.connector.Error:
                    pass
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()

    def load_schema_catalog(self) -> dict[str, Any]:
        """
        Loads the active database schema for SQL AI and schema exploration.

        Returns:
            database
            objects
            object_count
            column_count
        """

        database_name = self.fetch_scalar(
            "SELECT DATABASE() AS database_name"
        )

        rows = self.fetch_all(
            """
            SELECT
                T.TABLE_NAME AS object_name,
                T.TABLE_TYPE AS object_type,
                T.TABLE_COMMENT AS object_comment,
                C.COLUMN_NAME AS column_name,
                C.ORDINAL_POSITION AS ordinal_position,
                C.COLUMN_TYPE AS column_type,
                C.IS_NULLABLE AS is_nullable,
                C.COLUMN_KEY AS column_key,
                C.COLUMN_COMMENT AS column_comment
            FROM INFORMATION_SCHEMA.TABLES T
            INNER JOIN INFORMATION_SCHEMA.COLUMNS C
                ON C.TABLE_SCHEMA = T.TABLE_SCHEMA
               AND C.TABLE_NAME = T.TABLE_NAME
            WHERE T.TABLE_SCHEMA = DATABASE()
            ORDER BY
                CASE
                    WHEN T.TABLE_TYPE = 'BASE TABLE' THEN 0
                    ELSE 1
                END,
                T.TABLE_NAME,
                C.ORDINAL_POSITION
            """
        )

        grouped_objects: dict[str, dict[str, Any]] = {}

        for row in rows:
            object_name = str(row["object_name"])

            if object_name not in grouped_objects:
                grouped_objects[object_name] = {
                    "name": object_name,
                    "type": (
                        "table"
                        if row["object_type"] == "BASE TABLE"
                        else "view"
                    ),
                    "comment": row["object_comment"] or "",
                    "columns": [],
                }

            grouped_objects[object_name]["columns"].append(
                {
                    "name": row["column_name"],
                    "position": int(row["ordinal_position"]),
                    "column_type": row["column_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "key": row["column_key"] or "",
                    "comment": row["column_comment"] or "",
                }
            )

        objects = list(grouped_objects.values())

        return {
            "database": database_name,
            "objects": objects,
            "object_count": len(objects),
            "column_count": sum(
                len(item["columns"])
                for item in objects
            ),
        }

    def test_connection(self) -> dict[str, Any]:
        """
        Tests the Madden database connection and returns server details.
        """

        result = self.fetch_one(
            """
            SELECT
                DATABASE() AS database_name,
                CURRENT_USER() AS connected_user,
                @@hostname AS server_name,
                VERSION() AS server_version
            """
        )

        return {
            "connected": result is not None,
            "database": (
                result.get("database_name")
                if result
                else None
            ),
            "user": (
                result.get("connected_user")
                if result
                else None
            ),
            "server": (
                result.get("server_name")
                if result
                else None
            ),
            "version": (
                result.get("server_version")
                if result
                else None
            ),
        }

    def _create_connection(
        self,
    ) -> MySQLConnection:
        """
        Creates a new MySQL connection using the shared backend settings.
        """

        return mysql.connector.connect(
            **self.config
        )

    @staticmethod
    def _configure_read_only_session(
        cursor: MySQLCursorDict,
    ) -> None:
        """
        Applies database-session read-only and timeout protections.

        The database login itself should also remain read-only.
        """

        try:
            cursor.execute(
                "SET SESSION TRANSACTION READ ONLY"
            )
        except mysql.connector.Error:
            # Some MySQL-compatible environments may not permit this.
            # The read-only database account still provides protection.
            pass

        try:
            cursor.execute(
                "SET SESSION MAX_EXECUTION_TIME = "
                f"{SQL_TIMEOUT_SECONDS * 1000}"
            )
        except mysql.connector.Error:
            pass

    @staticmethod
    def _get_mysql_config() -> dict[str, Any]:
        """
        Reads and validates the MySQL connection values from backend/.env.
        """

        required_values = {
            "host": os.getenv("MYSQL_HOST"),
            "database": os.getenv("MYSQL_DATABASE"),
            "user": os.getenv("MYSQL_USER"),
            "password": os.getenv("MYSQL_PASSWORD"),
        }

        missing = [
            key.upper()
            for key, value in required_values.items()
            if value is None or not value.strip()
        ]

        if missing:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Missing MySQL settings in backend/.env: "
                    + ", ".join(missing)
                ),
            )

        return {
            "host": required_values["host"],
            "port": int(
                os.getenv("MYSQL_PORT", "3306")
            ),
            "database": required_values["database"],
            "user": required_values["user"],
            "password": required_values["password"],
            "connection_timeout": int(
                os.getenv("MYSQL_CONNECTION_TIMEOUT", "10")
            ),
            "autocommit": True,
            "use_pure": True,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }

    @staticmethod
    def _serialize_value(
        value: Any,
    ) -> Any:
        """
        Converts MySQL values into forms that FastAPI can serialize.

        Decimal and date/time values are kept intact so repository and
        service layers can still perform calculations before FastAPI
        serializes the final response.
        """

        if value is None:
            return None

        if isinstance(value, Decimal):
            return value

        if isinstance(
            value,
            (datetime, date, datetime_time),
        ):
            return value

        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.hex()

        return value


# Shared instance that repositories, services, and API routes can import.
madden_database = MaddenDatabase()
