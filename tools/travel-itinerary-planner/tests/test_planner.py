from importlib import import_module
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from fastapi.testclient import TestClient
app = import_module("tools.travel-itinerary-planner.app.main").app
C=TestClient(app)

def test_plan_respects_budget_access_and_has_citations():
 r=C.post('/api/itinerary',json={'days':2,'daily_budget':20,'interests':['history','food'],'accessibility_required':True})
 assert r.status_code==200
 for day in r.json()['days']:
  for a in day['activities']:assert a['citation']['source_id'].startswith('SYN-')

def test_infeasible_constraints_are_explained():
 r=C.post('/api/itinerary',json={'days':1,'daily_budget':0,'interests':['unknown'],'accessibility_required':True})
 assert r.status_code==422
