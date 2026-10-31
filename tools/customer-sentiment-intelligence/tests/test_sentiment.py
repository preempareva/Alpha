import os
from pathlib import Path
from importlib import import_module
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
os.environ['SENTIMENT_MODEL']=str(ROOT/'artifacts/sentiment.joblib')
app = import_module("tools.customer-sentiment-intelligence.app.main").app

def test_review_analysis_has_bounded_outputs():
 r=TestClient(app).post('/api/analyze',json={'text':'The desk lamp quality is excellent and delivery was fast.'})
 assert r.status_code==200
 assert r.json()['sentiment'] in {'positive','negative','neutral'}
 assert 'quality' in r.json()['themes']

def test_api_rejects_too_short_text():
 assert TestClient(app).post('/api/analyze',json={'text':'no'}).status_code==422
