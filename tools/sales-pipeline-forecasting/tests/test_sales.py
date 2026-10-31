import subprocess,sys
from importlib import import_module
from pathlib import Path
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
ALPHA_ROOT = ROOT.parents[1]
subprocess.run([sys.executable,"-m","tools.sales-pipeline-forecasting.scripts.generate_data"],cwd=ALPHA_ROOT,check=True,capture_output=True)
subprocess.run([sys.executable,"-m","tools.sales-pipeline-forecasting.scripts.train"],cwd=ALPHA_ROOT,check=True,capture_output=True)
app = import_module("tools.sales-pipeline-forecasting.app.main").app
C=TestClient(app)

def test_score_returns_probability_and_weighted_value():
 r=C.post('/api/score',json={'opportunity_id':'SYN-X','amount':10000,'age_days':40,'stage':'proposal','touches_30d':5,'stakeholder_count':3})
 assert r.status_code==200
 d=r.json();assert 0<=d['win_probability']<=1 and d['weighted_pipeline_value']>=0

def test_validation_rejects_negative_amount():
 assert C.post('/api/score',json={'opportunity_id':'X','amount':-1,'age_days':40,'stage':'proposal','touches_30d':5,'stakeholder_count':3}).status_code==422
