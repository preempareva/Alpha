from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
app=FastAPI(title='Supplier Quote Comparison',version='0.1.0')

class Quote(BaseModel):
 supplier:str=Field(min_length=1,max_length=80)
 unit_price:float=Field(gt=0)
 quantity:int=Field(gt=0)
 currency:str=Field(min_length=3,max_length=3)
 freight:float|None=Field(default=None,ge=0)
 tax_percent:float|None=Field(default=None,ge=0,le=100)
 lead_time_days:int|None=Field(default=None,ge=1,le=365)
 quality_score:float|None=Field(default=None,ge=0,le=100)
 compliance_confirmed:bool=False

class Compare(BaseModel):
 quotes:list[Quote]=Field(min_length=2,max_length=20)
 price_weight:float=Field(default=.55,ge=0,le=1)
 delivery_weight:float=Field(default=.25,ge=0,le=1)
 quality_weight:float=Field(default=.2,ge=0,le=1)

@app.get('/health')
def health():return {'status':'ok'}

@app.post('/api/compare')
def compare(payload:Compare):
 currencies={q.currency.upper() for q in payload.quotes}
 if len(currencies)!=1:raise HTTPException(422,'Quotes must use the same currency; conversion is not guessed.')
 weights=payload.price_weight+payload.delivery_weight+payload.quality_weight
 if abs(weights-1)>.001:raise HTTPException(422,'Score weights must sum to 1.0.')
 totals=[]
 for q in payload.quotes:
  missing=[]
  if q.freight is None:missing.append('freight')
  if q.tax_percent is None:missing.append('tax treatment')
  if q.lead_time_days is None:missing.append('lead time')
  if q.quality_score is None:missing.append('quality history')
  landed=(q.unit_price*q.quantity+(q.freight or 0))*(1+(q.tax_percent or 0)/100)
  totals.append({'supplier':q.supplier,'currency':q.currency.upper(),'unit_price':q.unit_price,'quantity':q.quantity,'estimated_landed_cost':round(landed,2),'lead_time_days':q.lead_time_days,'quality_score':q.quality_score,'compliance_confirmed':q.compliance_confirmed,'missing_terms':missing})
 max_cost=max(x['estimated_landed_cost'] for x in totals) or 1
 max_days=max((x['lead_time_days'] or 365) for x in totals)
 for item in totals:
  item['score']=round(payload.price_weight*(1-item['estimated_landed_cost']/max_cost)+payload.delivery_weight*(1-(item['lead_time_days'] or max_days)/max_days)+payload.quality_weight*((item['quality_score'] or 0)/100),4)
  if item['missing_terms'] or not item['compliance_confirmed']:item['status']='NEEDS_REVIEW'
  else:item['status']='COMPARABLE'
 totals.sort(key=lambda x:x['score'],reverse=True)
 return {'status':'ANALYST_REVIEW','quotes':totals,'suggested_order':totals[0]['supplier'] if totals[0]['status']=='COMPARABLE' else None,'weights':{'price':payload.price_weight,'delivery':payload.delivery_weight,'quality':payload.quality_weight},'notice':'Comparison aid only. Verify source documents and terms; no supplier is selected or contacted.'}

@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><title>Quote comparison</title></head><body style='font:16px system-ui;max-width:800px;margin:3rem auto'><h1>Supplier quote comparison</h1><p>Try API /docs with synthetic quote data. Missing terms are flagged; no award is made.</p><p>Every landed-cost component and score weight is returned for review.</p></body></html>"""
