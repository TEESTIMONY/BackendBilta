# Bilta Backend

This is the standalone Django + DRF backend for Bilta.

## Included

- Django API project in `backend/`
- CRM/CMS app in `crm/`
- Deployment files:
  - `requirements.txt`
  - `Procfile`
  - `render.yaml`

## Run locally

1. Create a virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env`

3. Run migrations:

```bash
python manage.py migrate
```

4. Create an admin user:

```bash
python manage.py createsuperuser
```

5. Start the server:

```bash
python manage.py runserver
```

## Main API routes

- `/api/products/`
- `/api/customers/`
- `/api/jobs/`
- `/api/payments/`
- `/api/photocopy-sessions/`
- `/api/settings/`
- `/api/staff-accounts/`
- `/api/staff-invitations/`
- `/api/auth/login/`
- `/api/auth/logout/`
- `/api/auth/me/`
- `/api/public/order-requests/checkout/`
- `/api/public/order-requests/design/`
- `/api/health/`

## Production notes

- Use Postgres in production via `DATABASE_URL`
- Do not use local SQLite on ephemeral hosts
- If you deploy the backend separately from the frontend, set:
  - `CORS_ALLOW_ALL_ORIGINS=false`
  - `CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com`
  - `CSRF_TRUSTED_ORIGINS=https://your-frontend-domain.com`

## Supabase Postgres

This backend is ready to use Supabase Postgres through `DATABASE_URL`.

For a Render web service, the safest Supabase connection type is the `Session pooler`
connection string from the Supabase `Connect` dialog. Supabase recommends:

- direct connection for persistent servers when IPv6 is supported
- session pooler for persistent clients that need IPv4/IPv6 support
- transaction pooler for short-lived serverless traffic

In practice, that means:

1. Create your Supabase project
2. Open `Connect`
3. Copy the `Session pooler` Postgres connection string
4. Paste it into `DATABASE_URL` on Render
5. Keep the `sslmode=require` portion if Supabase includes it in the URL

## Render

This export includes `render.yaml` for a temporary Render deployment, but it no
longer provisions a Render Postgres database. You should add your Supabase
connection manually in the Render dashboard.

Recommended Render environment variables:

- `DATABASE_URL` = your Supabase `Session pooler` connection string
- `DJANGO_SECRET_KEY` = generated secret
- `DJANGO_DEBUG` = `false`
- `DJANGO_ALLOWED_HOSTS` = your Render hostname
- `CORS_ALLOW_ALL_ORIGINS` = `false` after initial testing
- `CORS_ALLOWED_ORIGINS` = your Vercel frontend URL
- `CSRF_TRUSTED_ORIGINS` = your Vercel frontend URL and your Render backend URL

After the first deploy:

```bash
python manage.py migrate
python manage.py createsuperuser
```
