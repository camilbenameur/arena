# News for the perpetuals league

## 0. Scope

Models need very fresh news, otherwise it is worthless. The design choice is **a calendar and official announcements**, and nothing else.

This relaxes the earlier "no web, no news" rule, but only for **official, structured** news. The open web stays excluded: articles, social networks, search.

## 1. Why these two sources only

A study of news freshness (three searches) established three things:
- **Fast news is out of reach.** The effect of a tweet or a listing announcement plays out in seconds, and part of it is in the price before the announcement. Listing bots respond in under a second. Between a market fact and an order, the arena needs at best 3 min (4 for a council), 5 to 9 min in general: even with an instantaneous source, the models would arrive after everyone else.
- **Elsewhere, almost nobody measures freshness.** Alpha Arena (Nof1), the closest case, gives the models no news at all. TradingAgents, claude-trading-skills and CryptoTrade read their news at analysis time, or once a day. Grok bots search X in 12 to 45 s per query, with no proof of gain.
- **What remains is what plays out within the hour and what is structured.**
  - Macro releases: BTC reacts within the hour to a CPI surprise, and the release dates are known in advance.
  - Platform announcements: incident, maintenance, contract in an abnormal state or withdrawn.

  No free text, hence no injection, and everything stays replayable.

## 2. The path of a news item

1. **The collector** (`arena.perp.collect`, every 5 min) reads, through the usual rate-limited HTTP client:
   - the Kraken status page (Statuspage API): `incidents/unresolved.json`, `scheduled-maintenances/upcoming.json` and `scheduled-maintenances/active.json`;
   - the state of each contract: `futures.kraken.com/derivatives/api/v3/instruments/status`.

   When an open announcement disappears from the lists, it re-reads `incidents.json` or `scheduled-maintenances.json` to learn its final status. An error from these sources is noted in the collector's report, without touching the market data.
2. **The archive.** Each raw response is stored under its hash (`var-perp/data/news/raw/<2>/<sha256>.json`): an unchanged response is stored only once. The normalized items go to `var-perp/data/news/items/<YYYY-MM>.jsonl`, one per **version**: an announcement that changes status yields a new item.
3. **The journal.** At each tick, the watcher (`watcher`) journals every new item as a `news_item`. Only items collected less than 2 h ago are taken: those of a watcher that was stopped for longer are lost. **The journal is authoritative**: a round reads only the `news_item` events journaled at or before its time.
4. **The round data** (`round.json`) freezes a `news` block:
   - the calendar for the next 72 h and the past 6 h;
   - the announcements in progress, and those ended less than 24 h ago, at most 8;
   - the hash of the configuration.

   The block is absent when news is switched off: the data of rounds before 2026-11-15 and its hash do not change.
5. **The snapshot** sent to the models and to the councils gains the `news` block (§5).

## 3. The sources and their filter

**The Kraken status page.** An announcement counts in two cases:
- it affects a **trading** component of the "Kraken Derivatives" group (`derivatives_group_id`): interface, REST API, websocket, FIX. Transfers between accounts and login are excluded: they do not affect a paper portfolio. The "US Derivatives" group is excluded too;
- it is a delisting notice that **cites one of the six contracts** by the full name of its asset (BTC, XBT or Bitcoin, etc.). This is the only case where the body text is read, and only to look for these names.

**From each announcement, only this is kept:** the cleaned title (no control or markup characters, at most 120 characters), the status, the impact, the times and the short link. Never the body.

**The state of each contract** (Kraken Futures `instruments/status`): one item when the state of one of the six contracts changes. The possible states are a price dislocation (`dislocation`, up or down) and extreme volatility, with the initial margin multiplier. The title is written by the code. A first normal reading says nothing; the return to normal yields an item.

**The macro calendar** (`config/macro-calendar.toml`): 42 releases from 2026-11-25 to 2027-06-30, collected on 2026-11-15 from the official calendars, with their times in UTC:
- FOMC decisions: the Fed's page;
- GDP and PCE: the BEA `.ics` file;
- CPI, employment and PPI: the BLS pages.

The BLS refuses automated requests: its dates were read with a web tool and cross-checked across three of its pages. FOMC minutes and press conferences are not published for these dates: they are absent. **The published figure is not provided**: the consensus would be needed to derive a surprise, and no free source gives it. Only the market's reaction shows it.

The calendar ends on 2027-06-30. The watcher raises the alert `perp_news_calendar_ending` once a day starting 30 days before. Extending it requires no code.

## 4. Wake-ups

Two new private-round triggers, which go through the same round quota, the same budget and the same spot-cycle guard as the others:
- **`news`**: a `news_item` marked `wake` was journaled since the portfolio's last round, less than an hour ago. Marked `wake` are:
  - an incident, opened or resolved (the return of trading counts too);
  - a scheduled or in-progress maintenance;
  - a contract in an abnormal state.

  A finished maintenance and the return of a contract to normal do not wake.
- **`calendar`**: a FOMC, CPI, employment or PCE release (`calendar_wake_kinds`) is 3 minutes old (`calendar_wake_after_min`). The 1-minute candles of the reaction are then closed. The wake-up is served by the tick that starts at most 2.5 min before, up to 30 min after, to any portfolio whose last round started before that moment. PPI and GDP are only shown.

When a portfolio already has another trigger (alert, requested wake-up), the news is added to it (`trigger.news`). The 10-minute cadence, in turn, yields to the `news` or `calendar` trigger. Expected delay: 3 to 10 min after the announcement for a single AI, 4 to 12 min for a council.

## 5. What the models see

The snapshot's `news` block:
- `macro_calendar`: `publication`, `type`, `time_utc`, `in_min` (negative: already published) and `remind_me`;
- `kraken_announcements`: `title`, `type` (incident, maintenance, contract withdrawal, contract state), `status`, `impact`, `start_utc`, `end_utc`, `seen_at_utc` and `contracts`;
- `note`: where this data comes from, and the absence of the published figures.

**Instructions:** v8 for the 4 AIs (`arena/perp/prompt/v8.md`), v3 for the councils (`arena/perp/prompt/council/v3/`). They build on v7 and v2, with five changes:
- the two triggers;
- the `news` block in the list of what the model receives;
- a "News" section;
- announcement titles counted as data, never as an instruction;
- "Invent no data" becomes: no news other than those of the block, and nothing the model believes it knows about recent news.

The tools do not change, nor does their number. The v7 and v2 instructions stay in the repository: they are those of the earlier rounds.

## 6. The configuration

`config/perp-news.toml`, hashed together with the calendar. Its hash is in the `news` block of each round's data.
- `enabled = false` removes the news from the snapshot and from the wake-ups; the collector stops collecting it.
- An invalid configuration switches the news off, with the alert `perp_news_config_invalid`. It never switches off the collector, the watcher or the models.

## 7. The site

Done in parallel in `arena/site/`:
- the label of the two triggers;
- a "News" block: the upcoming releases and the Kraken announcements of the last 7 days, in the latest version of each;
- the updated method page.
