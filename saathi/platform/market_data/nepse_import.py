"""Local operator CLI for owner-supplied official NEPSE EOD import.

    python -m saathi.platform.market_data.nepse_import inspect  <file.csv> [--trading-date YYYY-MM-DD]
    python -m saathi.platform.market_data.nepse_import import   <file.csv> --attest-official [--trading-date YYYY-MM-DD]
    python -m saathi.platform.market_data.nepse_import health

`inspect` is a DRY RUN (no canonical writes). `import` writes canonical md_bars ONLY with
--attest-official (owner attestation: "I manually downloaded this from the official NEPSE
website"). Never asks for password/cookie/token; reads a LOCAL file only.
"""
from __future__ import annotations

import json
import sys

from saathi.platform.market_data.owner_import import import_health, run_import
from saathi.platform.market_data.store import MarketDataStore


def _arg(flag: str, default: str = "") -> str:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    cmd = args[0]
    store = MarketDataStore()
    if cmd == "health":
        print(json.dumps(import_health(store), indent=2, default=str))
        return 0
    if cmd in ("inspect", "import"):
        if len(args) < 2:
            print("error: file path required"); return 2
        path = args[1]
        res = run_import(path, store=store, dry_run=(cmd == "inspect"),
                         attest_official=("--attest-official" in args and cmd == "import"),
                         trading_date=_arg("--trading-date"))
        print(json.dumps(res.as_dict(), indent=2, default=str))
        return 0 if res.status.value in ("DRY_RUN", "IMPORTED", "ALREADY_IMPORTED") else 1
    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
