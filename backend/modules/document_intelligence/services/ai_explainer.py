from __future__ import annotations

from .recommendation_engine import CashApplicationRecommendation


class AIExplainer:
    """
    Produces a grounded explanation from deterministic output.

    It intentionally does not invent facts or select a different match. An LLM
    can later rephrase this text, but the recommendation remains authoritative.
    """

    def explain(self, recommendation: CashApplicationRecommendation) -> str:
        invoices = ", ".join(recommendation.recommended_invoice_numbers) or "none"
        lines = [
            f"Recommendation status: {recommendation.status}",
            f"Confidence: {recommendation.confidence_score}%",
            f"Strategy: {recommendation.strategy or 'none'}",
            f"Recommended invoices: {invoices}",
            f"Manual review required: {'Yes' if recommendation.review_required else 'No'}",
        ]

        if recommendation.reasons:
            lines.append("Reasons:")
            lines.extend(f"- {reason}" for reason in recommendation.reasons)

        if recommendation.historical_behavior:
            profile = recommendation.historical_behavior
            lines.append(
                f"Historical signal sample: {profile.sample_size} records "
                f"({profile.confidence_level} confidence)."
            )

        lines.append("No ERP posting was performed by this recommendation.")
        return "\n".join(lines)
