# WalletAPI

## What this project is

**WalletAPI** is a multi-tenant digital wallet and ledger backend built with **Django + Django REST Framework**.

It models a platform where:

- A **tenant** is a business / organization (merchant).
- A **tenant user** is a person under that business who owns **one wallet**.
- Money moves only through a **ledger** (deposit, withdraw, transfer) with idempotency and row locking — not by editing balances directly.
- A **platform super admin** (Django `createsuperuser`) can inspect tenants and users across the platform.

Typical use: create a tenant → register users under it → deposit / withdraw / transfer → check balance and history.

Amounts are always **integers in minor units** (BDT paisa). Example: `1000` = **10.00 BDT**. Never send floats.

---

## Who can call what

| Role | How they authenticate | What they do |
| --- | --- | --- |
| Anyone | — | Create a tenant |
| Tenant user | `Authorization: Bearer <tenant JWT>` **and** `X-Tenant-ID` | Register/login, wallet, ledger money ops |
| Platform super admin | `Authorization: Bearer <admin JWT>` from `/api/auth/admin/login/` | List tenants and all domain users |

---

## Environment files

| File | When to use |
| --- | --- |
| `.env.example` | Template for **local (non-Docker)** runs |
| `.env` | Your local secrets/config — copy from `.env.example` |
| `.env.docker.example` | Template for **Docker Compose** |
| `.env.docker` | Compose env — copy from `.env.docker.example` |

**Local (no Docker):** Django loads `.env` (via project bootstrap). Point `DB_*` at your local Postgres. Leave `DATABASE_URL` empty unless you intentionally use a hosted DB.

**Docker:** Compose uses `--env-file .env.docker`. It **overrides** `DB_HOST`, Redis URLs, and clears `DATABASE_URL` so containers talk to Compose Postgres/Redis — not your host DB.

Important variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret |
| `DEBUG` | Dev mode; enables Swagger auto-auth helpers |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | Postgres connection |
| `DATABASE_URL` | Optional hosted Postgres URL; leave empty for local/`DB_*` |
| `REDIS_URL` / `CELERY_*` | Wired for cache/Celery; **not required** for core wallet/ledger features |
| `SWAGGER_SUPERUSER_*` | DEBUG-only Swagger auto-login (local `.env`) |

### Local vs Docker databases (important)

**Local setup and Docker Compose use different Postgres databases by default.** That is intentional and standard.

| Setup | Database |
| --- | --- |
| Without Docker | Host Postgres from `.env` (`localhost:5432`) |
| With Docker | Compose `db` service (host port **5434**, volume `walletapi_pgdata`) |

A superuser (or tenants/users) created in one setup **will not appear** in the other. Create a superuser in whichever environment you are using:

- Local: `python manage.py createsuperuser`
- Docker: `docker compose --env-file .env.docker exec web python manage.py createsuperuser`

---

## Setup without Docker

**Requirements:** Python 3.10+, local Postgres.

```bash
cd Wallet

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env if your Postgres user/password/port differ

python3 manage.py migrate
python3 manage.py createsuperuser   # platform admin (for /api/auth/admin/login/)

python3 manage.py runserver
```

- API: http://localhost:8000  
- Health: http://localhost:8000/api/health/  
- Swagger: http://localhost:8000/api/docs/  

Prefer `http://localhost:8000` over `https://127.0.0.1` if the browser forces HTTPS.

```bash
pytest
```

Tests refuse a remote `DB_HOST` and clear `DATABASE_URL` so they only hit local Postgres.

---

## Setup with Docker

**Requirements:** Docker + Docker Compose.

Compose starts: **web**, **Celery worker**, **Celery beat**, **Postgres**, **Redis**.

```bash
cd Wallet

cp .env.docker.example .env.docker
# Optional: change host ports in .env.docker

docker compose --env-file .env.docker up --build
```

Background:

```bash
docker compose --env-file .env.docker up --build -d
```

Stop:

```bash
docker compose --env-file .env.docker down
```

Default host ports (so this stack can sit beside another project on 8000/5432):

| Service | Host port |
| --- | --- |
| Web (API) | **8001** → container 8000 |
| Postgres | **5434** → container 5432 |
| Redis | **6381** → container 6379 |

- Health: http://localhost:8001/api/health/  
- Swagger: http://localhost:8001/api/docs/  

