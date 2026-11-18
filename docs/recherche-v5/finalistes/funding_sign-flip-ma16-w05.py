"""Funding famille: portage/foule par contrat. Pour chaque contrat, funding horaire lissé (moyenne sur 16 heures, en pb).
Short quand la moyenne dépasse +0,05 pb, long quand elle passe sous -0,05 pb, sinon on garde la position
(bascule sans phase à plat). Poids 0.5 par contrat (levier brut max 0.5x6). Décision à l'heure du funding, avec le seul
funding déjà appliqué (causal). Pas de stop (les stops ont fait perdre en conception)."""
import numpy as np

MA_H = 16
HI_BP = 0.05
W = 0.5
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
