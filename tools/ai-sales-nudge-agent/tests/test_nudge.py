import os
from importlib import import_module
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
os.environ['NUDGE_DB']=str(ROOT/'instance/test.db')
module = import_module("tools.ai-sales-nudge-agent.app.main")
app, init = module.app, module.init

@pytest.fixture(autouse=True)
def setup():
 p=ROOT/'instance/test.db'
 if p.exists():p.unlink()
 init();yield
 if p.exists():p.unlink()

def test_suggestions_are_drafts_only():
 r=TestClient(app).get('/api/leads').json()['items']
 assert all(x['status']=='DRAFT_ONLY' for x in r)

def test_approval_does_not_send_and_cannot_repeat():
 c=TestClient(app);d=c.post('/api/drafts',json={'lead_id':'SYN-LEAD-01','message':'Would a proposal review be helpful?'}).json()
 assert c.post(f"/api/drafts/{d['draft_id']}/approve").json()['status']=='APPROVED'
 assert c.post(f"/api/drafts/{d['draft_id']}/approve").status_code==404
