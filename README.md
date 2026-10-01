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
