# Arena dashboard: design decisions

The dashboard is served privately on `127.0.0.1:8787` and published as a public version on GitHub Pages (`ops/publish.py`, outbound only: no port is opened on the host).

**"Scoreboard" direction** (mockup A, chosen over B "Night desk"), replacing "Notebook". The earlier direction was criticized as hard to read: scrolling over blocks of text that cannot be read, a home page that does not say enough, a UI that is not user friendly. The result is a sports-style leaderboard that reads at a glance: light background, a single type family (Plex Sans, figures in Plex Mono), **no big headline**: the title is a one-line sentence, and the leaderboard and the chart, side by side, carry the first screen. Design intent: **persuade** for the home page and `councils.html` (the councils page), **operate** for the portfolio pages.
The first-screen question, for a visitor who knows nothing about the subject: what is this (Claude models trading in simulation against benchmarks), who is leading, where to click.

## Structure

| Page | Contents, in order |
|---|---|
| `index.html` (home) | One sentence, then one card per league (councils, solo AIs, spot): what it measures, a small chart, the leader, the runner-up and the non-AI benchmark, a link. Then "How it works" in three points. All three leagues appear on the home page. |
| `councils.html` | Sentence and lead-in, leaderboard and chart, "How a council decides" (3 steps), latest decisions as cards, detailed table, news, collapsed rules. |
| `derivatives.html` (solo AIs) | Same template; the league's former `index.html` address became the home page. |
| `spot.html` | Same template, with the season status below the leaderboard. |
| Portfolio pages | Figures, chart, positions, **decisions**, then pending orders and operations. |

## Components

- **Leaderboard** (`home.scores`): rank (ties at the hundredth of a percent), a swatch in the chart-line color (hatched for a benchmark), name as a link, subtitle, return in large type. The non-AI benchmark comes last, with rank "ref.". An AI that has not bought anything yet says so ("all cash").
- **Decision card** (`render_perp._decision`, sentences in `readable.py`): the time and the trigger, then **what was decided in one jargon-free sentence** ("Preparing to bet on a fall in Solana"), then **why in one sentence**: for a council, the actual count of step A opinions ("7 advisers out of 9 see Solana falling; the devil's advocate attacks...") with one mark per adviser (▲ rise, ▼ fall, ● no opinion, ○ absent: the shape carries the meaning, not only the color); for a solo AI, "In its words", the first sentence of its reasoning of at least 9 words, in quotation marks, with "bp" converted to % (1 bp = 0.01%), never rewritten. The detail (full reasoning, opinions, orders, guardrail, execution) is collapsed behind a link that says what it contains.
- **SIMULATED label** in the header of every page ("SIMULATED · fictitious money", red, bordered), and "Simulation." at the start of the footer. The yellow banner stays removed; "REAL MONEY" would appear if `venue_mode` were no longer paper.

## Decisions

