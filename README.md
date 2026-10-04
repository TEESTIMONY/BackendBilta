# Bilta Backend

Django + Django REST Framework API for the Bilta print shop: product catalogue, customers, jobs, payments, photocopy sessions, staff accounts and website order/design requests.

The frontend lives in a separate repository (`bilta_frontend`).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Settings are read from environment variables (see `.env.example`); the `.env` file is **not** loaded automatically, so export the values in your shell or hosting provider. With no variables set, the app runs in debug mode against SQLite.

Admin: `http://127.0.0.1:8000/admin/`

## Tests

```bash
python manage.py test crm
```

## Access rules

Every endpoint is staff-only unless listed below. "Owner" means a superuser.

| Endpoint | Anonymous | Staff | Owner |
| --- | --- | --- | --- |
| `GET /api/health/` | yes | yes | yes |
| `/api/products/` | read | read | read + write |
| `POST /api/public/order-requests/checkout/`, `.../design/` | yes | yes | yes |
| `GET /api/announcements/active/` | yes | yes | yes |
| `POST /api/auth/login/`, `/api/auth/invitations/...` | yes (rate limited) | yes | yes |
| `GET /api/job-attachments/<id>/download/` | with signed link only | yes | yes |
| customers, jobs, orders, payments, photocopy sessions, order message logs | no | read + write | + delete |
| settings, message templates, announcements (list/edit) | no | read | read + write |
| staff accounts, staff invitations, audit logs | no | no | yes |

Attachment `download_url` values returned by the jobs API are signed and expire after 12 hours.

## Production environment

```env
DJANGO_SECRET_KEY=<long random value>        # required when DJANGO_DEBUG=false
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=api.example.com         # the *.onrender.com host is added automatically on Render
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME

DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
CSRF_TRUSTED_ORIGINS=https://api.example.com

CORS_ALLOW_ALL_ORIGINS=false
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com
```

Optional: `USE_SUPABASE_STORAGE=true` plus the `SUPABASE_STORAGE_*` values stores uploaded files in a Supabase Storage bucket instead of local disk.

Deploy sequence:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn backend.wsgi:application
```

## Render

`render.yaml` defines a free Python web service that builds, collects static files, runs migrations on start and health-checks `/api/health/`. In the Render dashboard, set:

- `DATABASE_URL` (external Postgres, e.g. Supabase)
- `CORS_ALLOWED_ORIGINS` is preset in `render.yaml` to `https://bilta.com.ng` and `https://www.bilta.com.ng`. Add any other frontend URL (e.g. a Vercel preview) there, or the browser will block its API calls.
- `DJANGO_ALLOWED_HOSTS`: only if you use a custom API domain
- `SUPABASE_STORAGE_*` credentials
- Optionally `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` to create the first owner account on start

The free service sleeps when idle, and its local disk is wiped on each deploy, so use Postgres and Supabase Storage rather than SQLite and local media.

Point the frontend at the API with:

```env
VITE_DJANGO_API_BASE=https://your-render-service.onrender.com/api
VITE_USE_DJANGO_API=true
```


## Staff profiles and monitoring

The frontend's `/team/staff` page lets owners set staff names, job roles, fixed monthly salaries (NGN), and expected resumption times (Africa/Lagos).

Owners record each day's actual arrival and leaving times, a rating from 1 to 10, notes, and an optional bonus recommendation. Staff can read only their own profile and attendance; salaries and attendance are editable only by owners, and ratings, notes, and bonus recommendations are owner-only. Bonus markers support review; they do not change salaries or issue payments.

`GET/PATCH /api/staff-profiles/` and `GET/POST/PATCH /api/staff-daily-records/` provide the data. Use `?start=YYYY-MM-DD&end=YYYY-MM-DD&staff=<user_id>` for daily history. Daily records are unique per staff member and day. The expected start time is saved with each daily record so later schedule changes do not rewrite historical lateness. Corrections to profiles and daily records are recorded in the owner's audit log.

Run `python manage.py migrate` before starting the updated API. Migration 0013 creates profiles for existing staff; new staff profiles are created automatically.


Cash counts are owner/admin-only (`/api/cash-counts/`). Admin enters one combined cash and transfer total for the whole shop each day. No staff selection is required. The total is compared with all shop payments and photocopy collections before expenses. Staff cannot view or enter counts. Migration 0014 combines historical staff counts per day, preserving the original rows in an owner-only audit entry.

The money statement's `received` value automatically sums payment records and photocopy collections recorded by all staff and admins for each day (Africa/Lagos). It works without a cash count. Manual shop counts are used for reconciliation; `remaining` is recorded collections minus expenses.
