"""Perpetual futures league (paper). See docs/ETUDE-AGENTS-TRADERS.md and docs/DECISION-OWNER-agents-traders.md.

This league has its own journal and its own state directory (`var-perp/` by default), isolated from the
spot league. Step 1 only collects public market data: no portfolio, no order, no account, no key.

Code in this package is written in English (decision of 12/11/2026). Units follow `arene.types`:
integers only on the money path; prices of USD-quoted contracts are stored in micro-USD (µUSD).
"""
