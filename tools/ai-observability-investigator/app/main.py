from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from .investigate import investigate
app=FastAPI(title='Incident Evidence Correlator (synthetic)',version='0.1.0')
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/api/incidents/{incident_id}')
def get_incident(incident_id:str):
 try:return investigate(incident_id)
 except KeyError as e:raise HTTPException(404,str(e)) from e
@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Incident Evidence Correlator (synthetic)</title><style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem}button{padding:.6rem;background:#164e63;color:white;border:0;border-radius:5px}pre{white-space:pre-wrap;background:#f1f4f5;padding:1rem}</style></head><body><h1>Incident Evidence Correlator (synthetic)</h1><p>Synthetic metrics/logs/traces, correlated by incident. Recommendations are read-only.</p><button onclick="load('INC-100')">Payment timeout sample</button> <button onclick="load('INC-101')">Search latency sample</button><pre id=o></pre><script>async function load(id){o.textContent=JSON.stringify(await(await fetch('/api/incidents/'+id)).json(),null,2)}</script></body></html>"""
