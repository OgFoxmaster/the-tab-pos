# Security checklist

- Use strong secrets in production.
- Rotate JWT secret and change default owner credentials.
- Restrict CORS to production origins.
- Use HTTPS behind a reverse proxy or cloud load balancer.
- Enforce role-based access control on every sensitive endpoint.
- Never store plaintext passwords; use hashed passwords only.
- Keep PostgreSQL credentials out of source control.
- Back up the database and enable audit logs.
