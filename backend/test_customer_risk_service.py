from customer_risk_service import rank_customer_risk


def test_customer_risk_is_ranked_by_priority_and_score() -> None:
    rows = [
        {
            "customer_number": 100,
            "customer_name": "Elevated Customer",
            "credit_limit": 100_000,
            "balance": 80_000,
            "exposure": 80_000,
            "past_due_amount": 0,
            "days_60_plus": 0,
            "days_90_plus": 0,
            "utilization_percent": 80,
        },
        {
            "customer_number": 200,
            "customer_name": "Critical Customer",
            "credit_limit": 50_000,
            "balance": 55_000,
            "exposure": 55_000,
            "past_due_amount": 15_000,
            "days_60_plus": 10_000,
            "days_90_plus": 5_000,
            "utilization_percent": 110,
        },
        {
            "customer_number": 300,
            "customer_name": "High Customer",
            "credit_limit": 100_000,
            "balance": 92_000,
            "exposure": 92_000,
            "past_due_amount": 5_000,
            "days_60_plus": 0,
            "days_90_plus": 0,
            "utilization_percent": 92,
        },
    ]

    customers = rank_customer_risk(rows, limit=100)

    assert [customer["customer_number"] for customer in customers] == [
        200,
        300,
        100,
    ]
    assert [customer["rank"] for customer in customers] == [1, 2, 3]
    assert customers[0]["risk_priority"] == "Critical"
    assert customers[1]["risk_priority"] == "High"
    assert customers[2]["risk_priority"] == "Elevated"
    assert customers[0]["risk_reasons"][0].startswith("Exposure is")


def test_customer_risk_honors_limit() -> None:
    rows = [
        {
            "customer_number": number,
            "customer_name": f"Customer {number}",
            "credit_limit": 1_000,
            "balance": 800 + number,
            "exposure": 800 + number,
            "past_due_amount": 0,
            "days_60_plus": 0,
            "days_90_plus": 0,
            "utilization_percent": 80 + number,
        }
        for number in range(1, 6)
    ]

    customers = rank_customer_risk(rows, limit=2)

    assert len(customers) == 2
    assert [customer["rank"] for customer in customers] == [1, 2]
