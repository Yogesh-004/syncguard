# Security

- **Secrets:** never committed; `.env` + `.env.example`; image contains no secrets.
- **Uploads:** 5MB/10k limit (configurable), mime sniff, sanitize filename, block path traversal (`../`), reject malformed, never trust extension, never execute uploaded code.
- **API:** Pydantic validation, rate limiting on uploads/reconciliation, CORS allowlist, secure headers (HSTS, X-Content-Type-Options).
- **Auth:** v0 anonymous; JWT (python-jose+passlib) ready; every resolution logs `resolved_by`.
- **PII:** repo uses synthetic data only; docs warn: "Do not upload confidential/production data to public demo".
- **Errors:** never expose stack traces to client; log server-side.
