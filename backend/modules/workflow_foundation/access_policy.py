from __future__ import annotations


PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/v1/workflow-foundation/bootstrap-status",
        "/api/v1/workflow-foundation/bootstrap",
        "/api/v1/workflow-foundation/sessions",
        "/api/v1/workflow-foundation/invitations/preview",
        "/api/v1/workflow-foundation/invitations/activate",
    }
)


def required_modules_for_path(path: str) -> tuple[str, ...] | None:
    """Return acceptable module grants, None for public, or () for fail-closed."""

    normalized = path.rstrip("/") or "/"
    if normalized in PUBLIC_PATHS:
        return None

    if normalized.startswith("/api/v1/workflow-foundation/security"):
        return ("security_administration",)
    if normalized.startswith("/api/v1/workflow-foundation"):
        return ("work_management",)

    if normalized.startswith("/api/v1/financial-close"):
        return ("financial_close",)
    if normalized.startswith("/api/v1/accounts-payable"):
        return ("accounts_payable",)
    if normalized.startswith("/api/v1/credit-risk"):
        return ("credit_risk",)
    if normalized.startswith("/api/v1/erp-evidence/accounts-payable"):
        return ("accounts_payable",)
    if normalized.startswith("/api/v1/erp-evidence/credit"):
        return ("credit_risk",)
    if normalized == "/api/v1/erp-evidence/status":
        return ("accounts_payable", "credit_risk")

    if normalized == "/api/v1/payment-notes" or normalized.startswith(
        "/api/v1/payment-notes/"
    ):
        return ("payment_notes",)

    if (
        normalized == "/api/v1/modules"
        or normalized.startswith("/api/v1/modules/")
        or normalized.startswith("/api/v1/platform")
    ):
        return ("dashboard",)

    if normalized.startswith("/api/v1/documents/cash-application"):
        return ("cash_application",)
    if normalized.startswith("/api/v1/documents"):
        if "/lockbox/" in normalized or normalized.startswith(
            "/api/v1/documents/lockbox/"
        ):
            return ("lockbox",)
        # PSS-007 owns the shared job/upload routes used by Lockbox, AP capture,
        # daily document operations, and Document AI Studio. Any one consuming
        # module grant admits this shared service surface; job-level document
        # authorization remains an explicit enterprise-deployment gap.
        return (
            "document_intelligence",
            "document_ai_studio",
            "accounts_payable",
            "lockbox",
        )
    if normalized.startswith("/training"):
        return ("document_ai_studio",)

    if normalized.startswith("/api/v1/customers"):
        return ("customer_360",)
    if normalized.startswith("/api/v1/customer-risk"):
        return ("customer_360", "credit_risk")
    if normalized.startswith("/api/v1/customer-match"):
        return ("customer_360", "credit_risk", "cash_application", "lockbox")
    if normalized.startswith("/api/v1/customer-intelligence"):
        return ("customer_360",)
    if normalized.startswith("/api/test/"):
        return ("cash_application", "lockbox")

    if normalized.startswith("/api/v1/automations"):
        return ("automation_center",)
    if normalized.startswith("/api/v1/reports"):
        return ("report_builder",)
    if normalized.startswith("/sql"):
        return ("sql_workspace",)

    if normalized.startswith("/knowledge/reindex"):
        return ("knowledge_base",)
    if normalized in {"/knowledge/status", "/knowledge/search"}:
        return ("knowledge_base", "ai_assistant", "dashboard")
    if normalized == "/knowledge/chat":
        return ("ai_assistant",)
    if normalized == "/chat":
        return ("ai_assistant",)

    if normalized == "/modules" or normalized.startswith("/platform"):
        return ("dashboard",)

    # Unknown application/API routes are intentionally not inherited by any
    # account. A new module must be registered and mapped before it can run.
    return ()


__all__ = ["required_modules_for_path"]
