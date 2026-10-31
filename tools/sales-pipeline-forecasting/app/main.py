from pathlib import Path
import os
import joblib
import pandas as pd
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
ROOT=Path(__file__).resolve().parents[1]
MODEL=Path(os.getenv('SALES_MODEL',str(ROOT/'artifacts/sales.joblib')))
FEATURES=['amount','age_days','stage','touches_30d','stakeholder_count']
app=FastAPI(title='Sales Pipeline Forecast',version='0.1.0')
class Opportunity(BaseModel):
 opportunity_id:str=Field(min_length=1,max_length=80)
 amount:float=Field(gt=0,le=1e9)
 age_days:int=Field(ge=0,le=3650)
 stage:str=Field(min_length=1,max_length=30)
 touches_30d:int=Field(ge=0,le=1000)
 stakeholder_count:int=Field(ge=0,le=500)
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/api/metrics')
def metrics():
 p=MODEL.with_name('evaluation.json')
 if not p.exists():raise HTTPException(503,'Train model first with scripts/train.py.')
 return __import__('json').loads(p.read_text())
@app.post('/api/score')
def score(payload:Opportunity):
 if not MODEL.exists():raise HTTPException(503,'Train model first with scripts/train.py.')
 d=payload.model_dump();oid=d.pop('opportunity_id')
 model=joblib.load(MODEL);prob=float(model.predict_proba(pd.DataFrame([d],columns=FEATURES))[0,1])
 return {'opportunity_id':oid,'win_probability':round(prob,4),'weighted_pipeline_value':round(prob*payload.amount,2),'horizon_days':90,'notice':'Synthetic point-in-time model output; review pipeline context. Not a revenue commitment.'}
@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><title>Pipeline forecast</title></head><body style='font:16px system-ui;max-width:800px;margin:3rem auto'><h1>Sales pipeline forecast</h1><p>Synthetic point-in-time 90-day win probabilities. Open <a href='/docs'>API docs</a> to score an opportunity. Weighted value is not a committed forecast.</p><a href='/api/metrics'>Evaluation metrics</a></body></html>"""
