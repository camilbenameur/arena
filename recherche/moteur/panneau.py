"""Panneau de données du moteur : tableaux numpy alignés sur une grille de jours UTC.

Le panneau est ce que le moteur découpe en messages `Jour`. Il se construit depuis `Donnees` (chargeur) ou
depuis des séries synthétiques (`synthetique`, utilisées par les tests et par le test de causalité C9).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from recherche.moteur.contrat import HEURES, N_COLONNES

JOUR_S = 86400
_COLS = ["open", "high", "low", "close", "volume", "taker_buy_base"]


@dataclass(frozen=True)
class Panneau:
    symboles: tuple[str, ...]
    jours: np.ndarray  # (T,) int64, ouverture du jour en secondes UTC
    spot_1d: np.ndarray  # (T, N, 6)
    spot_1h: np.ndarray | None  # (T, N, 24, 6)
    perp_1h: np.ndarray | None  # (T, N, 24, 6)
    eligibles: np.ndarray  # (T, N) bool
    eligibles_perp: np.ndarray | None  # (T, N) bool
    funding_idx: tuple  # T tableaux int64 : paire de chaque échéance du jour
    funding_taux: tuple  # T tableaux float64
    funding_ts: tuple  # T tableaux int64 : fundingTime (secondes)

    @property
    def n_jours(self) -> int:
        return len(self.jours)

    @property
    def n_paires(self) -> int:
        return len(self.symboles)

    def _remplacer(self, **kw) -> Panneau:
        return replace(self, **kw)

    def permuter(self, perm: np.ndarray) -> Panneau:
        """Colonne k du résultat = colonne `perm[k]` de l'original (les poids se rendent par `inv`)."""
        perm = np.asarray(perm)
        inv = np.empty_like(perm)
        inv[perm] = np.arange(len(perm))
        fi = tuple(inv[a] if len(a) else a for a in self.funding_idx)
        return self._remplacer(
            symboles=tuple(self.symboles[p] for p in perm),
            spot_1d=self.spot_1d[:, perm],
            spot_1h=None if self.spot_1h is None else self.spot_1h[:, perm],
            perp_1h=None if self.perp_1h is None else self.perp_1h[:, perm],
            eligibles=self.eligibles[:, perm],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[:, perm],
            funding_idx=fi)

    def sous_univers(self, symboles: list[str] | tuple[str, ...]) -> Panneau:
        pos = {s: k for k, s in enumerate(self.symboles)}
        cols = np.array([pos[s] for s in symboles])
        nouv = np.full(self.n_paires, -1, dtype=np.int64)
        nouv[cols] = np.arange(len(cols))
        fi, ft, fs = [], [], []
        for a, b, c in zip(self.funding_idx, self.funding_taux, self.funding_ts, strict=True):
            garde = nouv[a] >= 0 if len(a) else np.zeros(0, dtype=bool)
            fi.append(nouv[a][garde])
            ft.append(b[garde])
            fs.append(c[garde])
        # jours sans aucune paire cotée au début : on les retire (le flux commence à la première cotation)
        deb = int(np.argmax(self.eligibles[:, cols].any(axis=1)))
        sl = slice(deb, None)
        return Panneau(
            symboles=tuple(symboles), jours=self.jours[sl], spot_1d=self.spot_1d[sl][:, cols],
            spot_1h=None if self.spot_1h is None else self.spot_1h[sl][:, cols],
            perp_1h=None if self.perp_1h is None else self.perp_1h[sl][:, cols],
            eligibles=self.eligibles[sl][:, cols],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[sl][:, cols],
            funding_idx=tuple(fi[sl]), funding_taux=tuple(ft[sl]), funding_ts=tuple(fs[sl]))

    def tronquer(self, n_jours: int) -> Panneau:
        sl = slice(0, n_jours)
        return self._remplacer(
            jours=self.jours[sl], spot_1d=self.spot_1d[sl],
            spot_1h=None if self.spot_1h is None else self.spot_1h[sl],
            perp_1h=None if self.perp_1h is None else self.perp_1h[sl],
            eligibles=self.eligibles[sl],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[sl],
            funding_idx=self.funding_idx[sl], funding_taux=self.funding_taux[sl],
            funding_ts=self.funding_ts[sl])

    def mettre_a_l_echelle(self, facteurs: np.ndarray) -> Panneau:
        """Prix × facteur (par paire), volumes et achats taker ÷ facteur (même valeur échangée)."""
        f = np.asarray(facteurs, dtype=np.float64)

        def ech(a):
            if a is None:
                return None
            fp = f.reshape((1, len(f)) + (1,) * (a.ndim - 3))[..., None]
            b = a.copy()
            b[..., 0:4] = a[..., 0:4] * fp
            b[..., 4:6] = a[..., 4:6] / fp
            return b

        return self._remplacer(spot_1d=ech(self.spot_1d), spot_1h=ech(self.spot_1h),
                               perp_1h=ech(self.perp_1h))

    def corrompre_apres(self, coupure: int, rng: np.random.Generator) -> Panneau:
        """Remplace par du bruit toute donnée dont `connue_a` > `coupure` (secondes UTC)."""
        T, N = self.n_jours, self.n_paires
        h_fin = self.jours[:, None] + (np.arange(HEURES)[None, :] + 1) * 3600  # (T, 24)
        bruit_h = np.broadcast_to((h_fin > coupure)[:, None, :], (T, N, HEURES))
        j_fin = self.jours + JOUR_S
        bruit_j = j_fin > coupure  # (T,)
        bruit_jn = np.broadcast_to(bruit_j[:, None], (T, N))

        def bruit(forme):
            b = np.exp(rng.normal(0.0, 1.0, forme))
            return b

        s1d = self.spot_1d.copy()
        s1d[bruit_jn] = bruit(s1d[bruit_jn].shape) * 100.0
        s1h = None
        if self.spot_1h is not None:
            s1h = self.spot_1h.copy()
            s1h[bruit_h] = bruit(s1h[bruit_h].shape) * 100.0
        p1h = None
        if self.perp_1h is not None:
            p1h = self.perp_1h.copy()
            p1h[bruit_h] = bruit(p1h[bruit_h].shape) * 100.0
        elig = self.eligibles.copy()
        elig[bruit_jn] = rng.random(elig[bruit_jn].shape) < 0.5
        elp = None
        if self.eligibles_perp is not None:
            elp = self.eligibles_perp.copy()
            elp[bruit_jn] = rng.random(elp[bruit_jn].shape) < 0.5
        ft = tuple(np.where(s + 1 > coupure, rng.normal(0, 1e-3, len(s)), t)
                   for t, s in zip(self.funding_taux, self.funding_ts, strict=True))
        return self._remplacer(spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, eligibles=elig,
                               eligibles_perp=elp, funding_taux=ft)

    def rebaser(self, jours_volume: int = 30) -> Panneau:
        """Panneau tel que la STRATÉGIE le voit (le moteur, lui, calcule les rendements sur les prix réels).

        - prix (o,h,l,c, spot et perp) divisés, par paire, par le premier close spot valide de la paire :
          le niveau absolu n'identifie plus ni la paire ni la date ;
        - volumes (et achats taker) divisés, par paire, par le volume moyen courant des `jours_volume`
          premiers jours cotés : à partir du jour `jours_volume` le diviseur est fixe, avant il vaut la
          moyenne des volumes des jours cotés connus jusqu'au jour courant inclus (clôture). Causal : le
          diviseur du jour t ne dépend que de données de jours <= t.
        Les zéros (paire non cotée) restent des zéros. Le premier close valide est celui du jour de cotation,
        donc connu dès que la paire existe."""
        T, N = self.n_jours, self.n_paires
        close = self.spot_1d[:, :, 3]
        valide = self.eligibles & (close > 0)
        niveau = np.ones(N)
        vscale = np.ones((T, N))
        for k in range(N):
            idx = np.flatnonzero(valide[:, k])
            if len(idx) == 0:
                continue
            niveau[k] = close[idx[0], k]
            moy = np.cumsum(self.spot_1d[idx, k, 4]) / np.arange(1, len(idx) + 1)
            if len(moy) >= jours_volume:
                moy[jours_volume - 1:] = moy[jours_volume - 1]
            moy = np.where(np.isfinite(moy) & (moy > 0), moy, 1.0)
            vscale[idx, k] = moy

        def reb(a):
            if a is None:
                return None
            b = a.copy()
            extra = (1,) * (a.ndim - 3)
            b[..., 0:4] = a[..., 0:4] / niveau.reshape((1, N) + extra)[..., None]
            b[..., 4:6] = a[..., 4:6] / vscale.reshape((T, N) + extra)[..., None]
            return b

        return self._remplacer(spot_1d=reb(self.spot_1d), spot_1h=reb(self.spot_1h), perp_1h=reb(self.perp_1h))

    def jour(self, i: int):
        """Message `Jour` du jour i."""
        from recherche.moteur.contrat import Jour

        idx, tx = self.funding_idx[i], self.funding_taux[i]
        return Jour(
            i=i, spot_1d=self.spot_1d[i],
            spot_1h=None if self.spot_1h is None else self.spot_1h[i],
            perp_1h=None if self.perp_1h is None else self.perp_1h[i],
            funding=[(int(a), float(b)) for a, b in zip(idx, tx, strict=True)],
            eligibles=self.eligibles[i],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[i])

    # --- séries dérivées utilisées par le portefeuille -------------------------------------------
    def rendements_spot(self) -> np.ndarray:
        """(T, N) : rendement du jour t (clôture t-1 -> clôture t) ; 0 si l'une des clôtures est absente."""
        return _rendements(self.spot_1d[:, :, 3])

    def rendements_perp(self) -> np.ndarray:
        if self.perp_1h is None:
            return np.zeros((self.n_jours, self.n_paires))
        return _rendements(self.perp_1h[:, :, HEURES - 1, 3])

    def funding_par_jour(self) -> np.ndarray:
        """(T, N) : somme des taux de funding des échéances tombées dans chaque jour."""
        out = np.zeros((self.n_jours, self.n_paires))
        for i, (a, b) in enumerate(zip(self.funding_idx, self.funding_taux, strict=True)):
            if len(a):
                np.add.at(out[i], a, b)
        return out


