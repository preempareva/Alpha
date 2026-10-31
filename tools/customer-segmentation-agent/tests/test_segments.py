from importlib import import_module
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
ALPHA_ROOT=ROOT.parents[1]
run_segments = import_module("tools.customer-segmentation-agent.app.segments").run_segments

@pytest.fixture(scope='module',autouse=True)
def data():
 subprocess.run([sys.executable,"-m","tools.customer-segmentation-agent.scripts.generate_data"],cwd=ALPHA_ROOT,check=True,capture_output=True)

def test_profiles_are_aggregate_and_labeled_exploratory():
 r=run_segments(4)
 assert r['status']=='EXPLORATORY' and r['customers']==700
 assert len(r['segments'])==4
 assert 'customer_id' not in r['segments'][0]

def test_cluster_count_is_validated():
 with pytest.raises(ValueError):run_segments(1)
