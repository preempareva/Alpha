from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
app=FastAPI(title='Travel Itinerary Planner',version='0.1.0')
CATALOG=[
 {'id':'SYN-A1','name':'Riverside Garden','interest':'nature','cost':0,'hours':2,'accessible':True,'source':'Fictional demo catalog v1'},
 {'id':'SYN-A2','name':'City History Hall','interest':'history','cost':12,'hours':2,'accessible':True,'source':'Fictional demo catalog v1'},
 {'id':'SYN-A3','name':'Hilltop Lookout','interest':'nature','cost':5,'hours':3,'accessible':False,'source':'Fictional demo catalog v1'},
 {'id':'SYN-A4','name':'Design Market','interest':'food','cost':18,'hours':2,'accessible':True,'source':'Fictional demo catalog v1'},
 {'id':'SYN-A5','name':'Science Center','interest':'family','cost':20,'hours':3,'accessible':True,'source':'Fictional demo catalog v1'},
 {'id':'SYN-A6','name':'Old Town Walk','interest':'history','cost':0,'hours':2,'accessible':True,'source':'Fictional demo catalog v1'},
]
class Plan(BaseModel):
 days:int=Field(ge=1,le=7)
 daily_budget:float=Field(ge=0,le=10000)
 interests:list[str]=Field(min_length=1,max_length=5)
 accessibility_required:bool=True
 available_hours_per_day:float=Field(default=7,ge=1,le=16)
@app.get('/health')
def health():return {'status':'ok'}
@app.post('/api/itinerary')
def itinerary(p:Plan):
 wanted={i.lower() for i in p.interests}
 options=[x for x in CATALOG if x['interest'] in wanted and x['cost']<=p.daily_budget and x['hours']<=p.available_hours_per_day and (x['accessible'] or not p.accessibility_required)]
 if not options:raise HTTPException(422,'No demo activities match these constraints; relax a preference.')
 days=[];used=set();total=0
 for day in range(1,p.days+1):
  activity=next((a for a in options if a['id'] not in used),None)
  if not activity:days.append({'day':day,'activities':[],'note':'No additional matching activity in this small demo catalog.'});continue
  used.add(activity['id']);total+=activity['cost']
  days.append({'day':day,'activities':[{'name':activity['name'],'estimated_cost':activity['cost'],'duration_hours':activity['hours'],'citation':{'source_id':activity['id'],'catalog':activity['source']}}]})
 return {'destination':'Demo City (fictional)','days':days,'estimated_total':total,'currency':'USD (illustrative)','approval':'Review itinerary before travel. No booking or payment capability exists.','notice':'Catalog and price estimates are fictional examples, not live travel information.'}
@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><title>Itinerary planner</title></head><body style='font:16px system-ui;max-width:800px;margin:3rem auto'><h1>Travel itinerary planner</h1><p>Fictional catalog only. It does not provide live availability or book travel.</p><p>Use <a href='/docs'>API docs</a> to build a plan with day count, budget, interests and accessibility constraints.</p></body></html>"""
