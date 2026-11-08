# Thetabpos (The Tab POS)

The Tab is a liquor-store POS with a shared FastAPI backend and database, an installable web till, and a Flutter Android app. Both clients use the same product, inventory, sales, staff, and expense records.

The web till is **offline-first**: it caches the catalog on the device and keeps taking cash sales when the network drops, then syncs them (idempotently) when it reconnects. It accepts **M-Pesa** through Safaricom Daraja (STK Push, verified callbacks, idempotent settlement), lets the first owner **create their account from the login screen with a Gmail address**, lets that owner **create staff logins with name, username, password and role**, and supports **forgot password** by email. Owners and managers also get **daily, weekly and monthly reports**, CSV export, refunds with stock restoration, VAT receipts, and an **AI sales analyst** that answers questions about the computed numbers.

For production hosting, naming and the go-live checklist see [`DEPLOYMENT.md`](DEPLOYMENT.md).

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
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   On macOS/Linux use `source .venv/bin/activate` and `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.

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

The API URL is compiled into the Android app; rebuild the APK when it changes. The repository also
ships `.github/workflows/android-apk.yml`: set the GitHub Actions repository variable
`API_BASE_URL`, run **Build Thetabpos APK**, and download the `thetabpos-apk` artifact. The Flutter
client currently covers the online cash workflow; the web PWA is the complete till with M-Pesa,
owner signup, staff logins and password reset.

## Roles and workflows

- **Owner / manager:** dashboard, POS with cash or M-Pesa, sales, refunds, reports, AI insights, inventory, expenses, and staff management. Managers cannot create or edit owner or manager accounts.
- **Stock:** inventory visibility and stock receiving.
- **Cashier:** live dashboard, product search, cart, discounts, cash checkout, and personal sales history.
- Sales are validated and saved with stock movements in one database transaction. A failed checkout leaves inventory unchanged.
- Refunds restore stock, mark the payment refunded, write an audit event, and are excluded from revenue.
- Prices are treated as VAT-inclusive (16% by default) and the VAT portion is shown on receipts; set `VAT_RATE=0` to disable it.
- The offline till queues cash sales in IndexedDB with a unique `client_reference`; `POST /sales` is idempotent on that reference, so a retry cannot double-deduct stock. Offline replays older than `OFFLINE_SALE_MAX_AGE_DAYS` are rejected.
- M-Pesa uses a payment-intent flow: the API prices the basket, sends the STK prompt, and creates the sale only after the callback is verified with the STK query endpoint. Failed or cancelled prompts create no sale; repeats settle once. Cash remains the only offline payment.

## Reports and the AI analyst

Owners and managers can open **Reports** for today, this week or this month: revenue, average basket, gross profit, expenses, net, refunds, VAT, an hourly/daily chart, top products, payment mix, cashier performance, restock attention and CSV export. **Insights** generates a rules-based briefing that always works, and — when `ZAI_API_KEY` is configured on the server — lets you ask questions answered from that same computed snapshot. The model never sees raw customer or staff data.

## Accounts, staff and password reset

On a fresh database (`SEED_DEMO_DATA=false`) the login screen offers **Create owner account**. Enter
the shop's Gmail address and a strong password; that account becomes the owner. Signup then closes,
unless the address is added to `OWNER_SIGNUP_EMAILS` (and optionally `OWNER_SIGNUP_CODE`).

The owner opens **Users** to create each staff login with full name, username, password and role
(`manager`, `cashier` or `stock`). **Forgot password?** on the login screen emails a single-use reset
link when Mailtrap SMTP is configured (`MAILTRAP_API_TOKEN` and `MAILTRAP_FROM`). Without Mailtrap,
development returns a reset link instead of sending mail; production returns a clear error.

For local development, the backend still seeds the demo accounts when `SEED_DEMO_DATA=true`:
`owner` / `Owner@123`, `manager` / `Manager@123`, `cashier` / `Cashier@123`, `stock` / `Stock@123`.
Set unique passwords, or set `SEED_DEMO_DATA=false` and claim the owner account from the UI.

## Deployment

The full research and step-by-step path is in [`DEPLOYMENT.md`](DEPLOYMENT.md). The short version:
host the FastAPI API on a Python runtime with managed PostgreSQL (the included `render.yaml` creates
`thetabpos-api` and `thetabpos`), point `VITE_API_BASE_URL` at the API, set `CORS_ORIGINS` and
`APP_WEB_URL` to the web origin, and set `APP_ENV=production` with a real `JWT_SECRET`. Then claim
the owner account from the login screen, create staff logins,and add the Daraja M-Pesa credentials and Mailtrap SMTP settings. The API refuses to start with the placeholder JWT secret.

## Deployment notes

- Use PostgreSQL and HTTPS for multi-device operation.
- Configure `JWT_SECRET`, database connection, CORS origins, and a reachable API URL for both clients.
- Configure Safaricom Daraja in the API environment; M-Pesa appears in the till automatically when the keys are present, and stays hidden otherwise.
- Do not deploy the example environment values or default staff passwords.

## Deployment on Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/OgFoxmaster/the-tab-pos)

Sign in with the GitHub account that owns this repository, verify your email, and approve the
blueprint. The first deploy needs no secrets: it starts with cash sales and owner signup.Add the M-Pesa Daraja settings and Mailtrap SMTP settings on the API service afterwards to turn on M-Pesa and
password-reset email.

`render.yaml` defines the API (`thetabpos-api`), PostgreSQL and the static web app (`thetabpos`).

1. Push the repository to GitHub.
2. Click the button above, or Render: **New → Blueprint**, select the repository, apply.
3. Add the M-Pesa Daraja keys and Mailtrap settings on the API service after the first deploy. If Render
   suffixes a service name, update `CORS_ORIGINS`, `APP_WEB_URL` and `VITE_API_BASE_URL` to the URLs
   Render shows. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for each value.
4. Deploy the API, confirm `/health`, deploy the web app, then open its URL.
5. Choose **Create owner account** on the login screen, then add staff from **Users**.

Expected URLs: `https://thetabpos-api.onrender.com` (API) and `https://thetabpos.onrender.com` (web).
Render adds a suffix if a name is already taken, so use the exact URLs it shows. Vercel or
Cloudflare Pages can host the static frontend, but the FastAPI API needs a Python runtime with
PostgreSQL. Do not put payment or Mailtrap secrets in the web build.
