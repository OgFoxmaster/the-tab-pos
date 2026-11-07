# The Tab feature parity checklist

This is the release gate for the React/Vite web app and Flutter Android app. Both clients use the same FastAPI API, database, authentication and backend permission rules.

A feature is **Both tested** only when the same backend workflow has been exercised from web and Android. A client surface alone is not sufficient.

## Status definitions

- `[ ]` Not implemented or not verified.
- `[~]` Partially implemented; the client has some related capability, but not the complete feature.
- `[x]` Implemented and tested against the shared backend on both clients.

## Release matrix

| Feature | Web | Android APK | Both tested | Notes |
| --- | --- | --- | --- | --- |
| Login, logout and password reset | `[~]` | `[~]` | `[ ]` | Web has reset UI and login code; Flutter has login-code flow but no reset UI. |
| Company registration and setup | `[~]` | `[ ]` | `[ ]` | Web collects company and first branch; Flutter does not yet have registration. |
| Company and branch switching | `[ ]` | `[ ]` | `[ ]` | Backend exposes company context and branch list; switching UI is not implemented. |
| Employee creation and role assignment | `[x]` | `[ ]` | `[ ]` | Web Users supports staff management; Flutter has no employee management screen. |
| Role-specific dashboards | `[~]` | `[~]` | `[ ]` | Existing role navigation exists; expanded departments need equivalent screens and tests. |
| POS checkout and cart management | `[x]` | `[x]` | `[ ]` | Cash checkout is implemented on both; payment integrations remain unchanged. |
| Product search and barcode scanning | `[x]` | `[~]` | `[ ]` | Web has SKU scanning/search; Flutter has product search but no barcode scanner. |
| Inventory receiving and adjustments | `[x]` | `[~]` | `[ ]` | Receiving exists; adjustment and cross-client verification remain. |
| Suppliers and procurement | `[ ]` | `[ ]` | `[ ]` | Not implemented. |
| Expenses and financial records | `[x]` | `[x]` | `[ ]` | Expense creation/listing exists; shared workflow still needs cross-client tests. |
| Sales history, refunds and receipts | `[~]` | `[~]` | `[ ]` | Sales history exists; refunds/receipts are not complete in both clients. |
| Daily, weekly and monthly reports | `[x]` | `[ ]` | `[ ]` | Web reports exist; Flutter report screen is missing. |
| AI business analyst | `[x]` | `[ ]` | `[ ]` | Web insights exist; Flutter client is missing. |
| Subscription and account management | `[ ]` | `[ ]` | `[ ]` | Not implemented. |
| Audit logs and activity history | `[ ]` | `[ ]` | `[ ]` | Backend audit records exist; client views and full verification are missing. |

## Shared backend contract

- FastAPI OpenAPI is the API contract for both clients.
- Tenant ownership, branch access, role checks, pricing, discounts, stock changes and financial calculations are enforced by the backend.
- Do not duplicate business rules in React or Flutter to make a client appear complete.
- M-Pesa and card integrations are intentionally outside the current foundation work and must not be rewritten as part of parity work.

## Release gate

Before a release is called feature-complete:

1. Run `python scripts/check_feature_parity.py`.
2. Build the web application.
3. Run Flutter analysis and build the release APK.
4. Exercise each changed workflow from both clients against the same API/database.
5. Update this file only with evidence from those checks; do not change `[ ]` to `[x]` based on code presence alone.

## Online/offline policy

The target release policy is **online-only** for web and Android business operations. The web client currently contains an offline sales queue and related messaging; this is tracked as a reconciliation item and must not be expanded to Android until the product decision is made and both clients implement the same policy.
