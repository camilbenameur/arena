# Deploying axis 10: Trend at 1x, Wick Hunter retired, carry added

Branch `lead/apply-axis-10` (worktree `~/dev/arena-wt-axis10`), one or more commits, not pushed, services untouched. The live units run directly from `~/dev/arena` (`%h/arena`, its `.venv`), so merging changes the code the next oneshot loads. Follow the order: **stop what plays, merge, retire, restart**.

## What the change does at run time

| Item | Before | After |
|---|---|---|
| `council-perp:trend`, `benchmark-perp:trend-engine` (2x) | playing | retired by `portfolio_retired` (flattened at market, curves dotted) |
| `council-perp:trend-1x`, `benchmark-perp:trend-engine-1x` | none | opened by the watcher at the first 4-hour bar close after the restart, EUR 1,000 each |
| `robot-perp:hunter`, `benchmark-perp:hunter-5min` | played by `arena-perp-hunter.service` | retired; config `enabled = false`; unit stopped and disabled |
| `benchmark-perp:carry` | none | opened at the first watcher tick, its pairs entered at the first scheduled (4-hour) round |

`config/council-league.toml` now lists only `perp-council-trend-1x.toml`. Nothing frozen by Season 1 is touched (`arena/season.py`: `arena/perp/`, `arena/site/` and the perp configs are outside the freeze).

## Before you start

```bash
cd ~/dev/arena && git status --short        # must be clean on main
systemctl --user list-timers 'arena-*' --no-pager
journalctl --user -u arena-perp-watcher -n 20 --no-pager   # last tick healthy
```

Keep `arena-perp-collect.timer` running: the retirement needs a market view younger than 15 minutes to flatten the positions (it fails closed and writes nothing otherwise).

## Steps

1. **Pause the players** (the retirement CLI also takes the watcher lock and waits up to 20 minutes for a running tick, but pausing avoids a tick running new code on half-retired portfolios):
   ```bash
   systemctl --user stop arena-perp-watcher.timer
   systemctl --user stop arena-perp-hunter.service
   systemctl --user disable arena-perp-hunter.service   # it must not come back at boot; the unit file stays in ops/systemd
   ```
   Let a running `arena-perp-watcher.service` finish (`systemctl --user is-active arena-perp-watcher.service`).
