# Complete Matching and Recommendation Engine

Extract this ZIP directly over:

```text
C:\Users\Josh.Corbit\vite-project
```

It adds:

- `combination_matcher.py`
- `recommendation_engine.py`
- `history_repository.py`
- `historical_behavior_engine.py`
- `ai_explainer.py`
- service exports and a basic test

The package does not overwrite `invoice_matcher.py`, your working repository, aging logic, or `main.py`.

## Add the test endpoint to main.py

Copy the imports and endpoint from `MAIN_INTEGRATION_SNIPPET.py` into `backend/main.py`.

## Safety behavior

- Exact math is deterministic and cent-based.
- Multiple exact combinations always require review.
- Historical data only adjusts confidence slightly.
- The engine never posts to Madden.
- TMIHSH is treated as invoice-history evidence, not proof of the exact payment-application sequence.
