from __future__ import annotations

import sys
import types
import unittest

try:
    from fastapi import HTTPException
except ModuleNotFoundError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi_stub

from core.sql_validator import normalize_and_validate_sql


class ReadOnlySqlValidatorTests(unittest.TestCase):
    def assert_blocked(self, sql: str, expected_text: str) -> None:
        with self.assertRaises(HTTPException) as raised:
            normalize_and_validate_sql(sql)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn(expected_text, str(raised.exception.detail))

    def test_allows_replace_scalar_function_in_report_expression(self) -> None:
        sql = """
            SELECT
                CASE
                    WHEN CHAR_LENGTH(REPLACE(T01.TIHLNUMINV, ' ', '')) = 8
                    THEN LEFT(REPLACE(T01.TIHLNUMINV, ' ', ''), 1)
                    ELSE REPLACE(T01.TIHLNUMINV, ' ', '')
                END AS store_number
            FROM DTA273.TMIHSL AS T01
        """

        self.assertEqual(normalize_and_validate_sql(sql), sql.strip())

    def test_allows_nested_replace_scalar_functions(self) -> None:
        sql = "SELECT REPLACE(REPLACE(customer_name, '-', ''), ' ', '') FROM TMCUST"

        self.assertEqual(normalize_and_validate_sql(sql), sql)

    def test_replace_words_in_strings_and_comments_are_not_commands(self) -> None:
        sql = "SELECT 'REPLACE INTO audit_log' AS note /* REPLACE customer */"

        self.assertEqual(normalize_and_validate_sql(sql), sql)

    def test_blocks_replace_into_as_first_statement_keyword(self) -> None:
        self.assert_blocked(
            "REPLACE INTO report_cache (report_id) VALUES (1)",
            "beginning with REPLACE",
        )

    def test_blocks_replace_into_after_with_clause(self) -> None:
        self.assert_blocked(
            "WITH source AS (SELECT 1 AS report_id) "
            "REPLACE INTO report_cache (report_id) SELECT report_id FROM source",
            "blocked SQL command: REPLACE",
        )

    def test_blocks_mysql_replace_command_when_into_is_omitted(self) -> None:
        self.assert_blocked(
            "WITH source AS (SELECT 1 AS report_id) "
            "REPLACE report_cache (report_id) SELECT report_id FROM source",
            "blocked SQL command: REPLACE",
        )

    def test_other_write_commands_remain_blocked(self) -> None:
        self.assert_blocked(
            "WITH source AS (SELECT 1 AS report_id) "
            "UPDATE report_cache SET report_id = 2",
            "blocked SQL command: UPDATE",
        )

    def test_file_writing_select_remains_blocked(self) -> None:
        self.assert_blocked(
            "SELECT report_id FROM report_cache INTO OUTFILE '/tmp/report.csv'",
            "blocked SQL command: INTO OUTFILE",
        )


if __name__ == "__main__":
    unittest.main()
