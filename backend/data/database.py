import sqlite3
from pathlib import Path

from core.test_path_override import resolve_test_path_override


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DATABASE_PATH = Path(
    resolve_test_path_override(
        "ETOP_TEST_WORKBENCH_DB", DEFAULT_DATA_DIR / "workbench.db"
    )
)
DATA_DIR = DATABASE_PATH.parent


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        connection = sqlite3.connect(
            DATABASE_PATH,
            timeout=30,
            check_same_thread=False,
        )

        connection.row_factory = sqlite3.Row
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )
        connection.execute(
            "PRAGMA journal_mode = WAL;"
        )

        return connection

    except sqlite3.DatabaseError as exc:
        raise RuntimeError(
            f"The SQLite database file is invalid: "
            f"{DATABASE_PATH}. Stop the backend, delete "
            "workbench.db, workbench.db-wal, and "
            "workbench.db-shm, then restart the backend."
        ) from exc


def initialize_database() -> None:
    # Each module owns its versioned schema and idempotent seed. Calling the
    # module hooks here keeps migration in the established local SQLite startup
    # boundary without duplicating domain DDL in the shared database module.
    # Deferred imports avoid a circular import at module-load time (each
    # module's own repository/service imports from data.database).
    from modules.ar_collections.notes_repository import (
        initialize_ar_collections_database,
    )
    from modules.automations.repository import initialize_automations_database
    from modules.credit_risk.repository import initialize_credit_risk_database
    from modules.freight_logistics.notes_repository import (
        initialize_freight_logistics_database,
    )
    from modules.inventory_purchasing.notes_repository import (
        initialize_inventory_purchasing_database,
    )
    from modules.general_ledger.notes_repository import (
        initialize_general_ledger_database,
    )
    from modules.cash_flow_forecasting.notes_repository import (
        initialize_cash_flow_forecasting_database,
    )
    from modules.pricing_contracts.notes_repository import (
        initialize_pricing_contracts_database,
    )
    from modules.reports.service import initialize_reports_database
    from modules.sales_order_visibility.notes_repository import (
        initialize_sales_order_visibility_database,
    )
    from modules.tax_compliance.notes_repository import (
        initialize_tax_compliance_database,
    )
    from modules.vendor_intelligence.notes_repository import (
        initialize_vendor_intelligence_database,
    )

    initialize_reports_database()
    initialize_automations_database()
    initialize_credit_risk_database()
    initialize_vendor_intelligence_database()
    initialize_ar_collections_database()
    initialize_freight_logistics_database()
    initialize_inventory_purchasing_database()
    initialize_tax_compliance_database()
    initialize_sales_order_visibility_database()
    initialize_pricing_contracts_database()
    initialize_general_ledger_database()
    initialize_cash_flow_forecasting_database()
