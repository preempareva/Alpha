from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/generated/transactions.csv'
rng=np.random.default_rng(112)
rows=[]
for c in range(700):
 group=c%4
 count=int(rng.poisson([2,8,3,15][group])+1)
 for i in range(count):
  days=int(rng.integers(0,[120,30,90,14][group]+1))
  amount=float(rng.lognormal([3.2,3.7,4.5,3.0][group],.45))
  rows.append({'transaction_id':f'T{c:04}-{i:02}','customer_id':f'SYN-{c:04}','date':(pd.Timestamp('2026-01-01')-pd.Timedelta(days=days)).date().isoformat(),'amount':round(amount,2)})
OUT.parent.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'Wrote {len(rows)} synthetic transactions for 700 fictional customers')
