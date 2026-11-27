"""All 22 logged trials. Each returns target weights decided at close t (before the engine's t+1 execution lag)."""
import os
import numpy as np, pandas as pd
from lib import *

def term_spread(idx):
    return (load("TNX","close") - load("IRX","close")).reindex(load("SPY").index).ffill().reindex(idx)

def xs_mom(px, k, abs_filter):
    r = px.shift(21) / px.shift(252) - 1            # 12-1 month momentum
    rank = r.rank(axis=1, ascending=False)
    pick = ((rank <= k) & r.notna()).astype(float)
    if abs_filter: pick = pick * (r > 0)
    return pick / k

def tom_hold(idx):
    s = pd.Series(idx, index=idx); ym = idx.to_period("M")
    pos = pd.Series(range(len(idx)), index=idx).groupby(ym).cumcount()
    last = pd.Series(idx.to_period("M")[:-1] != idx.to_period("M")[1:], index=idx[:-1]).reindex(idx).fillna(False)
    return ((pos < 3) | last).astype(float)    # first 3 trading days + last trading day of the month (return days)

def halloween_hold(idx):
    m = idx.month; return pd.Series(((m >= 11) | (m <= 4)).astype(float), index=idx)

def only(px, col, hold):
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    w[col] = hold.shift(-2).fillna(0)   # calendar known in advance: signal at t covers return day t+2
    return w

CORE = ["SPY","TLT","IEF","GLD","DBC"]
def build(tid, px_all):
    """px_all: ETFs (+BTC) price panel, already truncated to the evaluation horizon."""
    etf = px_all[[c for c in px_all.columns if c != "BTC-USD"]]
    withb = px_all
    idx = px_all.index
    if tid == "A1": return size_ew(sig_tsmom(etf))
    if tid == "A2": return size_ew(sig_sma(etf))
    if tid == "A3": return size_ivn(sig_tsmom(etf), etf)
    if tid == "A4": return size_ivn(sig_sma(etf), etf)
    if tid == "A5": return size_vt(sig_tsmom(etf), etf)
    if tid == "A6": return size_vt(sig_ensemble(etf), etf)
    if tid == "A7": return size_ivn(sig_sma(withb), withb)
    if tid == "A8": return size_ivn(sig_ensemble(etf), etf)
    if tid == "B1": return xs_mom(etf, 3, False)
    if tid == "B2": return xs_mom(etf, 3, True)
    if tid == "B3": return xs_mom(etf, 4, True)
    if tid == "B4":
        r = etf / etf.shift(252) - 1
        w = pd.DataFrame(0.0, index=idx, columns=etf.columns)
        eq = r[["SPY","EFA"]].fillna(-9).idxmax(axis=1); up = r[["SPY","EFA"]].max(axis=1) > 0
        for c in ["SPY","EFA"]: w[c] = ((eq == c) & up).astype(float)
        w["IEF"] = (~up).astype(float)
        return w.where(r["SPY"].notna(), 0)
    if tid == "B5": return xs_mom(withb, 3, True)
    if tid == "C1": return size_ivn(etf.notna().astype(float).where(vol(etf).notna()), etf)
    if tid == "C2": return size_vt_port(size_ivn(etf.notna().astype(float).where(vol(etf).notna()), etf), etf)
    if tid == "C3":
        c = etf[CORE]; return size_ivn(c.notna().astype(float).where(vol(c).notna()), c).reindex(columns=etf.columns, fill_value=0)
    if tid == "C4": return size_ivn(withb.notna().astype(float).where(vol(withb).notna()), withb)
    ts = term_spread(idx)
    if tid == "D1": return only(etf, "TLT", (ts > 1.0).astype(float).shift(2)).shift(-2) if False else _carry(etf, "TLT", ts > 1.0)
    if tid == "D2": return _carry(etf, "IEF", ts > 0)
    if tid == "D3":
        w = pd.DataFrame(0.0, index=idx, columns=etf.columns); steep = (ts > 1.0).fillna(False)
        w["TLT"] = steep.astype(float); w["IEF"] = (~steep).astype(float); return w
    if tid == "E1": return only(etf, "SPY", tom_hold(idx))
    if tid == "E2": return only(etf, "SPY", halloween_hold(idx))
    raise KeyError(tid)

def _carry(etf, col, cond):
    w = pd.DataFrame(0.0, index=etf.index, columns=etf.columns); w[col] = cond.fillna(False).astype(float); return w

TRIALS = {
 "A1": ("trend","TSMOM 12m sign, 1/N per asset, rest cash"),
 "A2": ("trend","price > 10-month SMA (210d), 1/N per asset, rest cash (Faber GTAA)"),
 "A3": ("trend","TSMOM 12m sign, inverse-vol weights normalised to 100% invested"),
 "A4": ("trend","10m SMA, inverse-vol weights normalised to 100% invested"),
 "A5": ("trend","TSMOM 12m, each asset sized to 10% vol / N (MOP), gross <= 1x"),
 "A6": ("trend","1/3/6/12m sign ensemble, 10% vol per asset / N, gross <= 1x"),
 "A7": ("trend","A4 + BTC in the universe"),
 "A8": ("trend","1/3/6/12m ensemble, inverse-vol normalised"),
 "B1": ("xsmom","cross-sectional 12-1m momentum, top 3 of 11, 1/3 each, no absolute filter"),
 "B2": ("dual","dual momentum: top 3 of 11 by 12-1m, only if 12-1m > 0, else cash"),
 "B3": ("dual","dual momentum: top 4 of 11, absolute filter"),
 "B4": ("dual","GEM-like: best of SPY/EFA if 12m>0 else IEF"),
 "B5": ("dual","B2 + BTC in the universe"),
 "C1": ("riskparity","inverse 60d-vol across 11 ETFs, 100% invested"),
 "C2": ("riskparity","C1 scaled to 10% portfolio vol, gross <= 1x"),
 "C3": ("riskparity","inverse-vol on core 5 (SPY,TLT,IEF,GLD,DBC), 100% invested"),
 "C4": ("riskparity","C1 + BTC"),
 "D1": ("carry","TLT when 10y-3m term spread > 1 pt, else cash"),
 "D2": ("carry","IEF when term spread > 0, else cash"),
 "D3": ("carry","TLT when spread > 1 pt, else IEF (always bonds)"),
 "E1": ("seasonal","SPY on last + first 3 trading days of the month, else cash"),
 "E2": ("seasonal","SPY Nov-Apr (Halloween), else cash"),
}
FAMILY_OF = {k: v[0] for k, v in TRIALS.items()}
FAMILY_GROUP = {"trend":"trend","xsmom":"momentum","dual":"momentum","riskparity":"riskparity","carry":"carry","seasonal":"seasonal"}
