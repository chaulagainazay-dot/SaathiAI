# MD-1.1 Limitations

- Venue facts are a bounded consistency map, not a live venue catalogue.
- Real provider exchange aliases and genuine Meroshare/TMS/Nepal Share headers
  remain unverified; `SOURCE_SCHEMA_UNVERIFIED` is unchanged.
- Historical NEPSE holiday coverage remains `HOLIDAY_COVERAGE_UNKNOWN` under
  NEPSE-CAL-1.1 policy.
- Existing legacy models retain string fields and are adapted at boundaries;
  broad migration is outside this milestone.
- Explicit US/XNAS and BINANCE strings remain in isolated fixtures, calendars,
  security allowlists, and adapter metadata; each is intentional and not a
  generic omitted-venue default.
