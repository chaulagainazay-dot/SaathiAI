# M176–M183 Security Scan

| Scan | Result |
| --- | --- |
| Fixture authority | PASS — no COMPLETE_WITH_FIXTURE_METRICS; incomplete fails closed |
| Live broker | PASS — none |
| Broker credentials | PASS — unsupported |
| Withdrawal | PASS — disabled check only |
| eval/exec/subprocess | PASS — none in tg package |
| Public listener | PASS — 127.0.0.1 only in cert |
| Self-approval | PASS — rejected |
| LIVE_APPROVED | PASS — absent |
| Look-ahead | PASS — M62 engine look_ahead_ok retained |

`LIVE_TRADING_AUTHORIZED = False`
