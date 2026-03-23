# SILVERLINE Freight Services

Standard delivery website with:

- Client-facing tracking checker (`/`)
- Full services page (`/services/`)
- Backend admin login (`/backend/login/`)
- Shipment creation with backend-generated tracking number
- Item-level shipment details (name, quantity, weight, description)
- Live delivery progress per shipment (0-100), controlled from backend
- Withhold/release workflow managed from backend
- Hold status message shown on client tracking view

## Tech Stack

- Python 3.12
- Django 5
- SQLite (local), PostgreSQL-ready via `DATABASE_URL` (Render)
- WhiteNoise + Gunicorn for production serving

## Local Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_admin
python manage.py runserver
```

## Backend Admin Credentials

Set these in `.env` (local) and Render environment variables (production):

- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

Then run:

```bash
python manage.py bootstrap_admin
```

## Order Lifecycle

1. Login at `/backend/login/`
2. Create order from dashboard (`from` and `to` address)
3. Tracking number is generated automatically in backend
4. Optionally place order on hold with amount and message
5. Client sees hold message on tracking page
6. Admin releases hold after payment and shipment resumes

## Deploy on Render

- `render.yaml` is included.
- Push this project to GitHub and connect repo in Render.
- Render will run:
  - Build: install dependencies + `collectstatic`
  - Start: `migrate`, `bootstrap_admin`, and start Gunicorn

Recommended env vars on Render:

- `DEBUG=False`
- `SECRET_KEY=<render-generated>`
- `ALLOWED_HOSTS=.onrender.com`
- `CSRF_TRUSTED_ORIGINS=https://*.onrender.com`
- `DATABASE_URL=<Render PostgreSQL URL>`
- `ADMIN_EMAIL=<your-admin-email>`
- `ADMIN_PASSWORD=<your-strong-password>`
