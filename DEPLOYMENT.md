# Running Thetabpos in production

This is the deployment path for this repository: what to host where, which secrets to set, how to
take M-Pesa live, and what to verify before the shop depends on it.

## 1. Naming

| Thing | Recommendation | Why |
|---|---|---|
| Product / brand | **Thetabpos** | Deployed site name, page title and receipts. |
| Web till | **Thetabpos** | Installable PWA name on the phone home screen. |
| API host | **thetabpos-api** | Separate origin for CORS and certificates. |
| Expected web URL | `https://thetab.co.ke` | Custom domain attached to the Render static service. |
| Expected API URL | `https://api.thetab.co.ke` | Custom domain attached to the Render API service. |
| Custom domain | **thetab.co.ke** | `.co.ke` signals a Kenyan business, KSh pricing and 16% VAT. |

A custom domain has to be registered by you (a KENIC-accredited registrar for `.co.ke`). Render
attaches it and issues TLS automatically. The `onrender.com` URL works immediately without a domain.

## 2. Architecture

```
Android APK ─┐
             ├─► FastAPI + PostgreSQL  (Render web service + Render Postgres)
Web PWA ─────┘            ▲
                          └── static React build (Render static site / Vercel / Cloudflare Pages)
```

- **FastAPI must run on a normal Python runtime.** Sales are written in a database transaction with
  row locks (`SELECT … FOR UPDATE`) so stock cannot oversell. Cloudflare Workers/Pages Functions and
  Vercel Functions do not run Python or long-lived Postgres transactions, so the API cannot live
  there. Edge platforms are fine for the static frontend only.
- **One Postgres database** is the single source of truth for the web till and any other client.
- **The PWA is the offline till.** It caches the catalog in IndexedDB, queues cash sales, and syncs
  when connectivity returns (see §7). That requires HTTPS, which every option below provides.
- **SQLite is for development only.** It has no row locking, so never run two tills against it.

## 3. Render blueprint (recommended: one account, lowest setup)

`render.yaml` in the repository root defines everything: Postgres, the API service and the static
web app. The service names are already **thetabpos** (web) and **thetabpos-api** (API).

1. Push the repository to GitHub.
2. In Render: **New → Blueprint**, select the repository, apply.
3. Fill the `sync: false` values Render asks for:
   - `CORS_ORIGINS` — the web URL, e.g. `https://thetab.co.ke` (add a custom domain too:
     `https://thetabpos.co.ke,https://www.thetabpos.co.ke`). You can start with this value before the
     first deploy.
   - `APP_WEB_URL` — `https://thetab.co.ke`. Password-reset links are built from it.
   - `OWNER_SIGNUP_EMAILS` — the Gmail address that may claim the owner account, e.g.
     `you@gmail.com`. Add more comma-separated addresses only if you want more owners.
   - `OWNER_SIGNUP_CODE` — optional extra shared code asked for on the signup form.
   - `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`,
     `MPESA_CALLBACK_URL`, `MPESA_CALLBACK_TOKEN` — see §4. You can leave them empty at first; the
     web till then hides M-Pesa and only offers cash.    - `MAILTRAP_HOST`, `MAILTRAP_PORT`, `MAILTRAP_USERNAME`, `MAILTRAP_API_TOKEN`, `MAILTRAP_FROM`, `MAILTRAP_FROM_NAME` — see §5. The API reports these present when both token and sender are non-empty, but only a real reset request can confirm SMTP delivery. Mailtrap rejects SMTP when the token is wrong, the username is wrong, or `MAILTRAP_FROM` is not a verified sender. Without them a
     production password reset returns “email is not configured” instead of pretending to send.
   - `VITE_API_BASE_URL` on the static site — `https://api.thetab.co.ke`.
   - `ZAI_API_KEY` / `EXA_API_KEY` — optional AI analyst and web research (§6).
4. Deploy the API first and confirm its `/health` returns `"status":"ok"`. Then deploy the web app
   and open `https://thetab.co.ke`.
5. On the login screen choose **Create owner account**, enter the shop's Gmail address and a strong
   password. That account is the owner; staff logins are created from **Users**.
6. If the web URL changed, update `CORS_ORIGINS` and `APP_WEB_URL`, then redeploy the API.

Free plans sleep after inactivity and are for testing. Use the paid starter plans for a real shop:
the till should never wait for a cold start.

## 4. M-Pesa (Safaricom Daraja)

The till uses **M-Pesa Express (STK Push)** with a payment-intent flow:

