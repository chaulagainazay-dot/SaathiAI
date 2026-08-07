# M61 — Server Search

`GET /workflow/search?q=&type=&limit=` — authorized, tenant-scoped server search
across missions, projects, approvals, templates, and notifications. Scope reported
as `SERVER_AUTHORIZED`. Never leaks unauthorized objects (org/workspace scoped at
the store layer; a second tenant sees zero results — certified). Was:
SEARCH_AUTHORIZED_LOADED_RECORDS (client) → now SERVER_AUTHORIZED. The M60 search
page now queries the server (debounced).
