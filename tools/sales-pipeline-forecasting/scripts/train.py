import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV,calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score,brier_score_loss,roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/generated/opportunities.csv';OUT=ROOT/'artifacts'
FEATURES=['amount','age_days','stage','touches_30d','stakeholder_count']

def run():
 if not DATA.exists():raise SystemExit('Generate data first.')
 df=pd.read_csv(DATA,parse_dates=['snapshot_date']);cut=df.snapshot_date.quantile(.8);tr=df[df.snapshot_date<cut];te=df[df.snapshot_date>=cut]
 prep=ColumnTransformer([('num',Pipeline([('imp',SimpleImputer(strategy='median')),('scale',StandardScaler())]),['amount','age_days','touches_30d','stakeholder_count']),('cat',OneHotEncoder(handle_unknown='ignore'),['stage'])])
 base=Pipeline([('prep',prep),('model',LogisticRegression(max_iter=1000,class_weight='balanced',random_state=41))]);model=CalibratedClassifierCV(base,method='sigmoid',cv=3);model.fit(tr[FEATURES],tr.won_90d)
 p=model.predict_proba(te[FEATURES])[:,1];dummy=DummyClassifier(strategy='prior').fit(tr[FEATURES],tr.won_90d);dp=dummy.predict_proba(te[FEATURES])[:,1]
 metrics={'dataset':'synthetic one-row-per-opportunity snapshots','train_end':str(tr.snapshot_date.max().date()),'test_start':str(te.snapshot_date.min().date()),'train_rows':len(tr),'test_rows':len(te),'test_won_rate':round(float(te.won_90d.mean()),4),'model':{'roc_auc':round(float(roc_auc_score(te.won_90d,p)),4),'pr_auc':round(float(average_precision_score(te.won_90d,p)),4),'brier':round(float(brier_score_loss(te.won_90d,p)),4)},'dummy_prior':{'roc_auc':round(float(roc_auc_score(te.won_90d,dp)),4),'pr_auc':round(float(average_precision_score(te.won_90d,dp)),4),'brier':round(float(brier_score_loss(te.won_90d,dp)),4)},'limitations':['Synthetic outcomes generated from feature formula.','Each opportunity has one synthetic snapshot; repeated temporal histories are not represented.','Weighted pipeline is not a revenue commitment or causal estimate.']}
 OUT.mkdir(exist_ok=True);joblib.dump(model,OUT/'sales.joblib');(OUT/'evaluation.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2));return metrics
if __name__=='__main__':run()
