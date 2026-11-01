from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from .forecast import data,forecast,backtest
app=FastAPI(title='Demand Forecasting',version='0.1.0')
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/api/forecast/{sku}')
def get_forecast(sku:str,horizon:int=8):
 try:return forecast(data(),sku,horizon)
 except FileNotFoundError as e:raise HTTPException(503,str(e)) from e
 except ValueError as e:raise HTTPException(422,str(e)) from e
@app.get('/api/backtest/{sku}')
def get_backtest(sku:str,horizon:int=8):
 try:return backtest(data(),sku,horizon)
 except FileNotFoundError as e:raise HTTPException(503,str(e)) from e
 except ValueError as e:raise HTTPException(422,str(e)) from e
@app.get('/',response_class=HTMLResponse)
def home():return """<!doctype html><html><head><meta charset=utf-8><title>Demand Forecasting</title></head><body style='font:16px system-ui;max-width:800px;margin:3rem auto'><h1>Demand Forecasting</h1><p>Generate the synthetic dataset, then inspect a forecast and temporal backtest. Forecast is a simple baseline.</p><p><a href='/api/forecast/SKU-001'>Forecast SKU-001</a> · <a href='/api/backtest/SKU-001'>Backtest</a></p></body></html>"""
