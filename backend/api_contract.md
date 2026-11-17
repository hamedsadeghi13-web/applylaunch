# Backend API contract (v1) – STATUS: design, not implemented

Hosting suggestion: Supabase (Postgres + Auth + Edge Functions, free tier) or any small server. Secrets live only in the host's secret store.

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /search?q=&cc=&type=&funding=&limit=` | public | **Hybrid search.** 1) full-text over `positions` (nightly data), 2) in parallel a live probe of the top verified portals' search pages (rate-limited, cached 6 h), 3) normalise with the same extractor as `crawl.py`, 4) de-duplicate by URL and `(title, institution)`, 5) return `{positions:[…raw fields…]}`. The website already consumes this when `docs/config.json` has `"api": "https://…"` and merges it with the local data (`posOnlineKick` in index.html). |
| `GET /professors?q=&cc=&status=` | public | Same for professors (dataset + live OpenAlex lookup). |
| `GET/PUT /me/profile` | user | profile JSON (replaces localStorage) |
| `GET/PUT/DELETE /me/saved` | user | saved positions / professors |
| `GET/PUT /me/notifications` | user | e-mail preferences |
| `POST /admin/ingest` | service key | workers push `positions` / `professors` / `sources` (GitHub Actions can call this instead of committing JSON) |

Rules: every position/professor row carries its original URL; fields that were not found stay `NULL` (never guessed); expired rows are removed by a nightly job.
