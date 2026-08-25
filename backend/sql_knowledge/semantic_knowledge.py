from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


KNOWLEDGE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = KNOWLEDGE_DIR / "generated"


def tokenize(value: str) -> set[str]:
    ignored = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "give", "i", "in", "is", "it", "me", "of", "on", "or", "report",
        "show", "sql", "that", "the", "this", "to", "using", "want", "with",
    }
    return {
        word
        for word in re.findall(r"[a-z0-9_$]+", value.lower())
        if len(word) >= 2 and word not in ignored
    }


def load_json(filename: str, default: dict[str, Any]) -> dict[str, Any]:
    path = GENERATED_DIR / filename
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_knowledge() -> dict[str, Any]:
    return {
        "dictionary": load_json(
            "data_dictionary.json",
            {"tables": [], "table_count": 0, "column_count": 0},
        ),
        "routes": load_json(
            "route_codes.json",
            {"routes": [], "by_route": {}, "route_count": 0},
        ),
        "examples": load_json(
            "sql_examples.json",
            {"examples": [], "example_count": 0},
        ),
        "rules": load_json(
            "business_rules.json",
            {"rules": [], "rule_count": 0},
        ),
    }


def clear_knowledge_cache() -> None:
    load_knowledge.cache_clear()


def score_text(terms: set[str], *values: str) -> int:
    haystack = " ".join(value or "" for value in values).lower()
    score = 0
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", haystack):
            score += 15
        elif term in haystack:
            score += 5
    return score


def find_dictionary_tables(prompt: str, limit: int = 8) -> list[dict[str, Any]]:
    knowledge = load_knowledge()
    terms = tokenize(prompt)
    scored: list[tuple[int, dict[str, Any]]] = []

    for table in knowledge["dictionary"]["tables"]:
        score = score_text(
            terms,
            table.get("qualified_name", ""),
            table.get("name", ""),
            table.get("description", ""),
        )

        matching_columns: list[dict[str, Any]] = []
        for column in table.get("columns", []):
            column_score = score_text(
                terms,
                column.get("name", ""),
                column.get("description", ""),
            )
            if column_score > 0:
                matching_columns.append({**column, "relevance_score": column_score})
                score += column_score

        if score > 0:
            matching_columns.sort(key=lambda item: -item["relevance_score"])
            scored.append(
                (
                    score,
                    {
                        **table,
                        "matching_columns": matching_columns[:30],
                    },
                )
            )

    scored.sort(key=lambda item: (-item[0], item[1]["qualified_name"]))
    return [item for _, item in scored[:limit]]


def find_business_rules(prompt: str, limit: int = 6) -> list[dict[str, Any]]:
    terms = tokenize(prompt)
    rules = load_knowledge()["rules"]["rules"]
    scored: list[tuple[int, dict[str, Any]]] = []

    for rule in rules:
        score = score_text(
            terms,
            rule.get("name", ""),
            rule.get("description", ""),
            " ".join(rule.get("keywords", [])),
            rule.get("formula", ""),
        )
        if score > 0:
            scored.append((score, rule))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [item for _, item in scored[:limit]]


def find_sql_examples(prompt: str, limit: int = 4) -> list[dict[str, Any]]:
    terms = tokenize(prompt)
    examples = load_knowledge()["examples"]["examples"]
    scored: list[tuple[int, dict[str, Any]]] = []

    for example in examples:
        score = score_text(
            terms,
            example.get("name", ""),
            example.get("description", ""),
            " ".join(example.get("keywords", [])),
            " ".join(example.get("schema_objects", [])),
            " ".join(example.get("column_candidates", [])),
        )

        if score > 0:
            scored.append((score, example))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [item for _, item in scored[:limit]]


def find_route_context(prompt: str) -> dict[str, Any] | None:
    lowered = prompt.lower()
    route_terms = ("route", "store", "location")

    if not any(term in lowered for term in route_terms):
        return None

    routes = load_knowledge()["routes"]
    return {
        "description": (
            "Route code to store is reference data supplied outside the live ERP schema. "
            "Use this mapping only when the prompt requests store/location from route code."
        ),
        "route_count": routes.get("route_count", 0),
        "sample_routes": routes.get("routes", [])[:40],
    }


def render_semantic_context(prompt: str) -> tuple[str, dict[str, Any]]:
    dictionary_tables = find_dictionary_tables(prompt)
    business_rules = find_business_rules(prompt)
    sql_examples = find_sql_examples(prompt)
    route_context = find_route_context(prompt)

    lines = ["ENTERPRISE SEMANTIC KNOWLEDGE:", ""]

    if dictionary_tables:
        lines.append("RELEVANT DATA DICTIONARY DEFINITIONS:")
        for table in dictionary_tables:
            lines.append(
                f"TABLE `{table['qualified_name']}` -- {table.get('description', '')}"
            )
            columns = table.get("matching_columns") or table.get("columns", [])[:25]
            for column in columns:
                description = column.get("description", "")
                data_type = column.get("data_type", "")
                lines.append(
                    f"  - `{column['name']}` ({data_type}): {description}"
                )
            lines.append("")

    if business_rules:
        lines.append("VERIFIED BUSINESS RULES:")
        for rule in business_rules:
            lines.append(f"- {rule['name']}: {rule['description']}")
            lines.append(f"  Formula: {rule['formula']}")
            lines.append(f"  Tables: {', '.join(rule.get('tables', []))}")
        lines.append("")

    if sql_examples:
        lines.append("PROVEN SQL REFERENCE EXAMPLES:")
        for example in sql_examples:
            lines.append(f"EXAMPLE: {example['name']}")
            lines.append("```sql")
            lines.append(example["sql"])
            lines.append("```")
            if not example.get("read_only_reference", True):
                lines.append(
                    "NOTE: This source contains DDL/write syntax. Use it only to learn business logic; "
                    "generate a single read-only SELECT/WITH statement."
                )
            lines.append("")

    if route_context:
        lines.append("ROUTE CODE REFERENCE:")
        lines.append(route_context["description"])
        lines.append(json.dumps(route_context["sample_routes"], indent=2))
        lines.append("")

    metadata = {
        "dictionary_tables": [
            table["qualified_name"] for table in dictionary_tables
        ],
        "business_rules": [rule["name"] for rule in business_rules],
        "sql_examples": [example["name"] for example in sql_examples],
        "route_context_included": route_context is not None,
    }

    return "\n".join(lines).strip(), metadata


def get_knowledge_status() -> dict[str, Any]:
    knowledge = load_knowledge()
    return {
        "loaded": True,
        "dictionary_tables": knowledge["dictionary"].get("table_count", 0),
        "dictionary_columns": knowledge["dictionary"].get("column_count", 0),
        "route_codes": knowledge["routes"].get("route_count", 0),
        "sql_examples": knowledge["examples"].get("example_count", 0),
        "business_rules": knowledge["rules"].get("rule_count", 0),
    }
