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

## Supabase Storage

Uploaded media can also be stored in a Supabase bucket instead of Render's local
disk. This is the better long-term setup for job attachments and other uploaded
design assets.

This repo now supports that through Django's default media storage. When enabled,
uploaded files will be written to Supabase Storage over its S3-compatible
endpoint.

Set these environment variables:

- `USE_SUPABASE_STORAGE=true`
- `SUPABASE_STORAGE_BUCKET` = your Supabase bucket name
- `SUPABASE_STORAGE_ENDPOINT_URL` = your Supabase S3 endpoint
- `SUPABASE_STORAGE_REGION` = your Supabase storage region from project settings
- `SUPABASE_STORAGE_ACCESS_KEY_ID` = server-side S3 access key
- `SUPABASE_STORAGE_SECRET_ACCESS_KEY` = server-side S3 secret
- `SUPABASE_MEDIA_LOCATION=media`

Recommended setup:

1. Create a private bucket for uploads such as `bilta-media`
2. In Supabase Storage settings, enable S3 access
3. Generate server-side S3 credentials
4. Copy the endpoint and region from the same settings screen
5. Add the values above to Render

Notes:

- Keep the bucket private unless you intentionally want public files
- Staff downloads will still work through the Django API
- This mainly affects uploaded files like design assets and job attachments
- Product images in the current schema are still URL-based, so they are not yet
  being uploaded by Django into the bucket

## Render

This export includes `render.yaml` for a temporary Render deployment, but it no
longer provisions a Render Postgres database. You should add your Supabase
connection manually in the Render dashboard.

Recommended Render environment variables:

- `DATABASE_URL` = your Supabase `Session pooler` connection string
- `USE_SUPABASE_STORAGE` = `true` when ready to store uploads in Supabase
- `SUPABASE_STORAGE_BUCKET` = your private uploads bucket
- `SUPABASE_STORAGE_ENDPOINT_URL` = your Supabase S3 endpoint
- `SUPABASE_STORAGE_REGION` = your Supabase S3 region
- `SUPABASE_STORAGE_ACCESS_KEY_ID` = your Supabase S3 access key
- `SUPABASE_STORAGE_SECRET_ACCESS_KEY` = your Supabase S3 secret
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
