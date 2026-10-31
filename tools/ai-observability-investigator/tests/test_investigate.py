from importlib import import_module
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
investigate = import_module("tools.ai-observability-investigator.app.investigate").investigate

def test_incident_correlates_cross_service_evidence():
 r=investigate('INC-100')
 assert r['status']=='INVESTIGATION_DRAFT'
 assert {'checkout','payments'}<=set(r['services'])
 assert 'gateway timeouts' in r['hypothesis']
 assert 'No infrastructure action' in r['notice']

def test_unknown_incident_is_not_guessed():
 with pytest.raises(KeyError):investigate('INC-999')