2. **Merge** (from `~/dev/arena`, the units' checkout):
   ```bash
   git merge --no-ff lead/apply-axis-10
   .venv/bin/python -m pytest -q tests/test_axis10.py tests/test_trend_council.py tests/test_hunter.py   # quick check on the merged tree
   ```
   No new dependency, no `uv sync` needed.
3. **Retire the four portfolios** (`arena.perp.retired`; each flattens at market, ends the pending orders, journals `portfolio_retired` with the reason; exit 3 means "refused, nothing written", typically no fresh quote: wait for the next collector run and repeat). The robot first, because its two portfolios hold the largest leverage:
   ```bash
   cd ~/dev/arena
   R=".venv/bin/python -m arena.perp.retired"
   $R --portfolio robot-perp:hunter --reason "axis 10: frozen wick rule positive in 0 of 6 years on 2020-2025 (-34.7 bp per trade, 3,664 trades); edge specific to the 2025-26 year" --note "owner approved 2026-11-28"
   $R --portfolio benchmark-perp:hunter-5min --reason "axis 10: witness of the retired Wick Hunter" --note "owner approved 2026-11-28"
   $R --portfolio council-perp:trend --reason "axis 10: frozen trend engine at 2x lost 71.6% on 2020-2025 (max drawdown -92%); replaced by council-perp:trend-1x (axis 11: 1x holds on 2017-2019)" --note "owner approved 2026-11-28"
   $R --portfolio benchmark-perp:trend-engine --reason "axis 10: shadow of the retired 2x Trend Council; replaced by benchmark-perp:trend-engine-1x" --note "owner approved 2026-11-28"
   ```
   Reasons are cut at 200 characters by the journal; the ones above fit. The old portfolios' history is untouched, they only gain an end.
4. **Restart the watcher** (the new council, its shadow and the carry open by themselves):
   ```bash
   systemctl --user start arena-perp-watcher.timer
   ```
   Do not restart the hunter. `arena-perp-collect.timer`, `arena-publish.timer`, `arena-site.service` stay as they are. If you prefer a visible first tick: `systemctl --user start arena-perp-watcher.service`.
5. **Rebuild the site** (otherwise the 30-minute publish timer does it): `.venv/bin/arena build-site`.

Timing: `benchmark-perp:carry` is opened at the first tick, its four legs are entered at the first scheduled round after the restart (02:00, 06:00, ... UTC, 4-hourly), and the trend council opens at the first 4-hour bar close (00:00, 04:00, ... UTC, the watcher's first tick after HH:00, not during the spot cycle at HH:00 to HH:05).

## Verify

In the journal (`var-perp/journal/events.jsonl`; the chain must verify):
```bash
cd ~/dev/arena
.venv/bin/python - <<'PY'
from arena.journal import Journal
from collections import Counter
j = Journal(__import__("pathlib").Path("var-perp/journal/events.jsonl"))
ev = j.events()
for e in ev:
    if e["type"] == "portfolio_retired":
        print("retired", e["payload"]["portfolio"], e["payload"]["reason"][:70])
    if e["type"] == "portfolio_opened" and e["payload"]["portfolio"].endswith(("-1x", "carry")):
        print("opened ", e["payload"]["portfolio"], e["payload"]["capital_ueur"])
print(Counter(e["type"] for e in ev if e["type"] in ("spot_fill", "carry_plan", "trend_engine_target")))
PY
```
Expected: four `retired` lines, `opened` for `council-perp:trend-1x`, `benchmark-perp:trend-engine-1x` (after the first bar close) and `benchmark-perp:carry`; a `carry_plan` event (reason `entry`, `spot_price: kraken_index`) followed by 2 `spot_fill` and 2 short `perp_fill` for the carry; `trend_engine_target` events with `"scale": "1.0"`. Also: `journalctl --user -u arena-perp-watcher -n 50` shows no `carry` or `controls` problem, and `systemctl --user is-active arena-perp-hunter` is `inactive`.

On the site (`http://127.0.0.1:8787`, then the published one after the next publish):
- Councils league: "Trend Council 1x" live (solid), "Trend Council 2x" and "Benchmark engine only 2x" with the archived tag and dotted curves stopping at the retirement; the "Engine only 1x" gray ribbon under the 1x council.
- Solo AIs league: "Wick Hunter" and "Wick Hunter at a 5-min pace" archived and dotted; "Benchmark carry" live, with the badge "benchmark · a cash substitute: earns the funding paid by leveraged longs, no bet on price", the note about the valuation-only spot leg, a "Spot legs" table (BTC and ETH) and its funding line showing amounts received.
- The carry's net return stays within a fraction of a percent of 0 (an entry cost of about 0.6% of EUR 1,000, then funding accruing); a price move of the coins must not move it.

## Rollback

Retirements are journal events: append-only and permanent. A retired portfolio never plays again and there is no un-retire; that is by design.
- **Before step 3** (merged, nothing retired): `git revert -m 1 <merge commit>` in `~/dev/arena`, restart the timers and `systemctl --user enable --now arena-perp-hunter.service`. Nothing was changed in the journal.
- **After step 3**: reverting the code does not bring the 2x council or the hunter back. To play them again you would open new portfolios (new names, new config files); the retired ones stay as records. To stop the new ones instead: `python -m arena.perp.retired --portfolio council-perp:trend-1x ...` (and the shadow) with the reason, and remove `perp-council-trend-1x.toml` from `config/council-league.toml`.
- **The carry** cannot be retired by the CLI (the benchmarks stay in the league). To remove it from the site and the watcher, revert the code: the old code replays the journal without difficulty (it ignores the `spot_fill` and `carry_plan` event types), but the carry's perp shorts then stay open in the journal with no one managing them; flatten them first with a one-off `sim.flatten("benchmark-perp:carry", ...)` or leave the code in place and set the watcher not to call `_carry`.
- Hunter: re-enable with `enabled = true` in `config/perp-hunter.toml` and `systemctl --user enable --now arena-perp-hunter.service` only makes sense with new portfolio names, since its portfolios are retired (the process would find them halted and trade nothing).

## Decisions taken in the code (so the owner can overrule them)

- The 1x council has its own policy file, a copy of the 2x one (same numbers, comments updated), so the retired council's journaled policy hash still matches its file.
- `expected_move_bp` stays at 247 (inherited, noted in the config).
- Retired portfolios keep their ids; the site displays them as "Trend Council 2x", "Benchmark engine only 2x".
- The carry targets a fixed EUR 250 per leg (a quarter of the capital), not a share of the equity; the band is checked at the scheduled rounds (every 4 hours), not every 5 minutes.
- Margin and close-out checks of the carry ignore the spot leg's value (pessimistic): the spot cash is out of the collateral, so the shorts are margined against about EUR 500.
