from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/generated/demand.csv'

def data():
 if not DATA.exists():raise FileNotFoundError('Run scripts/generate_data.py first.')
 return pd.read_csv(DATA,parse_dates=['week'])

def forecast(df:pd.DataFrame,sku:str,horizon:int=8):
 if not 1<=horizon<=26:raise ValueError('Horizon must be 1 to 26 weeks.')
 s=df[df.sku==sku].sort_values('week').units.to_numpy(dtype=float)
 if len(s)<20:raise ValueError('Need at least 20 weekly observations.')
 train=s[:-horizon] if len(s)>horizon else s
 recent=train[-8:]
 mean=float(recent.mean());sigma=float(recent.std(ddof=1))
 future=pd.date_range(pd.Timestamp(df.week.max())+pd.Timedelta(weeks=1),periods=horizon,freq='W-MON')
 return {'sku':sku,'horizon_weeks':horizon,'method':'last-8-week mean with residual-style range','forecast':[{'week':d.date().isoformat(),'p50':round(mean,2),'p10':round(max(0,mean-1.28*sigma),2),'p90':round(mean+1.28*sigma,2)} for d in future],'notice':'Synthetic transaction-style benchmark, not inventory truth or a savings claim.'}

def backtest(df:pd.DataFrame,sku:str,horizon:int=8):
 s=df[df.sku==sku].sort_values('week').units.to_numpy(dtype=float)
 if len(s)<horizon+12:raise ValueError('Insufficient history for temporal holdout.')
 train,test=s[:-horizon],s[-horizon:]
 preds=[float(train[-8:].mean())]*horizon
 naive=[float(train[-1])]*horizon
 mae=lambda a,b:float(np.mean(np.abs(np.array(a)-np.array(b))))
 return {'train_weeks':len(train),'test_weeks':len(test),'mean_baseline_mae':round(mae(test,preds),3),'last_value_mae':round(mae(test,naive),3),'coverage_10_90':round(float(np.mean((np.array(test)>=np.maximum(0,np.array(preds)-1.28*np.std(train[-8:],ddof=1)))&(np.array(test)<=np.array(preds)+1.28*np.std(train[-8:],ddof=1)))),3)}
