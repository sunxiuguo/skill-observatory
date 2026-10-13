import json
from fastapi.testclient import TestClient
from skill_observatory.store import Store
from skill_observatory.api import create_app,summary


def test_summary_pagination_filters_detail_and_revision(tmp_path):
 s=Store(tmp_path/'state')
 with s.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  for n in range(120):
   s.put('runs',{'id':f'r{n:03}','session_id':'s','turn_id':str(n),'created_at':f'2026-10-13T02:{n//60:02}:{n%60:02}+00:00','status':'ready','cwd':'fixture-project','event_ids':['x'*64]*800,'attributions':[]},db)
  s.put('capability_invocations',{'id':'i','capability_id':'cap','stages':['executed'],'origin':'activation_canary','created_at':'now','cwd':'fixture-project'},db)
 with TestClient(create_app(s,daemon=False),base_url='http://127.0.0.1') as c:
  c.get('/api/session')
  result=c.get('/api/summary').json()
  assert len(result['runs'])==50 and result['metrics']['observed_runs']==120
  assert result['pagination']['runs']['total']==120
  assert all('event_ids' not in r for r in result['runs'])
  assert result['lifecycle_metrics']['stage_counts']['executed']==1
  assert len(json.dumps(result))<50000
  page=c.get('/api/entities/runs?offset=12&limit=12&order=oldest').json()
  assert page['total']==120 and page['items'][0]['id']=='r012'
  detail=c.get('/api/entities/runs/r119').json();assert len(detail['event_ids'])==800
  assert c.get('/api/entities/runs?query=r119').json()['total']==1
  assert c.get('/api/entities/runs?query=%25').json()['total']==0
  assert c.get('/api/entities/runs?bucket=ready').json()['total']==120
  assert c.get('/api/entities/runs?bucket=held').json()['total']==0
  assert c.get('/api/entities/capability_invocations?stage=executed&canary=only').json()['total']==1
  assert c.get('/api/entities/authority_grants').status_code==422
  assert c.get('/api/entities/authority_grants/secret').status_code==404
  assert c.get('/api/entities/runs?limit=51').status_code==422
  csrf=c.get('/api/session').json()['csrf']
  assert c.post('/api/settings',json={'paused':True},headers={'x-csrf-token':csrf}).status_code==200
  newer=c.get('/api/summary').json();assert newer['revision']>result['revision'] and newer['settings']['paused'] is True
