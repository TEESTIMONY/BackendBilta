# Bilta Frontend

Bilta is a React + Vite frontend for showcasing print products and related service pages.

## Run locally

```bash
npm install
npm run dev
```

## CMS-ready products setup (no custom backend required)

The Shop and Product Details pages are wired to use a headless-CMS style endpoint.

- If `VITE_CMS_PRODUCTS_URL` is provided, products are fetched from that URL.
- If it is not provided (or fails), the app falls back to local products data.

Priority order used by the app:
1. Team editor local override (browser localStorage)
2. Sanity dataset (if configured)
3. Generic CMS URL (if configured)
4. Local bundled products data (fallback)

### 1) Configure environment

Copy `.env.example` to `.env` and set:

```env
VITE_CMS_PRODUCTS_URL=https://your-cms-endpoint/products.json

# Optional Sanity config
VITE_SANITY_PROJECT_ID=your_project_id
VITE_SANITY_DATASET=production
VITE_SANITY_API_VERSION=2024-01-01
```

### 2) Expected CMS payload shape

You can return either an array or `{ products, filters }` object.

```json
{
  "filters": ["All Products", "BUSINESS CARDS", "POSTERS"],
  "products": [
    {
      "slug": "one-sided-business-cards",
      "category": "BUSINESS CARDS",
      "title": "One-sided Business Cards",
      "description": "Premium business cards for professional brand presentation.",
      "image": "https://example.com/image.jpg",
      "price": "₦12,000"
    }
  ]
}
```

Required fields per product: `slug`, `category`, `title`, `image`.

## Team products editor page

A built-in team editing page is available at:

`/team/products-editor`

> Security note: this route is **disabled by default**.
> Set `VITE_ENABLE_TEAM_EDITOR=true` only in private/internal environments.

What it does:
- Lets your team edit products quickly (title, slug, category, description, image, price)
- Saves changes into browser localStorage
- Overrides CMS/local data for that browser session/device
- Supports image URL paste or local image upload (stored as Base64 in localStorage)

Buttons:
- **Save Team Data**: stores editable products for immediate use on Shop/Product pages
- **Reset Team Data**: clears local override and returns to CMS/local source

## Build

```bash
npm run build
```

## Django REST API backend (CRM/CMS MVP)

A Django + DRF backend is now scaffolded in this repo for Bilta CRM/CMS operations.

### Included MVP modules

- Products
- Customers
- Orders (online + manual/job orders)
- Order items
- Message templates
- Order message logs
- Announcements
- Monthly order report endpoint

### API base

- `/api/products/`
- `/api/customers/`
- `/api/orders/`
- `/api/orders/monthly_report/?month=YYYY-MM`
- `/api/message-templates/`
- `/api/order-message-logs/`
- `/api/announcements/`
- `/api/announcements/active/`

### Backend run steps

1. Ensure env values in `.env` (see `.env.example` for backend keys).
2. Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

3. Create admin user:

```bash
python manage.py createsuperuser
```

4. Run server:

```bash
python manage.py runserver
```

5. Open admin:

- `http://127.0.0.1:8000/admin/`

### Notes

- Current default DB is SQLite; settings are environment-driven for easy Postgres switch.
- CORS is enabled for local frontend development.
- Next integration step is to point frontend services to these `/api/*` endpoints instead of localStorage/CMS fallback.

## Backend hosting readiness (Django API)

Backend is now prepared for production hosting with:

- `gunicorn` process entry (`Procfile`)
- `whitenoise` static file serving
- `dj-database-url` support via `DATABASE_URL`
- env-based production security toggles
- `requirements.txt` for backend deployment installs

### Production env checklist

Set these values in your hosting provider:

```env
DJANGO_SECRET_KEY=your-strong-secret
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-api-domain.com

DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME

DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
CSRF_TRUSTED_ORIGINS=https://your-api-domain.com

CORS_ALLOW_ALL_ORIGINS=false
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com
```

### Deploy command sequence (generic)

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn backend.wsgi:application
```

### Temporary Render deploy

This repo now includes a root [render.yaml](</c:/Users/testi/Documents/bilta/render.yaml:1>) blueprint for a temporary Render backend deploy.

What it provisions:
- one free Python web service
- one free Render Postgres database
- generated Django secret key
- automatic `migrate` on start
- static file collection during build
- health check at `/api/health/`

Important Render caveats:
- the free web service sleeps when idle
- the free Postgres database expires after 30 days
- SQLite should not be used on Render free because local filesystem changes are ephemeral

Suggested flow:
1. Push this repo to GitHub.
2. In Render, create a new Blueprint and select this repo.
3. Deploy the resources from `render.yaml`.
4. After deploy, create your first admin user from the Render shell or a one-off command:

```bash
python manage.py createsuperuser
```

5. Point the frontend API base to your Render backend URL:

```env
VITE_DJANGO_API_BASE=https://your-render-service.onrender.com/api
VITE_USE_DJANGO_API=true
```

## Push backend to a separate repository

If you want backend isolated in its own repo, run:

```bash
git subtree split --prefix backend -b backend-only
git init ../bilta-backend
cd ../bilta-backend
git pull ../bilta backend-only
git remote add origin https://github.com/<your-username>/<your-backend-repo>.git
git push -u origin main
```

If you also want `crm`, `manage.py`, `.env.example`, `requirements.txt`, and `Procfile` in that repo, I can do the clean extraction workflow next.
