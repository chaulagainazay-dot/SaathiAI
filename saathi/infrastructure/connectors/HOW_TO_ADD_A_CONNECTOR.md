# Adding a Connector

A new integration = **one driver + its manifest**. No business logic changes, no
registry changes. This is the whole procedure.

## 1. Write the driver

Create `drivers/<service>.py` (or `drivers/<category>/<service>.py`). It is the
**only** file allowed to import the service's SDK / know its endpoints.

```python
from ..base import Connector, Health, Status, RateLimited
from ..manifest import Manifest

_CAPS = frozenset({"do_thing", "do_other"})

class MyServiceConnector(Connector):
    id = "myservice"

    def __init__(self, token=None, transport=None):
        import os
        self._token = token if token is not None else os.getenv("MYSERVICE_TOKEN", "")
        self._transport = transport            # injectable for tests (httpx.MockTransport)

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="My Service", category="media", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound"}),
            requires_auth=True, cost=0.0, latency="low", reliability=0.97,
            rate_limits={"requests_per_second": 10},
            health_checks=frozenset({"token", "api"}))

    def authenticate(self) -> bool:
        return bool(self._token) and not self._token.startswith("YOUR")

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "MYSERVICE_TOKEN missing")
        # ...ping the API; map to OK / DEGRADED / DOWN, put quota_remaining in metrics
        return Health(Status.OK, "reachable")

    def execute(self, capability: str, **payload):
        self._require(capability)              # gates capability + auth
        # ...call the SDK/API, raise RateLimited on 429, AuthRequired on 401
        return {...}
```

Rules:
- **Transport/side-effects injectable** (so tests run with no network).
- `health()` never raises — catch and map to `Status`.
- Put a numeric `quota_remaining` (0–100) in `Health.metrics` if the service has quota; the registry emits `connector.quota_warning` when it drops ≤ 15.

## 2. Register it

Add the class to `drivers/__init__.py` and to `_DEFAULT_DRIVER_CLASSES` in
`connectors/__init__.py`. Done — `install_defaults()` now includes it, and it
appears in `diagnostics.snapshot()`.

## 3. Test it

`tests/test_connector_drivers.py` style: drive `execute`/`health` through an
`httpx.MockTransport`. Assert capability routing, auth gating, and one happy path.

## What you get for free

- **Direct** use: `registry.get("myservice").execute("do_thing", ...)`
- **Capability** routing: `registry.execute(capability="do_thing", ...)` picks the
  best healthy connector (rank: health → reliability → cost → latency)
- **Diagnostics**: `connector.diagnostics()` → `{healthy, latency_ms, quota_remaining,
  authenticated, last_success, last_error, ...}`, aggregated by the dashboard
- **Events**: `connector.executed / failed / rate_limited / auth_required /
  degraded / quota_warning / connected / disconnected` on the Event Fabric

## The one rule that matters

Departments call the **registry**; only `drivers/*` import SDKs. If you find
yourself importing a vendor SDK anywhere above `drivers/`, that logic belongs in
a driver instead.
