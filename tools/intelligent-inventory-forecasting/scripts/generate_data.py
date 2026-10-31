from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/generated/demand.csv'
rng=np.random.default_rng(27)
weeks=pd.date_range('2024-01-01',periods=104,freq='W-MON')
rows=[]
for sku in range(1,13):
 base=10+sku*2
 for i,w in enumerate(weeks):
  seasonal=1+.22*np.sin(2*np.pi*i/52)
  units=max(0,int(rng.poisson(base*seasonal)))
  rows.append({'week':w.date().isoformat(),'sku':f'SKU-{sku:03}','units':units})
OUT.parent.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'Wrote {len(rows)} synthetic weekly demand observations')
