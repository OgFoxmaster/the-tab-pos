# The Tab POS

The Tab is an online-only liquor-store POS with a shared FastAPI backend and database, a responsive installable web app, and a Flutter Android app. Both clients use the same product, inventory, sales, staff, and expense records.

## Project layout

- `backend/` — FastAPI API, authentication, inventory and sales workflows.
- `web/` — React/Vite dashboard and installable PWA.
- `mobile/` — Flutter Android application.
- `database/` — SQL schema reference.
- `start-pos.ps1`, `install-pos.ps1`, and `docker-compose.yml` — local workflow helpers.

## Run locally

1. Configure the backend environment. Copy `backend/.env.example` to `backend/.env`, then set a strong `JWT_SECRET`, a working `DATABASE_URL`, and your web origin in `CORS_ORIGINS`. The application defaults to SQLite if `DATABASE_URL` is unset; use PostgreSQL for a shared deployment.
2. Install and start the API:

   ```powershell
   cd backend
   ..\.venv312\Scripts\python.exe -m pip install -r requirements.txt
   ..\.venv312\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   If you do not have the project virtual environment, create one with `python -m venv .venv` and use `.venv\Scripts\python.exe` instead.

3. In a separate terminal, install and start the web app:

   ```powershell
   cd web
   npm install
   npm run dev
   ```

   The default API URL is `http://localhost:8000`. To use another API host, copy `web/.env.example` to `web/.env.local`, set `VITE_API_BASE_URL`, and restart Vite.

4. Open the Vite URL shown in the terminal. In a supported browser, use **Install app** to install The Tab as a PWA. The shell can be cached, but login, checkout, inventory updates, and reports require the live API.

## Android app

Install Flutter, then run the following from `mobile`:

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` is the Android emulator route to the development computer. Debug builds allow cleartext HTTP for local testing. For a physical device, set `API_BASE_URL` to a reachable HTTPS API URL (or the computer's LAN address during local development).

The temporary local-network debug APK is not included in GitHub because generated APKs are excluded. Build a debug APK with the API URL for your own network; it is not a production release.

Build a release APK against the deployed API:

```powershell
flutter build apk --release --dart-define=API_BASE_URL=https://your-api.example.com
```

The API URL is compiled into the Android app; rebuild the APK when it changes.

## Roles and workflows

- **Owner / manager:** dashboard, POS, sales, inventory, expenses, and staff management. Managers cannot create owner or manager accounts.
- **Stock:** inventory visibility and stock receiving.
- **Cashier:** live dashboard, product search, cart, cash checkout, and personal sales history.
- Sales are validated and saved with stock movements in one database transaction. A failed checkout leaves inventory unchanged.
- M-Pesa and card sales are not enabled until verified provider initiation and callback handling are implemented. The current mobile/web checkout only completes cash sales; do not treat an STK request or an unverified callback as a paid sale.

## Initial local accounts

The development backend seeds these accounts on first startup:

- `owner` / `Owner@123`
- `manager` / `Manager@123`
- `cashier` / `Cashier@123`
- `stock` / `Stock@123`

Set unique passwords through the corresponding environment variables before deployment. Do not use these development defaults in production.

## Deployment notes

- Use PostgreSQL and HTTPS for multi-device operation.
- Configure `JWT_SECRET`, database connection, CORS origins, and a reachable API URL for both clients.
- Configure Safaricom Daraja and a supported card provider only when their credentials, signed callbacks, payment status verification, and idempotent stock updates are ready.
- Do not deploy the example environment values or default staff passwords.

## Deploy the web app and API with Vercel

This repository is a monorepo. Create **two Vercel projects** from the same GitHub repository so the React frontend and FastAPI backend each build from their own folder:

1. Provision a hosted PostgreSQL database (for example, Neon or another managed PostgreSQL provider). Do not use the local SQLite database for a deployed POS.
2. In Vercel, import the repository as **The Tab POS API** and set **Root Directory** to `backend`. Let Vercel detect the Python/FastAPI app. Add these environment variables for Production and Preview:
   - `DATABASE_URL` — the provider's PostgreSQL connection URL.
   - `JWT_SECRET` — a newly generated, long random secret.
   - `OWNER_PASSWORD`, `MANAGER_PASSWORD`, `CASHIER_PASSWORD`, and `STOCK_PASSWORD` — unique strong passwords.
   - `APP_BASE_URL` — the deployed API URL.
   - `CORS_ORIGINS` — the deployed frontend origin, such as `https://your-web-project.vercel.app`.
3. Deploy the API first and verify `https://your-api-project.vercel.app/health` returns a healthy response.
4. Import the same GitHub repository again as **The Tab POS Web** and set **Root Directory** to `web`. Vercel detects Vite; use `npm run build` and `dist` if prompted. Add `VITE_API_BASE_URL` with the API deployment URL, for example `https://your-api-project.vercel.app`, then deploy.
5. Add the final frontend domain to the API project's `CORS_ORIGINS` and redeploy the API. Include each Preview frontend origin as needed for preview deployments.

The web project includes `web/vercel.json` for SPA routing. Vercel's Python runtime can host the FastAPI app from `backend/app/main.py`; the application needs the hosted database and environment variables above to work correctly. The Flutter app is not built or hosted by Vercel; its APK is built separately with the deployed API URL:

```powershell
cd mobile
flutter build apk --release --dart-define=API_BASE_URL=https://your-api-project.vercel.app
```

For security, generated APKs, local databases, `.env` files, virtual environments, and build folders are excluded by `.gitignore`. Keep payment-provider credentials in Vercel environment settings, not in GitHub.
