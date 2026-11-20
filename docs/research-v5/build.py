import pickle, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arena.perp.lab import backtest as B
from harness import DESIGN_DAYS
d = B.load(Path(__file__).with_name("data") / "kraken_futures")
print("minutes", d.n, "days", d.n / 1440, "from", d.ts[0], "to", d.ts[-1])
Path("full.pkl").write_bytes(pickle.dumps(d))
n = DESIGN_DAYS * 1440
cut = B.Data(d.ts[:n], d.open[:n], d.high[:n], d.low[:n], d.close[:n], d.volume[:n], d.funding[:n])
Path("design.pkl").write_bytes(pickle.dumps(cut))
print("design until", cut.ts[-1], "funding nonzero", (cut.funding != 0).sum(axis=0))