def _rendements(close: np.ndarray) -> np.ndarray:
    r = np.zeros_like(close)
    prev, cur = close[:-1], close[1:]
    ok = (prev > 0) & (cur > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.where(ok, cur / np.where(prev > 0, prev, 1.0) - 1.0, 0.0)
    return r


# ----------------------------------------------------------------------------------------------------
# Construction depuis `Donnees`
# ----------------------------------------------------------------------------------------------------


def _secondes(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.as_unit("ns").asi8 // 1_000_000_000


def panneau_depuis_tables(
    symboles: list[str], spot_1d: dict[str, pd.DataFrame], spot_1h: dict[str, pd.DataFrame] | None = None,
    perp_1h: dict[str, pd.DataFrame | None] | None = None,
    funding: dict[str, pd.DataFrame | None] | None = None,
) -> Panneau:
    """Aligne des tables par symbole (format du chargeur) sur une grille de jours commune."""
    d0 = min(int(_secondes(spot_1d[s].index)[0]) for s in symboles)
    d1 = max(int(_secondes(spot_1d[s].index)[-1]) for s in symboles)
    d0 -= d0 % JOUR_S
    jours = np.arange(d0, d1 + 1, JOUR_S, dtype=np.int64)
    T, N = len(jours), len(symboles)
    s1d = np.zeros((T, N, N_COLONNES))
    elig = np.zeros((T, N), dtype=bool)
    for k, s in enumerate(symboles):
        df = spot_1d[s]
        pos = (_secondes(df.index) - d0) // JOUR_S
        s1d[pos, k] = df[_COLS].to_numpy()
        elig[pos, k] = True
    s1h = None
    if spot_1h is not None:
        s1h = np.zeros((T, N, HEURES, N_COLONNES))
        for k, s in enumerate(symboles):
            df = spot_1h[s]
            sec = _secondes(df.index) - d0
            s1h[sec // JOUR_S, k, (sec % JOUR_S) // 3600] = df[_COLS].to_numpy()
    p1h, elp = None, None
    fi = [[] for _ in range(T)]
    ft = [[] for _ in range(T)]
    fs = [[] for _ in range(T)]
    if perp_1h is not None and any(perp_1h.get(s) is not None for s in symboles):
        p1h = np.zeros((T, N, HEURES, N_COLONNES))
        elp = np.zeros((T, N), dtype=bool)
        for k, s in enumerate(symboles):
            df = perp_1h.get(s)
            if df is None:
                continue
            sec = _secondes(df.index) - d0
            ok = (sec >= 0) & (sec // JOUR_S < T)
            sec = sec[ok]
            p1h[sec // JOUR_S, k, (sec % JOUR_S) // 3600] = df[_COLS].to_numpy()[ok]
            elp[sec // JOUR_S, k] = True
            fdf = (funding or {}).get(s)
            if fdf is not None:
                fsec = _secondes(fdf.index)
                for t, x in zip(fsec, fdf["taux"].to_numpy(), strict=True):
                    j = (int(t) - d0) // JOUR_S
                    if 0 <= j < T:
                        fi[j].append(k)
                        ft[j].append(float(x))
                        fs[j].append(int(t))
    return Panneau(
        symboles=tuple(symboles), jours=jours, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, eligibles=elig,
        eligibles_perp=elp,
        funding_idx=tuple(np.array(a, dtype=np.int64) for a in fi),
        funding_taux=tuple(np.array(a, dtype=np.float64) for a in ft),
        funding_ts=tuple(np.array(a, dtype=np.int64) for a in fs))


def panneau_depuis_donnees(donnees, univers: str = "principal", *, avec_1h: bool = True,
                           avec_perp: bool = True, symboles_arene: tuple[str, ...] | None = None) -> Panneau:
    """`univers` : "principal" (les 15 paires), "arene" (`symboles_arene`, sinon les 6 des critères via
    l'appelant) ou "controle:<SYM>" (un symbole de contrôle, barres 1 j seulement)."""
    if univers.startswith("controle:"):
        sym = univers.split(":", 1)[1]
        return panneau_depuis_tables([sym], {sym: donnees.controle_1d[sym]})
    syms = list(donnees.univers)
    pan = panneau_depuis_tables(
        syms, donnees.spot_1d, donnees.spot_1h if avec_1h else None,
        donnees.perp_1h if avec_perp else None, donnees.funding if avec_perp else None)
    if univers == "principal":
        return pan
    if univers == "arene":
        if symboles_arene is None:
            raise ValueError("univers 'arene' : fournir symboles_arene (criteres.univers_arene)")
        return pan.sous_univers(list(symboles_arene))
    raise ValueError(f"univers inconnu : {univers!r}")


# ----------------------------------------------------------------------------------------------------
# Données synthétiques
# ----------------------------------------------------------------------------------------------------


def synthetique(
    n_jours: int = 400, n_paires: int = 15, graine: int = 0, *, avec_1h: bool = True, avec_perp: bool = False,
    debut_jour: int = 1_514_764_800, cotations_tardives: bool = True, sigma_h: float = 0.004,
    regimes: bool = False,
) -> Panneau:
    """Panneau synthétique cohérent (barre 1 j = agrégat de ses 24 barres 1 h). Aucune donnée réelle.
    `regimes=True` : régimes de marché variés (tendances, krachs, funding élevé positif soutenu ou négatif,
    base négative) ; voir `synthetique_varie`."""
    rng = np.random.default_rng(graine)
    T, N, H = n_jours, n_paires, HEURES
    debut_jour -= debut_jour % JOUR_S
    jours = debut_jour + JOUR_S * np.arange(T, dtype=np.int64)
    commun = rng.normal(0.0, sigma_h * 0.6, (T * H, 1))
    if regimes:
        etat = _etats_marche(rng, T)
        mu_j = np.array([0.0002, 0.0012, -0.0010, -0.02])[etat]
        vol_j = np.array([1.0, 1.2, 1.6, 3.0])[etat]
        beta = rng.uniform(0.6, 1.4, N)
        mu_h = np.repeat(mu_j / H, H)[:, None] * beta[None, :]
        vol_h = np.repeat(vol_j, H)[:, None]
        ret = mu_h + (rng.normal(0.0, sigma_h, (T * H, N)) + commun) * vol_h
    else:
        ret = rng.normal(0.0002, sigma_h, (T * H, N)) + commun
    niveau0 = np.exp(rng.uniform(-1.0, 9.0, N))
    close = niveau0 * np.exp(np.cumsum(ret, axis=0))
    open_ = np.vstack([niveau0[None, :], close[:-1]])
    amp = np.abs(rng.normal(0.0, sigma_h * 0.5, (T * H, N)))
    high = np.maximum(open_, close) * (1.0 + amp)
    low = np.minimum(open_, close) * (1.0 - amp)
    vol = np.exp(rng.normal(8.0, 0.6, (T * H, N)))
    part = np.clip(0.5 + 0.08 * np.tanh(ret / sigma_h) + rng.normal(0.0, 0.05, (T * H, N)), 0.05, 0.95)
    taker = vol * part
    barres = np.stack([open_, high, low, close, vol, taker], axis=-1).reshape(T, H, N, 6).transpose(0, 2, 1, 3)
    barres = np.ascontiguousarray(barres)  # (T, N, 24, 6)
    s1d = np.empty((T, N, 6))
    s1d[..., 0] = barres[:, :, 0, 0]
    s1d[..., 1] = barres[..., 1].max(axis=2)
    s1d[..., 2] = barres[..., 2].min(axis=2)
    s1d[..., 3] = barres[:, :, -1, 3]
    s1d[..., 4] = barres[..., 4].sum(axis=2)
    s1d[..., 5] = barres[..., 5].sum(axis=2)
    elig = np.ones((T, N), dtype=bool)
    if cotations_tardives and N > 2:
        for k in range(N // 3, N):
            premier = int(rng.integers(1, max(2, T // 3)))
            elig[:premier, k] = False
    s1d[~elig] = 0.0
    barres[~elig] = 0.0
    s1h = barres if avec_1h else None
    p1h = elp = None
    fi, ft, fs = [], [], []
    if avec_perp:
        if regimes:
            ann, base = _funding_et_base(rng, T, N, H, etat)
        else:
            base = rng.normal(0.0, 0.0005, (T * H, N))
        pm = np.stack([x * (1.0 + base) for x in (open_, high, low, close)], axis=-1)
        pv = np.stack([vol * 3.0, taker * 3.0], axis=-1)
        pb = np.concatenate([pm, pv], axis=-1).reshape(T, H, N, 6).transpose(0, 2, 1, 3)
        p1h = np.ascontiguousarray(pb)
        elp = elig.copy()
        elp[: max(1, T // 10)] = False
        p1h[~elp] = 0.0
        if regimes:
            taux = ann[:, None, :] / 1095.0 + rng.normal(0.0, 0.00003, (T, 3, N))
        else:
            taux = rng.normal(0.00005, 0.00015, (T, 3, N))
        for i in range(T):
            ok = np.flatnonzero(elp[i])
            idx = np.tile(ok, 3).astype(np.int64)
            tx = taux[i][:, ok].reshape(-1)
            ts = np.repeat(jours[i] + np.array([0, 8, 16]) * 3600, len(ok)).astype(np.int64)
            fi.append(idx)
            ft.append(tx)
            fs.append(ts)
    else:
        z = np.zeros(0)
        fi = [z.astype(np.int64)] * T
        ft = [z] * T
        fs = [z.astype(np.int64)] * T
    return Panneau(
        symboles=tuple(f"S{k:02d}" for k in range(N)), jours=jours, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h,
        eligibles=elig, eligibles_perp=elp, funding_idx=tuple(fi), funding_taux=tuple(ft),
        funding_ts=tuple(fs))


def _etats_marche(rng: np.random.Generator, T: int) -> np.ndarray:
    """(T,) états de marché par blocs : 0 calme, 1 tendance haussière, 2 baissière, 3 krach (2 à 8 jours)."""
    etat = np.zeros(T, dtype=np.int64)
    t = 0
    while t < T:
        e = int(rng.choice(4, p=[0.35, 0.30, 0.25, 0.10]))
        duree = int(rng.integers(2, 9)) if e == 3 else int(rng.integers(20, 121))
        etat[t:t + duree] = e
        t += duree
    return etat


def _funding_et_base(rng: np.random.Generator, T: int, N: int, H: int, etat: np.ndarray):
    """(funding annualisé (T, N), base perp/spot par heure (T*H, N)) : niveaux de funding par blocs de 40 à 250
    jours (négatifs, nuls, modérés, élevés, extrêmes), en partie communs au marché ; base mean-revertante liée
    au funding, négative en krach et en marché baissier."""
    niveaux = np.array([-0.15, -0.05, 0.0, 0.12, 0.25, 0.5, 1.0, 1.4])
    ann = np.empty((T, N))
    for k in range(N):
        t = 0
        while t < T:
            duree = int(rng.integers(40, 251))
            ann[t:t + duree, k] = rng.choice(niveaux)
            t += duree
    marche = np.array([0.0, 0.3, -0.12, -0.25])[etat]
    ann = 0.6 * ann + 0.4 * rng.choice(niveaux[3:], size=1) * (etat[:, None] == 1) + marche[:, None]
    cible = 0.006 * ann - np.where(etat == 3, 0.02, 0.0)[:, None] - np.where(etat == 2, 0.004, 0.0)[:, None]
    b = np.zeros((T, N))
    cur = cible[0].copy()
    bruit = rng.normal(0.0, 0.0015, (T, N))
    for i in range(T):
        cur = 0.9 * cur + 0.1 * cible[i] + bruit[i]
        b[i] = cur
    base_h = np.repeat(b, H, axis=0) + rng.normal(0.0, 0.0003, (T * H, N))
    return ann, base_h


def synthetique_varie(n_jours: int = 1300, n_paires: int = 15, graine: int | None = None, **kw) -> Panneau:
    """Panneau synthétique à régimes variés pour le contrôle de causalité C9 (>= 1 300 jours : les
    stratégies à historique long, p. ex. 365 jours de funding, produisent des poids non triviaux).
    `graine=None` : graine tirée de `os.urandom` à chaque appel."""
    import os

    if graine is None:
        graine = int.from_bytes(os.urandom(8), "big")
    kw.setdefault("avec_perp", True)
    return synthetique(n_jours, n_paires, graine, regimes=True, **kw)
