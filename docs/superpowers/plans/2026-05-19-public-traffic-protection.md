# Public Traffic Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add list-route abuse protection and internal date-aware real browser traffic statistics for the read-only public Django site.

**Architecture:** Extend `PublicReadOnlyMiddleware` for cache-backed list route and fingerprint limits. Add a `PublicTrafficDailyStat` aggregate model plus a `blog.traffic` service to classify and record browser visits. Add a token-protected internal JSON stats endpoint.

**Tech Stack:** Django 5.2, Django cache framework, Django ORM, built-in Django test runner.

---

### Task 1: Tests First

**Files:**
- Modify: `djangoblog/test_read_only.py`
- Create: `blog/test_public_traffic.py`

- [ ] Add failing middleware tests for list route and fingerprint rate limits.
- [ ] Add failing traffic recording tests for browser vs script requests.
- [ ] Add failing stats endpoint tests for token protection and date filtering.
- [ ] Run `python manage.py test djangoblog.test_read_only blog.test_public_traffic` and confirm the new tests fail because implementation is missing.

### Task 2: Traffic Model

**Files:**
- Modify: `blog/models.py`
- Create: `blog/migrations/0014_publictrafficdailystat.py`

- [ ] Add `PublicTrafficDailyStat` with `date`, `route_name`, `path`, `ip_address`, `fingerprint`, `user_agent`, `visit_count`, `first_seen`, and `last_seen`.
- [ ] Add a uniqueness constraint on `(date, route_name, path, ip_address, fingerprint)`.
- [ ] Add indexes for date/route and date/path lookups.
- [ ] Run targeted tests and confirm model import errors are resolved.

### Task 3: Traffic Service

**Files:**
- Create: `blog/traffic.py`

- [ ] Implement `get_client_ip(request)` using `X-Forwarded-For` first and `REMOTE_ADDR` fallback.
- [ ] Implement `route_name_for_path(path)` for `index`, `index_page`, `news`, and `search`.
- [ ] Implement `request_fingerprint(request)` with SHA-256 over route path, query string, and user agent.
- [ ] Implement `looks_like_browser(request)` with the conservative browser heuristic from the design.
- [ ] Implement `record_public_visit(request)` using `get_or_create` and `F('visit_count') + 1`.
- [ ] Run traffic tests and confirm browser/script behavior passes.

### Task 4: Middleware Protection

**Files:**
- Modify: `djangoblog/read_only.py`
- Modify: `djangoblog/settings.py`

- [ ] Add `PUBLIC_LIST_RATE_LIMIT_PER_MINUTE`, default `60`.
- [ ] Add `PUBLIC_FINGERPRINT_RATE_LIMIT_PER_MINUTE`, default `90`.
- [ ] In `PublicReadOnlyMiddleware`, keep the existing global IP limit.
- [ ] Add watched-route list rate limit keyed by IP and route.
- [ ] Add fingerprint rate limit keyed by IP and request fingerprint.
- [ ] Record public browser visits after rate-limit checks pass.
- [ ] Run middleware and traffic tests.

### Task 5: Internal Stats Endpoint

**Files:**
- Modify: `blog/views.py`
- Modify: `blog/urls.py`

- [ ] Add `public_traffic_stats_view`.
- [ ] Return `404` if `PUBLIC_TRAFFIC_STATS_TOKEN` is missing or token does not match.
- [ ] Support `date`, `start`, `end`, and `limit`.
- [ ] Return JSON with `total_visits` and row objects.
- [ ] Add route `/_internal/traffic-stats/`.
- [ ] Run endpoint tests.

### Task 6: Final Verification

**Files:**
- No new code files.

- [ ] Run `python manage.py test djangoblog.test_read_only blog.test_public_traffic`.
- [ ] Run `python manage.py check`.
- [ ] Review `git diff --stat` and `git diff` for unintended edits.

