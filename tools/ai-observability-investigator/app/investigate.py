from datetime import datetime, timedelta

EVENTS=[
 {'incident':'INC-100','time':'2026-10-20T10:00:00Z','service':'checkout','kind':'metric','name':'error_rate','value':0.18},
 {'incident':'INC-100','time':'2026-10-20T10:01:00Z','service':'checkout','kind':'log','name':'payment_timeout','value':'gateway timeout'},
 {'incident':'INC-100','time':'2026-10-20T10:02:00Z','service':'payments','kind':'trace','name':'charge_authorization','value':'p95 4.2s'},
 {'incident':'INC-100','time':'2026-10-20T09:40:00Z','service':'catalog','kind':'metric','name':'request_rate','value':120},
 {'incident':'INC-101','time':'2026-10-21T08:00:00Z','service':'search','kind':'metric','name':'latency_p95','value':3.8},
 {'incident':'INC-101','time':'2026-10-21T08:02:00Z','service':'search','kind':'log','name':'cache_miss_spike','value':'cache hit rate fell'},
]

def investigate(incident_id:str):
 matches=[e for e in EVENTS if e['incident']==incident_id]
 if not matches:raise KeyError('Incident not found in synthetic event set.')
 times=[datetime.fromisoformat(e['time'].replace('Z','+00:00')) for e in matches]
 services=sorted({e['service'] for e in matches})
 signals=[e for e in matches if e['kind']=='metric' and (('error' in e['name'] and float(e['value'])>.05) or ('latency' in e['name'] and float(e['value'])>1.0))]
 if any(e['service']=='checkout' for e in signals):
  hypothesis='Checkout error spike aligns with payment authorization latency and gateway timeouts.'
  next_steps=['Inspect payment gateway health and timeout configuration.','Compare traces before and after the incident start.','Check recent deployment changes; do not roll back automatically.']
 else:
  hypothesis='Search latency increase aligns with a cache miss spike.'
  next_steps=['Check cache service health and recent invalidations.','Compare search latency by route and dependency.','Avoid changing cache policy until an operator reviews evidence.']
 return {'incident_id':incident_id,'status':'INVESTIGATION_DRAFT','window_start':min(times).isoformat(),'window_end':max(times).isoformat(),'services':services,'evidence':matches,'hypothesis':hypothesis,'recommended_next_steps':next_steps,'notice':'Synthetic telemetry; hypothesis only. No infrastructure action was taken.'}
