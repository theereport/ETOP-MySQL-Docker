from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.database import madden_database
from core.sql_validator import normalize_and_validate_sql

from sql_knowledge.semantic_knowledge import (
    get_knowledge_status,
    render_semantic_context,
)


router = APIRouter(
    prefix="/sql/ai",
    tags=["SQL AI"],
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "SQL_AI_MODEL",
    "qwen2.5-coder:7b",
)

MAX_SCHEMA_OBJECTS = int(
    os.getenv("SQL_AI_MAX_SCHEMA_OBJECTS", "15")
)

MAX_COLUMNS_PER_OBJECT = int(
    os.getenv("SQL_AI_MAX_COLUMNS_PER_OBJECT", "80")
)


class GenerateSqlRequest(BaseModel):
    prompt: str = Field(
        min_length=3,
        max_length=20_000,
    )

    current_sql: str = Field(
        default="",
        max_length=250_000,
    )

    selected_tables: list[str] = Field(
        default_factory=list,
        max_length=100,
    )


def tokenize_prompt(value: str) -> set[str]:
    ignored_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "build",
        "by",
        "create",
        "do",
        "for",
        "from",
        "generate",
        "get",
        "give",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "or",
        "report",
        "select",
        "show",
        "sql",
        "that",
        "the",
        "this",
        "to",
        "using",
        "want",
        "where",
        "with",
    }

    words = re.findall(
        r"[A-Za-z0-9_$]+",
        value.lower(),
    )

    return {
        word
        for word in words
        if len(word) >= 2
        and word not in ignored_words
    }


def score_schema_object(
    schema_object: dict[str, Any],
    terms: set[str],
    selected_tables: set[str],
) -> int:
    object_name = schema_object["name"].lower()
    object_comment = (
        schema_object.get("comment") or ""
    ).lower()

    score = 0

    if object_name in selected_tables:
        score += 10_000

    for term in terms:
        if term == object_name:
            score += 500
        elif term in object_name:
            score += 150

        if term in object_comment:
            score += 30

        for column in schema_object["columns"]:
            column_name = column["name"].lower()
            column_comment = (
                column.get("comment") or ""
            ).lower()

            if term == column_name:
                score += 100
            elif term in column_name:
                score += 35

            if term in column_comment:
                score += 12

    return score


def select_relevant_schema(
    catalog: dict[str, Any],
    prompt: str,
    current_sql: str,
    selected_tables: list[str],
) -> list[dict[str, Any]]:
    combined_text = f"{prompt}\n{current_sql}"
    terms = tokenize_prompt(combined_text)

    selected_table_names = {
        table.lower()
        for table in selected_tables
    }

    scored_objects = [
        (
            score_schema_object(
                schema_object,
                terms,
                selected_table_names,
            ),
            schema_object,
        )
        for schema_object in catalog["objects"]
    ]

    scored_objects.sort(
        key=lambda item: (
            -item[0],
            item[1]["name"],
        )
    )

    relevant_objects = [
        schema_object
        for score, schema_object in scored_objects
        if score > 0
    ][:MAX_SCHEMA_OBJECTS]

    if not relevant_objects:
        relevant_objects = [
            schema_object
            for _, schema_object in scored_objects[
                : min(15, MAX_SCHEMA_OBJECTS)
            ]
        ]

    return relevant_objects


