# Document Intelligence

## Initial use case

Convert a PNC Pittsburgh lockbox PDF into the approved Excel layout.

## Initial pipeline

1. Upload PDF
2. Classify document
3. Extract native text
4. Parse check-level transactions
5. Parse invoice allocations
6. Validate totals
7. Compare against approved Excel
8. Generate output
9. Route exceptions for review