| Topic | Decision | Reason |
|---|---|---|
| Language | French only, French typography (narrow no-break space before `; : ? !`, inside guillemets) applied by `render.typo_fr` | A single French-speaking reader |
| Theme | Light and dark, following `prefers-color-scheme`, tokens in `:root` | Reading in the morning and in the evening |
| Typeface | IBM Plex Sans (text and headings) and Mono (figures), Latin subset, self-hosted (`fonts/`, OFL-1.1, checksums in `SHA256SUMS`). Plex Serif is no longer used (files kept) | Crisp tabular figures, no external resource |
| CSP | `style-src 'self'`, `script-src 'self'`, no `unsafe-inline`; no `style` attribute in the HTML (gauges and bars are SVG with attributes) | The site displays text produced by models |
| Indexing | Public version is **indexed** (`index, follow`, `canonical`, `sitemap.xml`); the private site stays `noindex, nofollow` | The public site is meant to be found |
| Sharing | `og:` and `twitter:` tags (large-image card) on every public page; 1200×630 images `assets/preview.png` and `assets/preview-councils.png` (councils and council pages), diagrams without figures so they do not go stale; sources in `preview-src/` | The share link points to `councils.html` |
| Motion | Hover and focus feedback (150 to 200 ms, `cubic-bezier(0.22, 1, 0.36, 1)`): an underline that draws under leaderboard names, a league card that lifts by 2 px, an arrow that moves forward; no entrance animation, no loop, nothing under `prefers-reduced-motion` | Figures must be readable immediately; the site shows data that changes every 5 min, it is not a showcase |
| Loader, WebGL, shared element, service worker | No | Not relevant for a static data page |
| Chart | uPlot (vendored), one point per cycle, axis as deviation from the start (%); line styles computed once (`render._styles`) and shared by the HTML legend and `chart.js` | Legend readable without JS, by keyboard, with no layout shift |
| Text equivalent of the chart | `aria-label` with the values of the last cycle, HTML legend with values, tables | The chart is never the only source |
| Live prices (derivatives) | `assets/direct.js` reads the public feed `wss://futures.kraken.com/ws/v1` (`ticker` feed, no key) and revalues the published positions at the current mark: return, value, current price, unrealized P&L. Figures underlined with dots, line "Live estimate, Kraken price at HH:MM:SS UTC". Feed silent for 15 s: back to the published figures; reconnection with increasing delay (60 s at most), socket closed when the tab is hidden. The CSP opens `connect-src wss://futures.kraken.com` only on derivatives pages that have positions (`CSP_DIRECT`). The chart stays the journal's ("Last reading") | Prices should be fresh to within a few seconds; the only external resource of the site, read-only, no cookie or key |
| Freshness | `assets/site.js` compares the time of the next cycle with the reader's time ("in 3 h 06", "late") | The page is static; a stopped timer must be visible |
| Model that never decided | "never decided" badge, no rank or cost, alert on its page | A portfolio left in cash "beats" chance, which pays fees: a misleading figure |
| Public version | `build(..., public=True, root_path="/arena/")`: without the operator's "to do" line, with a 404 page; `ops/publish.py` blocks publication if a local path, a token, an e-mail address or an internal document appears | Only the experiment's figures go out; all figures are shown, euros included |
| Signature | The scoreboard next to the chart, at the top of each league, and the advisers' vote (▲▼●) on every council decision | Specific to this project (a league of AIs), readable without knowing the subject |
| Home chart | Labels at the end of each line (value and name, each name in its color), overlapping lines flagged in the subtitle | Direct reading, no legend to decode (OWID) |
| Printing | Navigation and legend hidden, footer warning kept | The simulated status must remain on paper |
| Justifications | Published as soon as the decision is made, collapsed behind the decision card (see Components) | No more blocks of text at first glance; everything stays one click away |
| Model that joined midway | Line that starts at its first cycle (no point at 100 before), entry date under its name and on its page, no rank against chance (computed over the whole period) | Do not compare it with the others over a period when it did not exist |
| Model colors | Haiku rust, Sonnet blue, Opus purple, Fable teal (`--llm3`, 5.4:1 on the light background); benchmarks stay dotted gray | Four distant hues, none close to the green of gains |
| "Simulation" banner | Yellow banner removed; in its place, the "SIMULATED · fictitious money" label in the header of every page and "Simulation." at the start of the footer; "REAL MONEY" if `venue_mode` is no longer paper | The SIMULATED label stays visible everywhere without a garish banner |
| Council league | Page `councils.html` (same journal, same markets as the derivatives; `kind == "council"` classifies), one page per council in `councils/`, "Councils" entry in the navigation, link on the derivatives home. Table: councils (mark "aggressive · leverage ≤ 10x · target ×2") then the 1x basket benchmark for reference. Haiku council ("10 Haiku · Haiku chair", `--council` magenta tint) and Opus council ("10 Haiku · Opus chair", `--council2` gold, 4.9:1 light, 11:1 dark); unknown council: "Council <slug>". Deliberation collapsed per round: step A (real opinions from the journal, never a hard-coded number: 8, then 9 with the Arbitrageur), B the Advocate, C the Chair ("Chair · Opus", the Chair's cost shown separately if it is not Haiku). Opinions published for the last 48 rounds. Method on the league page (`#m-councils`) | A 10x leverage cannot be compared with 2x AIs; only the Chair differs between the two councils |
| News | "News" block on the derivatives and councils homes (`journal.news_item`, latest version of each announcement; macro calendar from `arena.perp.news`, omitted if unreadable): releases in the next 7 days (badge "wakes the AIs 3 min after"), Kraken announcements of the last 7 days (kind, status, range, contracts, https link only). Round triggers "Kraken announcement" and "macro release · after ...", a discreet "... attached" note on the others. Method: `method.html#m-news` | Feeds the engine's wake-up triggers; official, structured sources only |
| Grouped labels | When several lines end at the same value, names that do not fit in the margin become "+N" | No text cut off at the chart edge |
| Stacked cards (mobile) | Only cells with nothing to read ("—") are hidden; "accepted", "rejected" and their reasons stay visible | A risk-control rejection must never disappear on a phone |

## Exceptions to the design-lint scan

- `low-contrast` on the static scan of `var/site/`: false positives, the scan crosses the dark theme's colors with the light background. The scan of rendered pages, light and dark, and axe-core give 0.
- `cramped-padding` on `.table-scroll` (static scan): cells have 11 px of inner padding; the text does not touch the edge.
- `em-dash-overuse` (advisory): these are the empty "—" cells of the tables, not prose.
