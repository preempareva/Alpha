from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/generated/weekly_sales.csv'
rng=np.random.default_rng(79)
rows=[]
weeks=pd.date_range('2024-01-01',periods=104,freq='W-MON')
for sku in range(1,9):
 base=8+sku*3
 for i,week in enumerate(weeks):
  seasonal=1+0.18*np.sin(2*np.pi*i/52)
  units=max(0,int(rng.poisson(base*seasonal)))
  rows.append({'week':week.date().isoformat(),'sku':f'SKU-{sku:03d}','units':units})
OUT.parent.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'Wrote {len(rows)} synthetic weekly demand records to {OUT}')
