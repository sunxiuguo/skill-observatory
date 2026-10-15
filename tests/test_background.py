import json
import pytest
import urllib.request
import urllib.error
from skill_observatory.background import ToolFreeGuard


def send(base,value):
    return urllib.request.urlopen(urllib.request.Request(base+'/responses',data=json.dumps(value).encode(),headers={'Content-Type':'application/json'}),timeout=3)


def test_default_guard_refuses_tools_before_upstream():
    with ToolFreeGuard('https://example.invalid/v1','model') as guard:
        try:send(guard.base_url,{'model':'model','tools':[{'name':'shell'}]})
        except urllib.error.HTTPError as ex:assert ex.code==403
    assert len(guard.receipts)==1 and guard.receipts[0]['forwarded'] is False


def test_explicit_profile_maps_only_tool_fields(monkeypatch):
    captured=[]
    class Response:
        status=200
        def getheader(self,*args):return 'application/json'
        def read1(self,*args):
            if getattr(self,'done',False):return b''
            self.done=True;return b'{"ok":true}'
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,method,path,body,headers):captured.append((method,path,json.loads(body),headers))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr('skill_observatory.background.http.client.HTTPSConnection',Connection)
    original={'model':'model','input':[{'role':'user','content':'bounded facts'}],'tools':[{'name':'view_image'}],'tool_choice':'auto'}
    with ToolFreeGuard('https://example.invalid/v1','model',empty_catalog=True) as guard:
        with send(guard.base_url,original) as result:assert result.status==200
    assert len(captured)==1
    assert captured[0][1]=='/v1/responses'
    assert captured[0][2]['input']==original['input'] and captured[0][2]['model']==original['model']
    assert captured[0][2]['tools']==[] and captured[0][2]['tool_choice']=='none'
    assert guard.receipts[0]['source_tool_count']==1 and guard.receipts[0]['tool_count']==0


def test_empty_catalog_does_not_admit_wrong_model():
    with ToolFreeGuard('https://example.invalid/v1','expected',empty_catalog=True) as guard:
        try:send(guard.base_url,{'model':'wrong','tools':[]})
        except urllib.error.HTTPError as ex:assert ex.code==403
    assert guard.receipts[0]['model_matches'] is False


def test_owner_hold_is_not_overridden_by_transport_qualification(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from skill_observatory import configuration
    from skill_observatory.store import Store
    store=Store(tmp_path/'state')
    reviewer=SimpleNamespace(transport_certification={'verified':True,'proof_sha256':'a'*64},
        execution_hold='BACKGROUND_SEMANTIC_INTEGRATION_HOLD')
    monkeypatch.setattr(configuration,'_owner',lambda *args:(SimpleNamespace(make_reviewer=lambda:reviewer),{'owner_sha256':'b'*64}))
    import pytest
    from skill_observatory.reviewer import ReviewDeferred
    held=configuration.load_reviewer(store,isolated=False)
    with pytest.raises(ReviewDeferred,match='BACKGROUND_SEMANTIC_INTEGRATION_HOLD'):
        held.review(store,{'id':'no_dispatch'})
    state=store.get('runtime','reviewer')
    assert state['status']=='semantic_integration_hold'
    assert state['transport_certification']['verified'] is True
    assert state['execution_hold']=='BACKGROUND_SEMANTIC_INTEGRATION_HOLD'


def test_guard_records_request_wait_and_rejects_bad_size_without_upstream():
    with ToolFreeGuard('https://example.invalid/v1','model') as guard:
        try:
            urllib.request.urlopen(urllib.request.Request(guard.base_url+'/responses',data=b'{}',headers={'Content-Length':'broken'}),timeout=3)
        except urllib.error.HTTPError as error:assert error.code==413
    assert guard.receipts[0]['reason_code']=='BACKGROUND_REQUEST_SIZE_REFUSED'
    assert guard.receipts[0]['forwarded'] is False


def test_guard_timeout_has_phase_and_uses_explicit_deadline(monkeypatch):
    captured=[]
    class Connection:
        def __init__(self,*args,**kwargs):captured.append(kwargs['timeout'])
        def request(self,*args,**kwargs):pass
        def getresponse(self):raise TimeoutError('must not persist private upstream details')
        def close(self):pass
    monkeypatch.setattr('skill_observatory.background.http.client.HTTPSConnection',Connection)
    with ToolFreeGuard('https://example.invalid/v1','model',timeout=300) as guard:
        try:send(guard.base_url,{'model':'model','tools':[]})
        except urllib.error.HTTPError as error:assert error.code==504
    row=guard.receipts[0]
    assert captured==[300]
    assert row['failed_phase']=='awaiting_headers' and row['reason_code']=='BACKGROUND_TRANSPORT_TIMEOUT'
    assert 'private' not in json.dumps(row)


@pytest.mark.parametrize('transport_verified',[False,True])
def test_schema_canary_status_requires_transport_proof(tmp_path,monkeypatch,transport_verified):
    from types import SimpleNamespace
    from skill_observatory import configuration
    from skill_observatory.store import Store
    s=Store(tmp_path/'state');reviewer=SimpleNamespace(transport_certification={'verified':transport_verified,'proof_sha256':'a'*64},
        semantic_certification={'verified':True,'proof_sha256':'b'*64})
    monkeypatch.setattr(configuration,'_owner',lambda *args:(SimpleNamespace(make_reviewer=lambda:reviewer),{'owner_sha256':'c'*64}))
    configuration.load_reviewer(s,isolated=False)
    row=s.get('runtime','reviewer')
    assert row['status']==('owner_verified_schema_review' if transport_verified else 'configured_not_certified')
