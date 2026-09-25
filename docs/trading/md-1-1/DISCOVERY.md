# MD-1.1 Discovery

Starting HEAD: `3c1d7d9d3ca050356ef5f8c1ae0cbaabdef7ec8c`.

The audit found concrete `XNAS` defaults in `MdRegisterBody`,
`DatasetRegistry.register`, OHLCV normalization, and `CalendarEngine.check_bars`.
Canonical MD-1 events already carried `venue`; NEPSE instruments already carried
`NEPSE:<SYMBOL>`. Historical import had explicit NEPSE adapter overrides but
generic local-file imports could retain US defaults when `market=NEPSE`.

Existing explicit US/XNAS synthetic fixtures are legitimate and remain explicit.
No execution, ledger, approval, guardian, construction, or risk path was changed.
