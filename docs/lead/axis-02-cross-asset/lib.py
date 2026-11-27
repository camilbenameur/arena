"""Cross-asset daily backtest engine. Data lives outside git (DATA dir)."""
import os
import numpy as np, pandas as pd
from math import sqrt
from scipy import stats  # noqa (only for DSR); falls back if missing
DATA = os.path.expanduser("~/dev/_arena-data/axis-02/")
DESIGN_END = "2015-12-31"
CONTROL_START = "2016-01-01"
COST = 0.0010          # 10 bp per side per trade
BAND = 0.02            # no-trade band: a weight is only changed if it moves > 2 pp from the held weight
START = "2007-03-01"   # first date all ETFs but BTC exist
ETFS = ["SPY","EFA","EEM","TLT","IEF","GLD","DBC","VNQ","FXE","FXY","UUP"]
CLASS = dict(SPY="eq",EFA="eq",EEM="eq",VNQ="re",TLT="bond",IEF="bond",GLD="com",DBC="com",FXE="fx",FXY="fx",UUP="fx",**{"BTC-USD":"crypto"})

def load(sym, col="adj"):
    d = pd.read_csv(DATA + sym.replace("^","") + ".csv", index_col=0, parse_dates=True)
    return d[col]

def panel(with_btc=False):
    cal = load("SPY").index
    cols = ETFS + (["BTC-USD"] if with_btc else [])
    px = pd.concat({s: load(s) for s in cols}, axis=1).reindex(cal)
    px = px.ffill(limit=3)
    px = px[px.index >= START]
    return px

def cash_rate():
    irx = load("IRX", "close").reindex(load("SPY").index).ffill() / 100 / 252
    return irx

def refs():
    cal = load("SPY").index
    acwi = load("ACWI").reindex(cal).pct_change()
    ief = load("IEF").reindex(cal).pct_change()
    spy = load("SPY").reindex(cal).pct_change()
    return {"BH_ACWI": acwi, "BH_SPY": spy, "60_40_ACWI_IEF": 0.6*acwi+0.4*ief}   # 60/40 rebalanced daily, cost-free (favours the reference)

def apply_band(w, band=BAND):
    W = w.values; H = np.zeros_like(W); h = np.zeros(W.shape[1])
    for t in range(len(W)):
        tgt = np.nan_to_num(W[t])
        mv = np.abs(tgt - h)
        # a weight going to exactly 0 or from 0 always trades; otherwise only if it moved > band
        chg = (mv > band) | ((tgt == 0) & (h != 0)) | ((h == 0) & (tgt > band/2 ))
        h = np.where(chg, tgt, h); H[t] = h
    return pd.DataFrame(H, index=w.index, columns=w.columns)

def backtest(w_target, px, end=None, start=None, lev=1.0, band=BAND, cost=COST):
    """w_target[t]: weights decided at close t. Trade at close t+1, earn return of t+2 onward."""
    r = px.pct_change()
    w = apply_band(w_target.reindex(px.index).fillna(0), band)
    if lev != 1.0: w = w * lev
    held = w.shift(2).fillna(0)             # position earning r[d]
    traded = (w.shift(1).fillna(0) - w.shift(2).fillna(0))  # trade executed at close d
    cr = cash_rate().reindex(px.index).fillna(0)
    gross = held.sum(axis=1)
    cashw = 1 - gross                        # negative if leveraged: borrow at cash rate + 0.5%/yr
    cash_ret = np.where(cashw >= 0, cashw * cr, cashw * (cr + 0.005/252))
    ret = (held * r.fillna(0)).sum(axis=1) + cash_ret - cost * traded.abs().sum(axis=1)
    out = pd.DataFrame({"ret": ret, "gross": gross, "turn": traded.abs().sum(axis=1), "ntrades": (traded.abs() > 1e-9).sum(axis=1)})
    if start: out = out[out.index >= start]
    if end: out = out[out.index <= end]
    return out

