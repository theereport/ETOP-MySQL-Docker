# Customer 360 Backend Module

## Endpoints

- `GET /api/v1/customers`
- `GET /api/v1/customers/search`
- `GET /api/v1/customers/{customer_number}`

## Search parameters

- `search`
- `route_code`
- `store_number`
- `active_only`
- `limit`
- `offset`

## Add to main.py

```python
from modules.customer_360.manifest import manifest as customer_360_manifest
```

Register it after the existing router registrations:

```python
app.include_router(customer_360_router)
```
