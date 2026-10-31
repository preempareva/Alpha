from importlib import import_module
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from fastapi.testclient import TestClient
app = import_module("tools.ai-supplier-quote-comparison.app.main").app
C=TestClient(app)
BASE={'quotes':[{'supplier':'A','unit_price':10,'quantity':10,'currency':'USD','freight':10,'tax_percent':5,'lead_time_days':10,'quality_score':90,'compliance_confirmed':True},{'supplier':'B','unit_price':9,'quantity':10,'currency':'USD','freight':30,'tax_percent':5,'lead_time_days':20,'quality_score':70,'compliance_confirmed':True}]}

def test_cost_breakdown_and_analyst_review():
 r=C.post('/api/compare',json=BASE).json()
 assert r['status']=='ANALYST_REVIEW' and r['quotes'][0]['estimated_landed_cost']>0
 assert 'no supplier is selected' in r['notice']

def test_currency_mismatch_is_rejected():
 p={'quotes':[dict(BASE['quotes'][0]),dict(BASE['quotes'][1],currency='INR')]}
 assert C.post('/api/compare',json=p).status_code==422

def test_missing_terms_are_not_guessed():
 q=dict(BASE['quotes'][0],freight=None,tax_percent=None)
 r=C.post('/api/compare',json={'quotes':[q,BASE['quotes'][1]]}).json()
 first=next(x for x in r['quotes'] if x['supplier']=='A')
 assert first['status']=='NEEDS_REVIEW' and 'freight' in first['missing_terms']

def test_score_weights_must_sum_to_one():
 p=dict(BASE,price_weight=.8,delivery_weight=.5,quality_weight=.2)
 assert C.post('/api/compare',json=p).status_code==422
