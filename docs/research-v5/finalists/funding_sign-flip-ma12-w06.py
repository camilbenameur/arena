"""Funding family: carry/crowd per contract. For each contract, smoothed hourly funding (12-hour mean, in bp).
Short when the mean rises above +0.05 bp, long when it falls below -0.05 bp, otherwise keep the position
(flip with no flat phase). Weight 0.6 per contract (max gross leverage 0.6x6). Decision at the funding hour, using only the
funding already applied (causal). No stop (stops lost money in the design phase)."""
import numpy as np

MA_H = 12
HI_BP = 0.05
W = 0.6
STOP_PCT = None


def targets(d):
    idx = np.where((d.funding != 0).any(axis=1))[0]
    F = d.funding[idx] * 1e4
    k = F.shape[1]
    nh = len(idx)
    cs = np.cumsum(np.vstack([np.zeros((1, k)), F]), axis=0)
    ma = np.full((nh, k), np.nan)
    if nh >= MA_H:
        ma[MA_H - 1:] = (cs[MA_H:] - cs[:-MA_H]) / MA_H
    out = np.full((d.n, k), np.nan)
    cur = np.zeros(k)
    prev = np.zeros(k)
    for t in range(nh):
        x = ma[t]
        cur = np.where(x > HI_BP, -1.0, np.where(x < -HI_BP, 1.0, cur))
        w = cur * W
        if np.any(w != prev):
            out[idx[t]] = w
            prev = w.copy()
    return out