1. The cashier enters the customer's phone and sends the basket to the API.
2. The API prices the basket, stores a `payment_intents` row, and asks Daraja to prompt the phone.
3. The customer approves with their M-Pesa PIN. Safaricom posts a callback.
4. **The callback is verified with the STK push query endpoint before a sale is created.** A forged
   callback cannot mark an order paid. The till also polls the intent and can ask the server to
   verify manually.
5. Failed/cancelled payments create no sale and do not touch stock. Settlement is idempotent: a
   repeated callback or retry returns the same sale.

Set these on the **API** service (never in the web build):

| Variable | Value |
|---|---|
| `MPESA_ENV` | `production` for live money, `sandbox` for testing. |
| `MPESA_CONSUMER_KEY` | Daraja app Consumer Key. |
| `MPESA_CONSUMER_SECRET` | Daraja app Consumer Secret. |
| `MPESA_SHORTCODE` | Paybill/Till number (sandbox default `174379`). |
| `MPESA_PASSKEY` | M-Pesa Express passkey for that shortcode. |
| `MPESA_TRANSACTION_TYPE` | `CustomerPayBillOnline` (or `CustomerBuyGoodsOnline` for a Till). |
| `MPESA_CALLBACK_URL` | `https://api.thetab.co.ke/mpesa/callback` |
| `MPESA_CALLBACK_TOKEN` | A long random secret. It is appended to the callback path automatically. |
| `MPESA_SIMULATE` | `false` in production. Simulation is ignored when `APP_ENV=production`. |

Where to get the values: create an app at <https://developer.safaricom.co.ke>, add the M-Pesa
Express product, then copy the Consumer Key/Secret and the Lipa na M-Pesa passkey for the shortcode.
The callback URL must be public HTTPS. For sandbox testing use `MPESA_ENV=sandbox`, the sandbox
shortcode/passkey and Safaricom's test MSISDN.

Before opening: sell **KSh 1** through M-Pesa, confirm the sale appears once in **Sales**, the stock
drops once, the receipt shows the M-Pesa receipt code, and a cancelled prompt produces no sale.
`GET /meta` reports `mpesa_enabled: true` and `mpesa_simulate: false` in production.

### Testing without Safaricom credentials

In development only (`APP_ENV=development` plus `MPESA_SIMULATE=true`) the POS shows **Simulate
paid** and **Simulate failed** buttons. This exercises the exact same settlement path without money.
It is disabled automatically when `APP_ENV=production`, and `POST /mpesa/simulate/...` returns 404.

## 5. Owner signup, staff accounts and password reset

**Owner signup (login screen).** On a fresh database the login screen shows **Create owner
account**. It accepts a Gmail address and password, creates the `owner` account and signs in. This
is email + password signup with a Gmail address, not Google OAuth; OAuth would need a Google Cloud
client ID/secret and an extra consent screen.

- Signup is open while no owner exists.
- After that it is only open for addresses in `OWNER_SIGNUP_EMAILS`.
- If `OWNER_SIGNUP_CODE` is set, the form also asks for that code.
- `SEED_DEMO_DATA=false` keeps the startup from creating demo staff accounts, so the first real
  owner can claim the shop.

**Staff logins.** The owner opens **Users** and creates each staff member with their full name, a
unique username, a password and a role (`manager`, `cashier`, `stock`). The same page can change a
role, reset a password or deactivate an account. Managers can manage cashiers/stock but cannot create
or edit owner/manager accounts.

**Forgot password.** The login screen's **Forgot password?** asks for the account email and sends a
single-use link that expires after `PASSWORD_RESET_MINUTES` (30 by default). Configure Mailtrap SMTP
Sending on the API service:

- No Mailtrap SDK is required; the API uses Python's built-in `smtplib`.
- Set `MAILTRAP_HOST=live.smtp.mailtrap.io` and `MAILTRAP_PORT=587`.
- Set `MAILTRAP_USERNAME=api` and `MAILTRAP_API_TOKEN` to the Mailtrap SMTP/API token.
- Set `MAILTRAP_FROM=hello@thetab.co.ke` (or another address on a verified Mailtrap sending domain).
- Set `MAILTRAP_FROM_NAME=The Tab POS`.

If the API reports `email_reset_configured: true` but the password-reset email still fails, the API variables are present and the problem is Mailtrap SMTP rejecting the message. The most likely causes, in order, are:

1. `MAILTRAP_API_TOKEN` is the account password or an expired token, and SMTP rejects it with `535 Authentication failed`.
2. `MAILTRAP_FROM` is not a verified sender on the Mailtrap account.
3. The sender domain is not verified in Mailtrap.
4. The Mailtrap account does not have sending enabled for the configured environment.

