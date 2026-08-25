from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.database import madden_database


router = APIRouter(
    prefix="/sql/schema",
    tags=["SQL Schema Explorer"],
)

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_$]+$")


def validate_identifier(value: str, label: str) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail=f"{label} cannot be blank.",
        )

    if not SAFE_IDENTIFIER.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}.",
        )

    return cleaned


@router.get("/summary")
def get_schema_summary() -> dict[str, Any]:
    summary = madden_database.fetch_one(
        """
        SELECT
            DATABASE() AS database_name,
            SUM(
                CASE
                    WHEN TABLE_TYPE = 'BASE TABLE' THEN 1
                    ELSE 0
                END
            ) AS table_count,
            SUM(
                CASE
                    WHEN TABLE_TYPE = 'VIEW' THEN 1
                    ELSE 0
                END
            ) AS view_count
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        """
    ) or {}

    column_count = madden_database.fetch_scalar(
        """
        SELECT COUNT(*) AS column_count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        """
    )

    return {
        "database": summary.get("database_name"),
        "tables": int(summary.get("table_count") or 0),
        "views": int(summary.get("view_count") or 0),
        "columns": int(column_count or 0),
    }


@router.get("/objects")
def get_schema_objects(
    search: str = Query(default="", max_length=200),
    object_type: str = Query(
        default="all",
        pattern="^(all|tables|views)$",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    conditions = ["T.TABLE_SCHEMA = DATABASE()"]
    parameters: list[Any] = []

    if object_type == "tables":
        conditions.append("T.TABLE_TYPE = 'BASE TABLE'")
    elif object_type == "views":
        conditions.append("T.TABLE_TYPE = 'VIEW'")

    if search.strip():
        conditions.append(
            """
            (
                T.TABLE_NAME LIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM INFORMATION_SCHEMA.COLUMNS C2
                    WHERE C2.TABLE_SCHEMA = T.TABLE_SCHEMA
                      AND C2.TABLE_NAME = T.TABLE_NAME
                      AND C2.COLUMN_NAME LIKE %s
                )
            )
            """
        )

        search_value = f"%{search.strip()}%"
        parameters.extend([search_value, search_value])

    where_clause = " AND ".join(conditions)

    rows = madden_database.fetch_all(
        f"""
        SELECT
            T.TABLE_NAME AS object_name,
            T.TABLE_TYPE AS object_type,
            T.ENGINE AS engine,
            T.TABLE_ROWS AS estimated_rows,
            T.TABLE_COMMENT AS table_comment,
            COUNT(C.COLUMN_NAME) AS column_count
        FROM INFORMATION_SCHEMA.TABLES T
        LEFT JOIN INFORMATION_SCHEMA.COLUMNS C
            ON C.TABLE_SCHEMA = T.TABLE_SCHEMA
           AND C.TABLE_NAME = T.TABLE_NAME
        WHERE {where_clause}
        GROUP BY
            T.TABLE_NAME,
            T.TABLE_TYPE,
            T.ENGINE,
            T.TABLE_ROWS,
            T.TABLE_COMMENT
        ORDER BY
            CASE
                WHEN T.TABLE_TYPE = 'BASE TABLE' THEN 0
                ELSE 1
            END,
            T.TABLE_NAME
        LIMIT %s
        """,
        [*parameters, limit],
    )

    objects = [
        {
            "name": row["object_name"],
            "type": (
                "table"
                if row["object_type"] == "BASE TABLE"
                else "view"
            ),
            "engine": row["engine"],
            "estimated_rows": (
                int(row["estimated_rows"])
                if row["estimated_rows"] is not None
                else None
            ),
            "comment": row["table_comment"] or "",
            "column_count": int(row["column_count"] or 0),
        }
        for row in rows
    ]

    return {
        "objects": objects,
        "count": len(objects),
        "limit": limit,
    }


@router.get("/objects/{object_name}/columns")
def get_object_columns(
    object_name: str,
) -> dict[str, Any]:
    safe_object_name = validate_identifier(
        object_name,
        "table or view name",
    )

    rows = madden_database.fetch_all(
        """
        SELECT
            COLUMN_NAME AS column_name,
            ORDINAL_POSITION AS ordinal_position,
            COLUMN_DEFAULT AS column_default,
            IS_NULLABLE AS is_nullable,
            DATA_TYPE AS data_type,
            COLUMN_TYPE AS column_type,
            CHARACTER_MAXIMUM_LENGTH AS character_length,
            NUMERIC_PRECISION AS numeric_precision,
            NUMERIC_SCALE AS numeric_scale,
            COLUMN_KEY AS column_key,
            EXTRA AS extra,
            COLUMN_COMMENT AS column_comment
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (safe_object_name,),
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Table or view '{safe_object_name}' "
                "was not found."
            ),
        )

    columns = [
        {
            "name": row["column_name"],
            "ordinal_position": int(
                row["ordinal_position"]
            ),
            "default": row["column_default"],
            "nullable": row["is_nullable"] == "YES",
            "data_type": row["data_type"],
            "column_type": row["column_type"],
            "character_length": (
                int(row["character_length"])
                if row["character_length"] is not None
                else None
            ),
            "numeric_precision": (
                int(row["numeric_precision"])
                if row["numeric_precision"] is not None
                else None
            ),
            "numeric_scale": (
                int(row["numeric_scale"])
                if row["numeric_scale"] is not None
                else None
            ),
            "key": row["column_key"] or "",
            "extra": row["extra"] or "",
            "comment": row["column_comment"] or "",
        }
        for row in rows
    ]

    return {
        "object_name": safe_object_name,
        "columns": columns,
        "count": len(columns),
    }


@router.get("/objects/{object_name}/indexes")
def get_object_indexes(
    object_name: str,
) -> dict[str, Any]:
    safe_object_name = validate_identifier(
        object_name,
        "table or view name",
    )

    rows = madden_database.fetch_all(
        """
        SELECT
            INDEX_NAME AS index_name,
            NON_UNIQUE AS non_unique,
            SEQ_IN_INDEX AS sequence_number,
            COLUMN_NAME AS column_name,
            COLLATION AS collation,
            CARDINALITY AS cardinality,
            INDEX_TYPE AS index_type,
            NULLABLE AS nullable,
            INDEX_COMMENT AS index_comment
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (safe_object_name,),
    )

    grouped_indexes: dict[str, dict[str, Any]] = {}

    for row in rows:
        index_name = row["index_name"]

        if index_name not in grouped_indexes:
            grouped_indexes[index_name] = {
                "name": index_name,
                "unique": not bool(row["non_unique"]),
                "primary": index_name == "PRIMARY",
                "type": row["index_type"],
                "cardinality": (
                    int(row["cardinality"])
                    if row["cardinality"] is not None
                    else None
                ),
                "comment": row["index_comment"] or "",
                "columns": [],
            }

        grouped_indexes[index_name]["columns"].append(
            {
                "name": row["column_name"],
                "sequence": int(row["sequence_number"]),
                "descending": row["collation"] == "D",
                "nullable": row["nullable"] == "YES",
            }
        )

    return {
        "object_name": safe_object_name,
        "indexes": list(grouped_indexes.values()),
        "count": len(grouped_indexes),
    }