def metrics(ret, rf=None, turn=None, ntr=None):
    ret = ret.dropna()
    if rf is None: rf = cash_rate().reindex(ret.index).fillna(0)
    rf = rf.reindex(ret.index).fillna(0)
    n = len(ret); yrs = n / 252
    eq = (1 + ret).cumprod()
    cagr = eq.iloc[-1] ** (1/yrs) - 1
    vol = ret.std() * sqrt(252)
    ex = ret - rf
    sh = ex.mean() / ret.std() * sqrt(252) if ret.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    yr = (1 + ret).groupby(ret.index.year).prod() - 1
    m = dict(CAGR=cagr, vol=vol, Sharpe=sh, maxDD=dd, worst_year=yr.min(), pos_years=(yr > 0).mean(), total=eq.iloc[-1]-1, years=yrs,
             skew=stats.skew(ret), kurt=stats.kurtosis(ret, fisher=False))
    if turn is not None: m["turnover_per_yr"] = turn.reindex(ret.index).sum() / yrs
    if ntr is not None: m["trades_per_yr"] = ntr.reindex(ret.index).sum() / yrs
    return m

def deflated_sharpe(sr_ann, n_obs, skew, kurt, n_trials, trial_srs_ann):
    """Bailey & Lopez de Prado DSR (probability that true SR>0 after selection among n_trials). Uses daily SR."""
    from scipy.stats import norm
    sr = sr_ann / sqrt(252)
    v = np.var(np.array(trial_srs_ann) / sqrt(252), ddof=1) if len(trial_srs_ann) > 1 else 0.0
    g = 0.5772156649
    sr0 = sqrt(v) * ((1 - g) * norm.ppf(1 - 1/n_trials) + g * norm.ppf(1 - 1/(n_trials*np.e)))
    den = sqrt(1 - skew*sr + (kurt-1)/4 * sr**2)
    return float(norm.cdf((sr - sr0) * sqrt(n_obs - 1) / den)), sr0 * sqrt(252)

# ---------------- signals / sizing -----------------
def vol(px, n=60): return px.pct_change().rolling(n).std() * sqrt(252)

def sig_tsmom(px, lb=252): return (px / px.shift(lb) - 1 > 0).astype(float).where(px.shift(lb).notna())
def sig_sma(px, n=210): return (px > px.rolling(n).mean()).astype(float).where(px.rolling(n).mean().notna())
def sig_ensemble(px): # average of 1,3,6,12 month sign signals in [0,1]
    return sum(sig_tsmom(px, k) for k in (21, 63, 126, 252)) / 4

def size_ew(sig, n_total=None):
    """1/N of the full universe per asset on signal; the remainder stays in cash."""
    n = n_total or sig.shape[1]
    return sig.fillna(0) / n

def size_ivn(sig, px):
    """Inverse-vol weights among selected assets, normalised to 100% gross; cash if none."""
    iv = (1 / vol(px)).where(sig.fillna(0) > 0, 0) * sig.fillna(0)
    return iv.div(iv.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

def size_vt(sig, px, target=0.10, cap=1.0):
    """Moskowitz-Ooi-Pedersen style: each asset sized to `target` vol, averaged over the whole universe; gross capped at `cap`."""
    n = px.shape[1]
    w = (sig.fillna(0) * (target / vol(px)).clip(upper=3)) / n
    g = w.sum(axis=1)
    return w.div(np.maximum(g / cap, 1), axis=0).fillna(0)

def size_vt_port(w, px, target=0.10, cap=1.0, n=60):
    """Scale a weight matrix so that its trailing realised portfolio vol hits target; cap gross at cap."""
    rets = (w.shift(1).fillna(0) * px.pct_change().fillna(0)).sum(axis=1)  # proxy of exposure return
    pv = rets.rolling(n).std() * sqrt(252)
    k = (target / pv).clip(upper=cap / w.sum(axis=1).replace(0, np.nan)).replace([np.inf], np.nan)
    return w.mul(k, axis=0).fillna(0)