def render_schema_context(
    database_name: str,
    schema_objects: list[dict[str, Any]],
) -> str:
    lines = [
        f"DATABASE: {database_name}",
        "",
        "AVAILABLE OBJECTS:",
    ]

    for schema_object in schema_objects:
        object_type = schema_object["type"].upper()
        object_name = schema_object["name"]

        comment = schema_object.get("comment") or ""

        heading = f"{object_type} `{object_name}`"

        if comment:
            heading += f" -- {comment}"

        lines.append(heading)

        columns = schema_object["columns"][
            :MAX_COLUMNS_PER_OBJECT
        ]

        for column in columns:
            details = [column["column_type"]]

            if not column["nullable"]:
                details.append("NOT NULL")

            if column["key"]:
                details.append(
                    f"KEY={column['key']}"
                )

            description = ", ".join(details)

            column_line = (
                f"  - `{column['name']}`: "
                f"{description}"
            )

            if column.get("comment"):
                column_line += (
                    f" -- {column['comment']}"
                )

            lines.append(column_line)

        if (
            len(schema_object["columns"])
            > MAX_COLUMNS_PER_OBJECT
        ):
            remaining = (
                len(schema_object["columns"])
                - MAX_COLUMNS_PER_OBJECT
            )

            lines.append(
                f"  - ... {remaining} more columns"
            )

        lines.append("")

    return "\n".join(lines)


def call_ollama(
    messages: list[dict[str, str]],
) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 16384,
            "num_predict": 2048,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
        },
        "keep_alive": "30m",
    }

    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=300,
        ) as response:
            response_body = json.loads(
                response.read().decode("utf-8")
            )

    except (TimeoutError, socket.timeout) as timeout_error:
        raise HTTPException(
            status_code=504,
            detail=(
                "The local SQL AI model exceeded the "
                "5-minute generation timeout."
            ),
        ) from timeout_error

    except urllib.error.URLError as request_error:
        if isinstance(request_error.reason, socket.timeout):
            raise HTTPException(
                status_code=504,
                detail=(
                    "The local SQL AI model exceeded the "
                    "5-minute generation timeout."
                ),
            ) from request_error

        raise HTTPException(
            status_code=503,
            detail=(
                "Unable to reach Ollama at "
                f"{OLLAMA_BASE_URL}. "
                f"{request_error}"
            ),
        ) from request_error

    message = response_body.get("message") or {}
    content = message.get("content")

    if not content:
        raise HTTPException(
            status_code=502,
            detail=(
                "Ollama returned an empty SQL response."
            ),
        )

    return str(content).strip()


def extract_sql_from_response(
    response_text: str,
) -> tuple[str, str]:
    allowed_pattern = (
        r"\b(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN)\b"
    )

    fenced_match = re.search(
        r"```(?:sql|mysql)?\s*(.*?)```",
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if fenced_match:
        fenced_content = fenced_match.group(1).strip()

        statement_match = re.search(
            allowed_pattern,
            fenced_content,
            flags=re.IGNORECASE,
        )

        if not statement_match:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The local model returned a code block, "
                    "but no supported read-only SQL statement "
                    "was found inside it."
                ),
            )

        sql_text = fenced_content[
            statement_match.start():
        ].strip()

        explanation = (
            response_text[:fenced_match.start()]
            + response_text[fenced_match.end():]
        ).strip()

        return sql_text, explanation

    statement_match = re.search(
        allowed_pattern,
        response_text,
        flags=re.IGNORECASE,
    )

    if not statement_match:
        raise HTTPException(
            status_code=422,
            detail=(
                "The local model did not return a supported "
                "read-only SQL statement."
            ),
        )

    sql_text = response_text[
        statement_match.start():
    ].strip()

    explanation = response_text[
        :statement_match.start()
    ].strip()

    return sql_text, explanation

@router.get("/catalog")
def get_ai_schema_catalog() -> dict[str, Any]:
    return madden_database.load_schema_catalog()


@router.get("/knowledge/status")
def get_sql_ai_knowledge_status() -> dict[str, Any]:
    return get_knowledge_status()


