"""Perpetual futures league (paper). See docs/SPEC-MVP.md.

This league has its own journal and its own state directory (`var-perp/` by default), isolated from the
spot league. Step 1 only collects public market data: no portfolio, no order, no account, no key.

Units follow `arena.types`:
integers only on the money path; prices of USD-quoted contracts are stored in micro-USD (µUSD).
"""
