# LAN testing policy — SaathiOS private alpha

**Status: design only. Nothing in this document is implemented.**

```text
LAN_ACCESS_ENABLED=false
DEFAULT_BIND_ADDRESS=127.0.0.1
```

Both the backend (`saathi/config.py:96`, `SAATHI_HOST` defaulting to `127.0.0.1`)
and the frontend (`saathi-os/package.json`, `next dev`/`next start` with
`-H 127.0.0.1`) bind loopback only. That is the shipped default and this
document does not change it.

## Why loopback is the default

The private-alpha contract is local-first, offline-first, invite-only, and
labelled `SINGLE_HOST_LOCAL_DATA`. The product's own health check agrees: any
node or python listener bound to `*:` or `0.0.0.0` is reported as
`public_listener_regression` by `saathi/platform/private_alpha/prepare.py`, and
`saathi/platform/private_alpha/certification.py` turns that flag into a FAIL in
the private-alpha certification gate.

Before the loopback repair, `next start` inherited the framework default and
published the UI on every interface. On a café, hotel, airport or shared-office
network that exposes the sign-in page — and every authenticated surface behind
it — to anyone on the same subnet. Authentication still stands in front of it,
but a private-alpha build with no rate-limit hardening on every surface should
not be presenting an attack surface to strangers at all.

## Why someone would still want LAN access

Testing SaathiOS on a phone or tablet, over the same Wi-Fi, without a tunnel.
That is a legitimate need. It is also a deliberate exposure decision, and it
should be made explicitly rather than inherited from a framework default.

## Required design if this is ever built

Anything short of all of the following is not acceptable for this product.

1. **Disabled by default.** No environment variable, no config file key, and no
   edit to the default scripts turns it on.
2. **Explicit command-line flag.** Opt-in has to be typed at the moment of use:

   ```text
   npm run start:lan -- --confirm-trusted-network
   ```

   Without `--confirm-trusted-network` the command must refuse and exit non-zero.
3. **Trusted-network warning and owner confirmation.** Print the exact addresses
   that will become reachable, name the current SSID or interface, and require an
   interactive confirmation. Never auto-confirm from an environment variable.
4. **Authenticated access only.** No route may become reachable that is not
   already behind the platform session gate. LAN mode must not relax
   authentication, session validation, RBAC or workspace isolation in any way.
5. **Host allowlist.** Bind to one specific interface address, never `0.0.0.0`
   and never `::`. The operator names the interface.
6. **Optional CIDR allowlist.** Reject connections whose peer address falls
   outside an operator-supplied private range (e.g. `192.168.1.0/24`). Refuse to
   accept a public CIDR at all.
7. **Visible banner.** A persistent, non-dismissable `LAN TESTING ENABLED`
   banner in the UI for the entire session, naming the bound address.
8. **No public internet exposure.** Refuse to start if the chosen address is not
   in a private range (RFC1918 / RFC4193 / link-local). No tunnel, no port
   forward, no reverse proxy is provided or documented.
9. **Automatic expiry.** A hard time limit, defaulting to something short (30
   minutes). On expiry the listener closes and the process either exits or
   rebinds to loopback. No indefinite LAN session.
10. **Audit record.** Write a platform audit entry on enable and on expiry,
    capturing who confirmed, the bound address, the CIDR allowlist and the
    expiry time.
11. **Clear return to loopback.** A documented single command, and the plain
    statement that restarting normally (`npm start`) already returns to
    loopback-only.

## Verification required before shipping it

- `lsof -nP -iTCP:3000 -sTCP:LISTEN` shows the specific private address, never
  `*:3000`, `0.0.0.0:3000` or `[::]:3000`.
- `test_doctor_no_public_saathi_listeners` still passes — meaning the check is
  either genuinely satisfied or has an explicit, reviewed LAN-mode exemption
  that cannot apply outside a confirmed LAN session.
- The private-alpha certification gate result is recorded for the LAN session.
- Expiry is proven by test, not by inspection.
- Refusing without `--confirm-trusted-network` is proven by test.
- Refusing a public CIDR is proven by test.

## Current recommendation

Do not build this for private alpha. If you need SaathiOS on your phone today,
prefer an SSH tunnel from the phone's tethered host, or accept that phone
testing happens on the machine running the app. Neither requires a listener on
the LAN.

If it is built later, it belongs in its own change with its own review — not
folded into an unrelated repair.
