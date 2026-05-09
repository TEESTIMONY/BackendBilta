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

## Render

This export includes `render.yaml` for temporary Render deployment.
