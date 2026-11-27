"""Polite, resumable download of Binance public-dump data for axis 05 (stored outside git)."""
import re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path("~/dev/_arena-data/axis-05").expanduser()
BASE = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT", "LINKUSDT"]


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-fetch/1.0"})
            return urllib.request.urlopen(req, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed {url}")


def list_keys(prefix):
    keys, marker = [], ""
    while True:
        u = f"{S3}?delimiter=/&prefix={prefix}&max-keys=1000" + (f"&marker={marker}" if marker else "")
        x = get(u).decode()
        ks = re.findall(r"<Key>([^<]*\.zip)</Key>", x)
        keys += ks
        if "<IsTruncated>true" in x and ks:
            marker = ks[-1]
        else:
            return keys


def main():
    for sym in SYMS:
        for kind, prefix in [
            ("metrics", f"data/futures/um/daily/metrics/{sym}/"),
            ("klines", f"data/futures/um/monthly/klines/{sym}/1m/"),
            ("klines_daily", f"data/futures/um/daily/klines/{sym}/1m/"),
            ("funding", f"data/futures/um/monthly/fundingRate/{sym}/"),
        ]:
            keys = list_keys(prefix)
            if kind == "klines_daily":  # only days after the last monthly zip
                monthly = sorted(k for k in list_keys(f"data/futures/um/monthly/klines/{sym}/1m/"))
                last = re.search(r"(\d{4}-\d{2})\.zip", monthly[-1]).group(1)
                keys = [k for k in keys if re.search(r"(\d{4}-\d{2})-\d{2}\.zip", k).group(1) > last]
            out = ROOT / kind / sym
            out.mkdir(parents=True, exist_ok=True)
            todo = [k for k in sorted(keys) if not (out / Path(k).name).exists()]

            def one(k):
                b = get(BASE + k)
                if b is not None:
                    part = out / (Path(k).name + ".part")
                    part.write_bytes(b)
                    part.rename(out / Path(k).name)
                time.sleep(0.1)
                return b is not None

            with ThreadPoolExecutor(6) as ex:  # 6 connections to a static CDN
                n = sum(ex.map(one, todo))
            print(sym, kind, len(keys), "listed,", n, "new", flush=True)


if __name__ == "__main__":
    main()
