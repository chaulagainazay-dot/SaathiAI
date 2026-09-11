# Reproducibility contract

An executable qualification requires, per instrument:

- dataset ID and SHA-256 dataset version;
- canonical instrument ID;
- exact revision snapshot/cutoff and content hash;
- source and data-quality classification;
- strategy version and immutable configuration hash;
- cost/fill versions;
- exact initial and walk-forward trial counts;
- seed 0 and expanding pre-final-test fold policy;
- all segment results, including poor segments.

The runner recomputes the supplied snapshot content hash and fails closed on mismatch.
A correction unavailable at a simulated decision time is excluded. The real run used
dataset version `sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8`,
seed 0, `crypto-spot-v1` costs, `next-observation-open-v1` fills, and
`EXPANDING_PRE_FINAL_TEST` walk-forward.

The exact public result artifact is retained locally as read-only content with SHA-256
`45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40`.
Its path is
`data/research/strategy-crypto-1/sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8/qualification-45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40.json`.

All six final-TEST evaluation keys are now spent. An exact rerun may only be described
as reproducibility; a changed configuration cannot reuse these TEST windows as
independent evidence. The runtime spend guard remains in-memory, so durable journal
persistence must be implemented before long-running paper/shadow use.