To confirm which one, trigger a single forgot-password request for a registered account and check the Mailtrap Email Logs:

- https://mailtrap.io/sending/email_logs

If no message appears there at all, SMTP authentication or sender validation rejected the attempt before Mailtrap accepted it. If a message appears but is marked undelivered or bounced, Mailtrap accepted the attempt but rejected the sender or domain.

If Render deploys a newer build and the API still reports `email_reset_configured: false`, the most likely cause is that the deployed backend is still running an older release, not that the variables are missing. In that case:

1. Open the `thetabpos-api` service in the Render dashboard.
2. Open the latest deploy under **Events** and read its build and start logs for `MAILTRAP` or `WARNING` lines.
3. Confirm the service is running the commit you expect.
4. If needed, trigger a manual redeploy from the service’s **Manual Deploy** menu.

The token must never be committed or placed in the web build. Check sent messages at
<https://mailtrap.io/sending/email_logs>. The link points at `APP_WEB_URL/?reset=<token>`. Reset
tokens are stored hashed, are single-use, and are invalidated when the password changes. Without
Mailtrap in development the API returns a development reset link so the flow can still be tested;
production refuses with a clear 503 instead of silently failing.

## 6. AI sales analyst (Z.ai)

The analyst never sees raw rows. The API computes the report, sends a compact JSON snapshot to an
OpenAI-compatible chat-completions endpoint, and returns the answer with the same numbers so the UI
can display the evidence. Without a key the app still works: the rules-based briefing is generated
locally in Python.

1. Create an API key at <https://z.ai> (recommended: low-cost GLM models, OpenAI-compatible).
2. Set these in the **API** service environment, never in the web build:
   - `ZAI_API_KEY` — the key (secret).
   - `ZAI_API_BASE` — `https://api.z.ai/api/paas/v4`.
   - `AI_MODEL` — `glm-4-flash` by default; allowed: `glm-4-flash`, `glm-4-air`, `glm-4-plus`,
     `glm-4.6`, `gpt-4o-mini`.
   - `AI_DAILY_LIMIT` — questions per account per day (default 40).
3. Restart the API and check `GET /ai/status` as an owner: `"configured": true`.
4. In the app, **Insights** shows the live badge and lets owners/managers ask questions.

## 7. Offline behaviour (and its limits)

The web till is offline-first:

- After the first successful load the catalog and prices are cached in IndexedDB.
- If the network drops, cash checkout writes the sale to a local queue with a UUID
  (`client_reference`) and the time it happened (`sold_at`), then decrements the cached stock.
- The sale replays automatically when the browser reports `online`, and every 30 seconds while a
  queue exists. `POST /sales` is idempotent on `client_reference`, so a retry can never double-charge
  or double-deduct stock.
- The server rejects replays older than `OFFLINE_SALE_MAX_AGE_DAYS` (14 by default) or stamped more
  than 10 minutes in the future, so a tampered till clock cannot rewrite history.
- A 4xx rejection (for example, stock changed while offline) keeps the sale in the queue and shows
  it in the app instead of silently dropping it.

Limits to plan around:

- Offline is for **cash** only. M-Pesa needs a live STK prompt and callback, so the M-Pesa button
  requires this till to be online. A failed M-Pesa prompt is never queued as a paid sale.
- Stock is validated **again** on sync. If two tills sold the last bottle while offline, the second
  sync is rejected and the cashier must resolve it; sell from one till per product category while
  offline if that matters.
- The Android app is still online-only. The web PWA is the offline-capable client.
- The service worker never caches `/login` or authenticated API responses, so a stolen device does
  not leak data from the cache.

## 8. Environment variables (API)

| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | yes | `production` enables the safety checks and disables simulation. |
| `DATABASE_URL` | yes | `postgresql://…` is rewritten to the psycopg 3 dialect automatically. |
| `JWT_SECRET` | yes | ≥32 random chars; the API refuses to boot with the placeholder. | | `CORS_ORIGINS` | yes | Comma-separated exact web origins. |
 | `STORE_NAME` | yes | `The Tab POS`. App-facing brand name for the API and email subjects. |
 | `STORE_TAGLINE` | no | `Liquor Store`. Optional tagline appended to the store name in config and email subjects. |