**`RUN_MIGRATIONS` (Compose only — not in `.env`)**  
Set on the **web** service in `docker-compose.yml` as `RUN_MIGRATIONS=1`. On container start, `docker/entrypoint.sh` waits for Postgres, then runs `python manage.py migrate` so tables exist without a manual migrate step. Worker and beat use `RUN_MIGRATIONS=0` so only **one** service applies migrations (avoids race conditions). You do not need to put this in `.env.docker`.

Create a platform superuser **inside Docker** (this DB is separate from local Postgres — see [Local vs Docker databases](#local-vs-docker-databases-important)):

```bash
docker compose --env-file .env.docker exec web python manage.py createsuperuser
```

---

## Design rules (short)

- One wallet per tenant user, created on register (`currency=BDT`, `balance=0`).
- Tenant scope: `X-Tenant-ID` must match the JWT `tenant_id` on wallet/ledger calls.
- Ledger is the source of truth; balance updates happen in the same DB transaction as ledger rows.
- Idempotency keys are unique per tenant; retries with the **same** key, amount, and wallets replay the original tx.
- First successful money move → **201** + `"replayed": false`; exact retry → **200** + `"replayed": true`.
- Wallet balance cannot be edited via Django admin (inspection only).

---

## APIs — what each one does

Interactive docs: `/api/docs/` (Swagger).

### Tenants

| Method | Path | Who | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/tenants/` | Public | Create a tenant (business). Save returned `id` as `X-Tenant-ID`. |
| `GET` | `/api/tenants/` | Super admin | List all tenants. |
| `GET` | `/api/tenants/<uuid>/` | Super admin | Get one tenant. |
| `GET` | `/api/tenants/users/` | Super admin | List domain users; optional `X-Tenant-ID` filters to one tenant. |

### Auth — tenant user

Require header **`X-Tenant-ID`** (except where noted).

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/auth/register/` | Create user under tenant, open wallet, return `user` + `wallet` + tokens. |
| `POST` | `/api/auth/login/` | Email/password login for that tenant; returns tokens. |
| `POST` | `/api/auth/refresh/` | Rotate refresh → new access + refresh; **old refresh is blacklisted**. |
| `POST` | `/api/auth/logout/` | Blacklist refresh token (logout). |
| `GET` | `/api/auth/me/` | Current tenant-user profile (needs Bearer + `X-Tenant-ID`). |
| `PATCH` | `/api/auth/me/` | Update profile (`name` only). |

### Auth — platform super admin

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/auth/admin/login/` | Django superuser login → admin JWT (tenant list/users). |

### Wallets

Need tenant-user Bearer + matching `X-Tenant-ID`.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/wallets/me/` | My wallet balance. |
| `GET` | `/api/wallets/me/transactions/` | My ledger history (paginated: `?page=`). |
| `GET` | `/api/wallets/<wallet_id>/` | Same wallet by id (own wallet only; else 404). |
| `GET` | `/api/wallets/<wallet_id>/transactions/` | History for that wallet (own only). |

### Ledger (money)

Need tenant-user Bearer + matching `X-Tenant-ID`. Body always needs `idempotency_key`. Operates on **the caller’s** wallet.

| Method | Path | Body | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/ledger/deposit/` | `{amount, idempotency_key}` | Credit my wallet. |
| `POST` | `/api/ledger/withdraw/` | `{amount, idempotency_key}` | Debit my wallet (fails if insufficient funds). |
| `POST` | `/api/ledger/transfer/` | `{to_wallet_id, amount, idempotency_key}` | Send to another wallet in the **same tenant**. |

### Utility

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/health/` | Liveness check → `{"status":"ok"}`. |

---

## Suggested happy path

1. `POST /api/tenants/` → save tenant `id`.
2. `POST /api/auth/register/` with header `X-Tenant-ID: <tenant id>` → save `access` / `refresh` / wallet `id`.
3. `POST /api/ledger/deposit/` with Bearer + same `X-Tenant-ID`.
4. `GET /api/wallets/me/` and `GET /api/wallets/me/transactions/`.
5. (Optional) register a second user, then `POST /api/ledger/transfer/` with their `wallet` id as `to_wallet_id`.

---

## Project layout (apps)

| App | Responsibility |
| --- | --- |
| `apps.tenants` | Tenant, domain user, JWT auth, admin login |
| `apps.wallets` | Wallet balance model + read APIs |
| `apps.ledger` | Immutable ledger + deposit / withdraw / transfer |

---

## Notes

- Redis and Celery are included in Compose for completeness; **wallet/ledger logic does not depend on them**.
- In DEBUG, Swagger may auto-fill a **superadmin** token; tenant-user endpoints still need a tenant JWT and `X-Tenant-ID`.
