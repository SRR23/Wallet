# WalletAPI

Multi-tenant wallet / ledger API (Django + DRF). Money is integer minor units (BDT paisa).

## Assumptions

- One wallet per tenant user, auto-created on register (`currency=BDT`, `balance=0`).
- Tenant scoping via `X-Tenant-ID` (+ JWT for tenant users).
- Ledger is source of truth; wallet `balance` is updated in the same DB transaction.
- Idempotency keys are unique per tenant.
- Deposit / withdraw / transfer act on the authenticated user's wallet (transfer `to_wallet_id` must be same tenant).

## Endpoints

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `/api/tenants/` | Public (create tenant) |
| `GET` | `/api/tenants/` | Super admin |
| `GET` | `/api/tenants/<uuid>/` | Super admin |
| `GET` | `/api/tenants/users/` | Super admin |
| `POST` | `/api/auth/register/` | `X-Tenant-ID` → user + wallet + tokens |
| `POST` | `/api/auth/login/` | `X-Tenant-ID` |
| `POST` | `/api/auth/refresh/` | `X-Tenant-ID` |
| `GET/PATCH` | `/api/auth/me/` | Tenant JWT + `X-Tenant-ID` |
| `POST` | `/api/auth/admin/login/` | Django superuser |
| `GET` | `/api/wallets/me/` | Tenant JWT — balance |
| `GET` | `/api/wallets/me/transactions/` | Tenant JWT — paginated history |
| `POST` | `/api/ledger/deposit/` | `{amount, idempotency_key}` |
| `POST` | `/api/ledger/withdraw/` | `{amount, idempotency_key}` |
| `POST` | `/api/ledger/transfer/` | `{to_wallet_id, amount, idempotency_key}` |

Amounts are integers (e.g. `1000` = 10.00 BDT). Replayed idempotent calls return **200** with `"replayed": true`; first success returns **201**.

## Setup

```bash
cd WalletAPI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Use `http://localhost:8000` (not `https://127.0.0.1` if your browser forces HTTPS).

Docs: `http://localhost:8000/api/docs/` (DEBUG auto-auth for superadmin JWT only; tenant APIs still need `X-Tenant-ID` + tenant JWT).

```bash
pytest
```
