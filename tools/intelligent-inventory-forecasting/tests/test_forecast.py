from importlib import import_module
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
ALPHA_ROOT=ROOT.parents[1]
forecast_module = import_module("tools.intelligent-inventory-forecasting.app.forecast")
data,forecast,backtest = forecast_module.data,forecast_module.forecast,forecast_module.backtest

def test_forecast_intervals_and_horizon():
 subprocess.run([sys.executable,"-m","tools.intelligent-inventory-forecasting.scripts.generate_data"],cwd=ALPHA_ROOT,check=True,capture_output=True)
 df=data();r=forecast(df,'SKU-001',8)
 assert len(r['forecast'])==8
 assert all(x['p10']<=x['p50']<=x['p90'] for x in r['forecast'])

def test_backtest_reports_naive_comparison():
 r=backtest(data(),'SKU-001')
 assert r['test_weeks']==8 and r['mean_baseline_mae']>=0