@router.post("/generate")
def generate_schema_aware_sql(
    request: GenerateSqlRequest,
) -> dict[str, Any]:
    catalog = madden_database.load_schema_catalog()

    semantic_context, semantic_metadata = render_semantic_context(
        prompt="\n".join(
            part
            for part in [
                request.prompt,
                request.current_sql,
                " ".join(request.selected_tables),
            ]
            if part
        )
    )

    relevant_schema = select_relevant_schema(
        catalog=catalog,
        prompt=request.prompt,
        current_sql=request.current_sql,
        selected_tables=request.selected_tables,
    )

    schema_context = render_schema_context(
        database_name=catalog["database"],
        schema_objects=relevant_schema,
    )

    system_prompt = """
You are a senior MySQL report developer working inside a
strictly read-only enterprise SQL environment.

You are given two forms of trusted context:

1. LIVE SCHEMA METADATA
   This establishes which tables, views, and columns currently exist.

2. ENTERPRISE SEMANTIC KNOWLEDGE
   This contains business descriptions, proven SQL examples,
   verified formulas, route-code mappings, and established
   reporting patterns.

Rules:
1. Use only tables, views, and columns present in the supplied
   live schema or explicitly documented in the supplied enterprise
   semantic knowledge.
2. Never invent a table or column.
3. Generate exactly one read-only SQL statement.
4. Allowed statement types are SELECT, WITH, SHOW, DESCRIBE,
   DESC, and EXPLAIN.
5. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
   TRUNCATE, REPLACE, CALL, stored procedure execution,
   temporary tables, OUTFILE, or DUMPFILE.
6. Use MySQL-compatible syntax.
7. Qualify ambiguous columns using table aliases.
8. Use understandable output aliases.
9. Preserve codes, values, formulas, exclusions, and date rules
   exactly when they are supported by proven examples.
10. Prefer proven joins and calculations from the enterprise
    semantic knowledge over guesses.
11. A proven SQL example is reference material. Adapt it to the
    user's request rather than copying unrelated output columns.
12. If an example contains procedure or write syntax, learn only
    from its reporting logic and generate a read-only query.
13. Legacy fields often use abbreviations. Use their documented
    business descriptions to interpret them.
14. Do not conclude that information is unavailable until you have
    inspected the data dictionary definitions and relevant examples.
15. Never return hypothetical, placeholder, generic, or
    commented-out SQL.
16. Never use generic names such as Customers, CustomerNumber,
    CustomerName, CreditLimit, or CurrentBalance unless those exact
    objects exist in the supplied context.
17. Do not wrap the generated statement in block comments.
18. Return SQL inside exactly one ```sql fenced block.
19. The first content inside the SQL block must be SELECT, WITH,
    SHOW, DESCRIBE, DESC, or EXPLAIN.
20. After the SQL block, briefly explain the tables, joins,
    calculations, filters, and assumptions used.
""".strip()

    user_prompt_parts = [
        "LIVE SCHEMA METADATA",
        "====================",
        schema_context,
        "",
        "ENTERPRISE SEMANTIC KNOWLEDGE",
        "=============================",
        semantic_context
        or "No matching enterprise semantic knowledge was found.",
        "",
        "USER REQUEST",
        "============",
        request.prompt.strip(),
    ]

    if request.current_sql.strip():
        user_prompt_parts.extend(
            [
                "",
                "CURRENT SQL",
                "===========",
                request.current_sql.strip(),
            ]
        )

    response_text = call_ollama(
        [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": "\n".join(
                    user_prompt_parts
                ),
            },
        ]
    )

    generated_sql, explanation = (
        extract_sql_from_response(response_text)
    )

    try:
        validated_sql = normalize_and_validate_sql(
            generated_sql
        )

    except HTTPException as validation_error:
        raise HTTPException(
            status_code=422,
            detail=(
                "The AI response was blocked by the "
                "read-only SQL validator: "
                f"{validation_error.detail}"
            ),
        ) from validation_error

    return {
        "success": True,
        "sql": validated_sql,
        "explanation": explanation,
        "database": catalog["database"],
        "model": OLLAMA_MODEL,
        "knowledge_used": semantic_metadata,
        "schema_objects_used": [
            {
                "name": schema_object["name"],
                "type": schema_object["type"],
                "column_count": len(
                    schema_object["columns"]
                ),
            }
            for schema_object in relevant_schema
        ],
    }