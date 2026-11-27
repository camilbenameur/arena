"""Download daily adjusted closes from the Yahoo chart API into the data dir (outside git)."""
import os
import requests, time, pandas as pd, sys
D=os.path.expanduser("~/dev/_arena-data/axis-02/")
SYMS=sys.argv[1:] or ["SPY","EFA","EEM","TLT","IEF","SHY","GLD","DBC","VNQ","UUP","FXE","FXY","BTC-USD","ETH-USD","^GSPC","ACWI","^IRX","^TNX"]
for s in SYMS:
    r=requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}",params={"period1":0,"period2":int(time.time()),"interval":"1d","events":"div,splits"},headers={"User-Agent":"Mozilla/5.0"},timeout=30)
    j=r.json()["chart"]["result"][0]
    ts=j["timestamp"]; q=j["indicators"]["quote"][0]; adj=j["indicators"].get("adjclose",[{}])[0].get("adjclose")
    df=pd.DataFrame({"close":q["close"],"adj":adj if adj else q["close"]},index=pd.to_datetime(ts,unit="s").normalize())
    df=df[~df.index.duplicated()].dropna()
    df.to_csv(D+s.replace("^","")+".csv"); print(s,df.index[0].date(),df.index[-1].date(),len(df))
    time.sleep(2)
