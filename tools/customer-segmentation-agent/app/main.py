from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from .segments import run_segments
app=FastAPI(title='Customer Segmentation',version='0.1.0')
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/api/segments')
def segments(k:int=4):
 try:return run_segments(k)
 except FileNotFoundError as e:raise HTTPException(503,str(e)) from e
 except ValueError as e:raise HTTPException(422,str(e)) from e
@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><title>Customer Segmentation</title></head><body style='font:16px system-ui;max-width:800px;margin:3rem auto'><h1>Customer Segmentation</h1><p>Segments are descriptive patterns in synthetic transaction data, not natural customer types or targeting instructions.</p><p>Run the data generator, then open <a href='/api/segments'>/api/segments</a> to inspect aggregate RFM profiles.</p></body></html>"""