| `APP_WEB_URL` | yes | Web URL used in password-reset links. |
| `SEED_DEMO_DATA` | yes | `false` for a real shop; the owner signs up instead. |
| `OWNER_SIGNUP_EMAILS`, `OWNER_SIGNUP_CODE` | no | Additional owners after the first claim. |
| `PASSWORD_RESET_MINUTES` | no | Reset link lifetime, default 30. | | `STORE_TAGLINE` | no | `Liquor Store`. Optional tagline appended to the store name in config and email subjects. |
 | `MAILTRAP_HOST`, `MAILTRAP_PORT`, `MAILTRAP_USERNAME`, `MAILTRAP_API_TOKEN`, `MAILTRAP_FROM`, `MAILTRAP_FROM_NAME` | for email reset | Mailtrap SMTP host/port, username, token, and sender. |
| `MPESA_ENV`, `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY` | for M-Pesa | Daraja credentials. |
| `MPESA_CALLBACK_URL`, `MPESA_CALLBACK_TOKEN` | for M-Pesa | Public HTTPS callback; token is appended to the path. |
| `MPESA_TRANSACTION_TYPE`, `MPESA_SIMULATE` | no | Defaults `CustomerPayBillOnline`, `false`. |
| `STORE_*`, `VAT_RATE` | no | Receipt header, currency and VAT breakdown. |
| `ZAI_API_KEY`, `ZAI_API_BASE`, `AI_MODEL`, `AI_DAILY_LIMIT` | no | AI analyst. |
| `EXA_API_KEY`, `EXA_NUM_RESULTS` | no | Web research for the AI analyst. |
| `OFFLINE_SALE_MAX_AGE_DAYS`, `OFFLINE_SALE_MAX_FUTURE_MINUTES` | no | Offline replay window. |

## 9. Android APK

The repository includes `.github/workflows/android-apk.yml`, which builds the Flutter APK on GitHub
Actions and uploads it as the **thetabpos-apk** artifact.

1. In GitHub: **Settings → Secrets and variables → Actions → Variables**, add
   `API_BASE_URL=https://api.thetab.co.ke`.
2. In GitHub, open **Actions → Build Thetabpos APK → Run workflow**.
3. Open the finished run and download **thetabpos-apk**, then install the APK on the phone. Android
   may ask you to allow installs from the browser/file manager.

Build locally instead:

```bash
cd mobile
flutter pub get
flutter build apk --release --dart-define=API_BASE_URL=https://api.thetab.co.ke
# mobile/build/app/outputs/flutter-apk/app-release.apk
```

The API URL is compiled into the APK, so rebuild when it changes. The Flutter app currently offers
the online cash workflow; the web PWA is the complete till with owner signup, staff logins, M-Pesa,
offline sales and receipts. On a phone, open the web URL in Chrome and choose **Add to Home screen**
to get the full till as an app while the Flutter client is being extended.

## 10. Go-live checklist

- [ ] `APP_ENV=production`, `SEED_DEMO_DATA=false` and a generated `JWT_SECRET`.
- [ ] Owner account claimed with the shop's Gmail address from the login screen.
- [ ] Staff accounts created for each real person; shared logins removed.
- [ ] A test password reset email received and used once; check Mailtrap Email Logs.
- [ ] `CORS_ORIGINS` and `APP_WEB_URL` contain only the real web origin.
- [ ] HTTPS on both the API and the web till.
- [ ] Catalog loaded with real products, buying prices, selling prices and stock.
- [ ] A test cash sale, a refund, an offline cash sale and a CSV report export.
- [ ] M-Pesa tested with KSh 1: receipt code on the receipt, one sale, stock down once, cancelled
      prompt leaves no sale.
- [ ] `GET /meta` shows `mpesa_enabled: true` and `mpesa_simulate: false`.
- [ ] A daily database backup (Render Postgres point-in-time recovery or `pg_dump` cron).
- [ ] Receipt printer configured from the browser print dialog (80mm receipt CSS included).
- [ ] APK built with the production API URL and installed on the selling phone(s).

## 11. Operating notes

- **Reports** are computed from sales rows for the selected window and compared with the previous
  window; daily uses hourly buckets, weekly/monthly use per-day buckets.
- **Audit trail** (`audit_events`) records sale, refund, product, inventory, staff and M-Pesa
  settlement events; it is written in the same request as the action.
- **Refunds** restore stock and mark the payment refunded; a refunded sale is excluded from revenue.
- **Costs** are snapshotted onto each sale line, so later buying-price changes do not rewrite past
  margins. Sales recorded before this version have no cost snapshot.
- **M-Pesa recovery:** if M-Pesa is paid but stock changed before settlement, the intent is marked
  paid with a `problem` note and an audit event, and no sale is created. Refund the customer from the
  M-Pesa receipt; the till shows the warning.
- The API keeps login throttling and the AI daily counter in memory. Run **one** API instance, or
  move those counters to Postgres/Redis before scaling horizontally.
