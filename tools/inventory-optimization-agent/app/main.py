from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .logic import history, backtest, recommend

app=FastAPI(title='Replenishment Calculator',version='0.1.0')

class Replenish(BaseModel):
    sku:str=Field(min_length=1,max_length=40)
    lead_time_weeks:int=Field(ge=1,le=26)
    on_hand:float=Field(ge=0)
    incoming:float=Field(default=0,ge=0)
    policy:str='balanced'

@app.get('/health')
def health():return {'status':'ok'}

@app.get('/api/backtest')
def get_backtest(sku:str='SKU-001'):
    try:
        df=history(); series=df[df.sku==sku]
        if series.empty:raise HTTPException(404,'SKU not found.')
        return {'sku':sku,**backtest(series)}
    except FileNotFoundError as e:raise HTTPException(503,str(e)) from e

@app.post('/api/recommend')
def suggestion(payload:Replenish):
    try:return recommend(history(),payload.sku,payload.lead_time_weeks,payload.on_hand,payload.incoming,payload.policy)
    except FileNotFoundError as e:raise HTTPException(503,str(e)) from e
    except ValueError as e:raise HTTPException(422,str(e)) from e

@app.get('/',response_class=HTMLResponse)
def home():
 return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Replenishment Calculator</title><style>body{font:16px system-ui;max-width:780px;margin:3rem auto;padding:0 1rem}input,select{padding:.6rem;margin:.3rem}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px}pre{white-space:pre-wrap;background:#f1f4f5;padding:1rem}</style></head><body><h1>Replenishment Calculator</h1><p>Synthetic demand model. Recommendations are drafts for approval; no purchase order is placed.</p><form id=f><label>SKU <input name=sku value=SKU-001></label><label>Lead time weeks <input name=lead_time_weeks type=number value=4 min=1 max=26></label><label>On hand <input name=on_hand type=number value=30 min=0></label><label>Incoming <input name=incoming type=number value=0 min=0></label><select name=policy><option>balanced</option><option>conservative</option><option>lean</option></select><button>Calculate draft recommendation</button></form><pre id=o aria-live=polite></pre><script>f.onsubmit=async e=>{e.preventDefault();let v=Object.fromEntries(new FormData(f));for(let k of ['lead_time_weeks','on_hand','incoming'])v[k]=Number(v[k]);let r=await fetch('/api/recommend',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(v)});o.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""
