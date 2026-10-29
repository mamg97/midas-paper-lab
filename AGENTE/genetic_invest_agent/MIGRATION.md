# Original genetic paper campaign

This is the original genetic optimizer, separate from `paper_demo`. All capital,
positions, trades and valuations here are simulated. There is no broker connection.
No private Git history, credentials, personal notifications, charts or unrelated
projects are imported. `migration_manifest.json` is the explicit source allowlist
and records source blob identifiers and SHA-256 fingerprints.

The legacy cohort, the forward cohort interrupted on 2026-10-07 and the independent
cohort starting on 2026-10-12 remain distinct. The first two files are immutable;
the active diary preserves every original valuation and trade. Missing sessions
must not be backfilled or capital reset. The existing IS/OOS procedure, dynamic
windows, 60 agents, 35 generations, universe CSV, commissions, next-open execution
and slippage remain unchanged. Same-close historical backtests retain their limits;
this migration does not establish profitability, point-in-time universe membership
or independence of daily model selection.

Only personal notifications are removed and optional SVG rendering is disabled.
Genetic search and market data are not cached because stale observations or RNG
reuse could change canonical results. Dependency installation uses the pip cache.

`genetic_sp500.yml` uses standard public Ubuntu runners. `verify` runs tests;
`training_check` performs full IS/OOS evolution without modifying any diary;
`publish_only` idempotently republishes the three existing equity summaries;
`trade` processes a genuinely due session before its next open. The UTC schedule
is 00:07 and 03:07 Tuesday–Saturday, after the preceding US market close. A session
already present skips training, including the backup attempt. Git publication is
restricted to the active simulated diary, bot-authored and never force-pushed.

Schedules remain gated by `GENETIC_PUBLIC_ACTIVE=true` until the handover is
verified. A separate private per-run interlock must first defer to an active public
run or an already published public session. Before a manual migration trial, check
that the private workflow has no active writer and that all source hashes still
match. After a genuine public paper-session commit and confirmed private ingest,
disable the private schedule, enable public schedules, and verify the next natural
run. A green test, read-only training, dispatch or republish alone is not evidence
of prospective continuity. GitHub identity/history can still link the pseudonym
to earlier public metadata; no anonymity guarantee is made.
