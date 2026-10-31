from importlib import import_module
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
ALPHA_ROOT=ROOT.parents[1]
logic = import_module("tools.inventory-optimization-agent.app.logic")
backtest,recommend = logic.backtest,logic.recommend
import pandas as pd

@pytest.fixture(scope='module')
def df():
 subprocess.run([sys.executable,"-m","tools.inventory-optimization-agent.scripts.generate_data"],cwd=ALPHA_ROOT,check=True,capture_output=True)
 return pd.read_csv(ROOT/'data/generated/weekly_sales.csv',parse_dates=['week'])

def test_recommendation_is_bounded_and_requires_approval(df):
 r=recommend(df,'SKU-001',4,15,0)
 assert r['status']=='NEEDS_APPROVAL'
 assert r['suggested_replenishment_units']>=0

def test_no_recommendation_when_stock_position_is_sufficient(df):
 r=recommend(df,'SKU-001',1,10000,0)
 assert r['suggested_replenishment_units']==0

def test_unknown_policy_and_invalid_lead_time_fail(df):
 with pytest.raises(ValueError):recommend(df,'SKU-001',4,10,0,'automatic')
 with pytest.raises(ValueError):recommend(df,'SKU-001',0,10,0)

def test_backtest_has_temporal_horizon(df):
 r=backtest(df[df.sku=='SKU-001'])
 assert r['test_weeks']==8 and r['train_weeks']>r['test_weeks']
