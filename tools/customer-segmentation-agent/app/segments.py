from pathlib import Path
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/generated/transactions.csv'
FEATURES=['recency_days','frequency','monetary']

def run_segments(k:int=4):
 if not 2<=k<=8:raise ValueError('Cluster count must be between 2 and 8.')
 if not DATA.exists():raise FileNotFoundError('Run scripts/generate_data.py first.')
 tx=pd.read_csv(DATA,parse_dates=['date'])
 ref=tx.date.max()+pd.Timedelta(days=1)
 f=tx.groupby('customer_id').agg(last_date=('date','max'),frequency=('transaction_id','nunique'),monetary=('amount','sum')).reset_index()
 f['recency_days']=(ref-f.last_date).dt.days
 x=f[FEATURES].copy();x['monetary']=x.monetary.clip(lower=0).apply(lambda v:__import__('math').log1p(v))
 z=StandardScaler().fit_transform(x)
 labels=KMeans(n_clusters=k,n_init=10,random_state=31).fit_predict(z)
 f['segment']=labels
 profiles=f.groupby('segment')[FEATURES].mean().round(2).reset_index().to_dict('records')
 silhouette=float(silhouette_score(z,labels)) if len(set(labels))>1 else 0
 return {'status':'EXPLORATORY','customers':len(f),'segments':profiles,'silhouette':round(silhouette,4),'feature_version':'rfm-v1','notice':'Synthetic exploratory segments. Names/actions require human review; no targeting or individual treatment is performed.'}
