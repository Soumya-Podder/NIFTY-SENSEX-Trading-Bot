import numpy as np
import pandas as pd

def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=1).mean()

def rsi(s,n=14):
    d=s.diff()
    up=d.clip(lower=0)
    dn=-d.clip(upper=0)
    au=up.ewm(alpha=1/n,adjust=False).mean()
    ad=dn.ewm(alpha=1/n,adjust=False).mean()
    result=100-100/(1+au/ad.replace(0,np.nan))
    result=result.mask((ad==0)&(au>0),100).mask((au==0)&(ad>0),0)
    return result.mask((au==0)&(ad==0),50)

def adx(df,n=14):
    up=df.high.diff(); dn=-df.low.diff()
    plus=up.where((up>dn)&(up>0),0.0)
    minus=dn.where((dn>up)&(dn>0),0.0)
    a=atr(df,n)
    p=100*plus.ewm(alpha=1/n,adjust=False).mean()/a.replace(0,np.nan)
    m=100*minus.ewm(alpha=1/n,adjust=False).mean()/a.replace(0,np.nan)
    dx=100*(p-m).abs()/(p+m).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean().fillna(0)

def add_features(df):
    x=df.copy().sort_values("timestamp").reset_index(drop=True)
    if x.empty: return x
    x["timestamp"]=pd.to_datetime(x.timestamp)
    if x.timestamp.dt.tz is None:
        x["timestamp"]=x.timestamp.dt.tz_localize("Asia/Kolkata")
    else:
        x["timestamp"]=x.timestamp.dt.tz_convert("Asia/Kolkata")
    if "symbol" in x and x.symbol.nunique()>1:
        return pd.concat([add_features(group) for _,group in x.groupby("symbol")],ignore_index=True).sort_values(["timestamp","symbol"])
    session=x.timestamp.dt.date
    x["ema9"]=ema(x.close,9); x["ema21"]=ema(x.close,21); x["ema50"]=ema(x.close,50)
    x["atr"]=atr(x); x["rsi"]=rsi(x.close); x["adx"]=adx(x)
    volume=pd.to_numeric(x.volume,errors="coerce").where(lambda s:s>=0)
    x["vwap"]=(x.close*volume).groupby(session).cumsum()/volume.groupby(session).cumsum().replace(0,np.nan)
    vm=volume.groupby(session).transform(lambda s:s.rolling(20,min_periods=5).mean())
    x["relative_volume"]=volume/vm.replace(0,np.nan)
    x["atr_percentile"]=x.atr.rolling(100,min_periods=20).rank(pct=True)
    x["vwap_distance_atr"]=(x.close-x.vwap)/x.atr.replace(0,np.nan)
    x["ema_slope_atr"]=(x.ema21-x.ema21.shift(5))/x.atr.replace(0,np.nan)
    return x
