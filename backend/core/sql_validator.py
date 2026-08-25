from __future__ import annotations

import re

from fastapi import HTTPException


ALLOWED_STARTING_KEYWORDS = {
    "SELECT",
    "WITH",
    "SHOW",
    "DESCRIBE",
    "DESC",
    "EXPLAIN",
}

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "UPSERT",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "RENAME",
    "GRANT",
    "REVOKE",
    "LOCK",
    "UNLOCK",
    "CALL",
    "EXEC",
    "EXECUTE",
    "LOAD",
    "HANDLER",
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "SET PASSWORD",
    "START TRANSACTION",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE SAVEPOINT",
    "KILL",
    "SHUTDOWN",
    "INSTALL",
    "UNINSTALL",
}

# MySQL uses REPLACE in two very different ways:
#
#   SELECT REPLACE(column_name, ' ', '')  -- read-only scalar function
#   REPLACE INTO table_name ...           -- data-changing statement
#
# The generic forbidden-keyword scan cannot distinguish those forms. Admit
# only the function form (the token must be followed by an opening parenthesis)
# and reject every command-shaped occurrence, including WITH ... REPLACE and
# MySQL's optional-INTO syntax: REPLACE table_name (...).
REPLACE_COMMAND_PATTERN = re.compile(r"\bREPLACE\b(?!\s*\()")

READ_UNCOMMITTED_PREFIX = re.compile(
    r"""
    ^\s*
    SET\s+
    (?:SESSION\s+)?
    TRANSACTION\s+
    ISOLATION\s+
    LEVEL\s+
    READ\s+
    UNCOMMITTED
    \s*;
    """,
    re.IGNORECASE | re.VERBOSE,
)


def remove_comments_and_strings(sql: str) -> str:
    """
    Remove SQL comments and quoted-string contents before security scanning.

    This prevents harmless text such as:

        SELECT 'delete this text'

    from being incorrectly blocked.
    """

    result: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        character = sql[index]

        if character in {"'", '"', "`"}:
            quote = character
            result.append(" ")
            index += 1

            while index < length:
                current = sql[index]

                if current == "\\":
                    index += 2
                    continue

                if current == quote:
                    if (
                        index + 1 < length
                        and sql[index + 1] == quote
                    ):
                        index += 2
                        continue

                    index += 1
                    break

                index += 1

            continue

        if (
            character == "-"
            and index + 1 < length
            and sql[index + 1] == "-"
        ):
            index += 2

            while index < length and sql[index] not in "\r\n":
                index += 1

            result.append(" ")
            continue

        if character == "#":
            index += 1

            while index < length and sql[index] not in "\r\n":
                index += 1

            result.append(" ")
            continue

        if (
            character == "/"
            and index + 1 < length
            and sql[index + 1] == "*"
        ):
            end_position = sql.find("*/", index + 2)

            if end_position == -1:
                raise HTTPException(
                    status_code=400,
                    detail="The SQL contains an unclosed block comment.",
                )

            index = end_position + 2
            result.append(" ")
            continue

        result.append(character)
        index += 1

    return "".join(result)


def count_sql_statements(sql: str) -> int:
    sanitized = remove_comments_and_strings(sql)

    statements = [
        statement.strip()
        for statement in sanitized.split(";")
        if statement.strip()
    ]

    return len(statements)


def normalize_and_validate_sql(raw_sql: str) -> str:
    """
    Normalize and validate one read-only SQL statement.

    Allowed:
        SELECT
        WITH
        SHOW
        DESCRIBE
        DESC
        EXPLAIN
    """

    sql = raw_sql.strip()

    if not sql:
        raise HTTPException(
            status_code=400,
            detail="Enter a SQL query before running it.",
        )

    # Existing Workbench queries may begin with this statement.
    # The application removes it and controls the session itself.
    sql = READ_UNCOMMITTED_PREFIX.sub(
        "",
        sql,
        count=1,
    ).strip()

    if not sql:
        raise HTTPException(
            status_code=400,
            detail="No executable read-only query was found.",
        )

    statement_count = count_sql_statements(sql)

    if statement_count > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only one SQL statement can be executed at a time. "
                "Remove any additional statements."
            ),
        )

    sql = sql.rstrip().rstrip(";").strip()

    sanitized = remove_comments_and_strings(sql)
    normalized = re.sub(
        r"\s+",
        " ",
        sanitized,
    ).strip().upper()

    first_keyword_match = re.match(
        r"^([A-Z]+)",
        normalized,
    )

    if not first_keyword_match:
        raise HTTPException(
            status_code=400,
            detail="The SQL statement could not be identified.",
        )

    first_keyword = first_keyword_match.group(1)

    if first_keyword not in ALLOWED_STARTING_KEYWORDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"SQL statements beginning with {first_keyword} are blocked. "
                "Only read-only SELECT, WITH, SHOW, DESCRIBE, DESC, "
                "and EXPLAIN statements are allowed."
            ),
        )

    if REPLACE_COMMAND_PATTERN.search(normalized):
        raise HTTPException(
            status_code=400,
            detail="The statement contains blocked SQL command: REPLACE.",
        )

    for forbidden_keyword in FORBIDDEN_KEYWORDS:
        keyword_pattern = (
            r"\b"
            + re.escape(forbidden_keyword).replace(
                r"\ ",
                r"\s+",
            )
            + r"\b"
        )

        if re.search(keyword_pattern, normalized):
            raise HTTPException(
                status_code=400,
                detail=(
                    "The statement contains blocked SQL command: "
                    f"{forbidden_keyword}."
                ),
            )

    if re.search(
        r"\bINTO\s+(OUTFILE|DUMPFILE)\b",
        normalized,
    ):
        raise HTTPException(
            status_code=400,
            detail="File-writing SQL commands are blocked.",
        )

    return sql


def apply_row_limit(
    sql: str,
    requested_limit: int,
) -> str:
    """
    Add LIMIT to SELECT and WITH queries when one is not already present.

    SHOW, DESCRIBE, DESC, and EXPLAIN statements are not modified.
    """

    if requested_limit < 1:
        raise HTTPException(
            status_code=400,
            detail="The row limit must be at least 1.",
        )

    sanitized = remove_comments_and_strings(sql)
    normalized = re.sub(
        r"\s+",
        " ",
        sanitized,
    ).strip().upper()

    if not normalized.startswith(("SELECT", "WITH")):
        return sql

    if re.search(r"\bLIMIT\s+\d+", normalized):
        return sql

    return f"{sql}\nLIMIT {requested_limit}"
