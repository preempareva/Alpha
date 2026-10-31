from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/generated/opportunities.csv'
rng=np.random.default_rng(87)
stages=['discovery','evaluation','proposal','negotiation']
rows=[]
for i in range(2500):
 date=pd.Timestamp('2024-01-01')+pd.Timedelta(days=int(rng.integers(0,640)))
 stage=rng.choice(stages,p=[.35,.3,.22,.13]);age=int(rng.integers(3,240));touches=int(rng.poisson(2.4));stake=int(rng.integers(1,7));amount=float(rng.lognormal(9.5,.7))
 logit=-2.4+stages.index(stage)*.7+touches*.18+stake*.08-age*.004
 p=1/(1+np.exp(-logit));won=int(rng.random()<p)
 rows.append({'opportunity_id':f'SYN-OPP-{i:05}','snapshot_date':date.date().isoformat(),'amount':round(amount,2),'age_days':age,'stage':stage,'touches_30d':touches,'stakeholder_count':stake,'won_90d':won})
OUT.parent.mkdir(parents=True,exist_ok=True);pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'Wrote {len(rows)} synthetic point-in-time opportunity snapshots')
