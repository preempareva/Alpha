from __future__ import annotations

from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/generated/weekly_sales.csv'
POLICIES={'conservative':2.0,'balanced':1.65,'lean':1.28}


def history() -> pd.DataFrame:
    if not DATA.exists():
        raise FileNotFoundError('Generate the synthetic sales history with scripts/generate_data.py')
    return pd.read_csv(DATA,parse_dates=['week'])


def backtest(df: pd.DataFrame, horizon: int=8) -> dict:
    values=df.sort_values('week').units.to_numpy(dtype=float)
    if len(values)<horizon+12:
        raise ValueError('At least 20 weekly observations are required.')
    split=len(values)-horizon
    train,test=values[:split],values[split:]
    pred=[float(train[-min(4,len(train)):].mean())]*horizon
    seasonal=[float(train[-min(52,len(train)):][i%min(52,len(train))]) for i in range(horizon)] if len(train)>=52 else [float(train[-1])]*horizon
    mae=lambda a,b: float(sum(abs(x-y) for x,y in zip(a,b))/len(a))
    return {'horizon_weeks':horizon,'train_weeks':len(train),'test_weeks':len(test),
            'baseline_4week_mae':round(mae(test,pred),3),'seasonal_naive_mae':round(mae(test,seasonal),3),
            'test_actual_mean':round(float(test.mean()),3),'disclaimer':'Synthetic series; backtest is not a business forecast guarantee.'}


def recommend(df: pd.DataFrame, sku: str, lead_time: int, on_hand: float, incoming: float, policy: str='balanced') -> dict:
    if policy not in POLICIES: raise ValueError('Unknown policy.')
    if not 1<=lead_time<=26: raise ValueError('Lead time must be between 1 and 26 weeks.')
    if on_hand<0 or incoming<0: raise ValueError('Inventory quantities cannot be negative.')
    series=df[df.sku==sku].sort_values('week').units
    if len(series)<12: raise ValueError('SKU needs at least 12 weeks of history.')
    recent=series.tail(8).to_numpy(dtype=float)
    weekly=float(recent.mean())
    sigma=float(recent.std(ddof=1))
    z=POLICIES[policy]
    safety=z*sigma*(lead_time**0.5)
    reorder_point=weekly*lead_time+safety
    position=on_hand+incoming
    qty=max(0,int(round(reorder_point-position)))
    return {'sku':sku,'status':'NEEDS_APPROVAL','policy':policy,'weekly_demand_estimate':round(weekly,2),
            'weekly_demand_std':round(sigma,2),'lead_time_weeks':lead_time,'on_hand':on_hand,'incoming':incoming,
            'inventory_position':position,'safety_stock':round(safety,2),'reorder_point':round(reorder_point,2),
            'suggested_replenishment_units':qty,'explanation':'Recent 8-week mean plus a configurable safety buffer. Synthetic suggestion only; no order was placed.'}
