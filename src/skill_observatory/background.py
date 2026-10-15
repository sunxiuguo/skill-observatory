"""Per-context tool-free wire guard for a trusted owner's existing transport.

No provider discovery, credentials, routing or certification is implemented here.
The owner pins its upstream and exact model. The default refuses tool catalogs.
An explicit empty-catalog profile maps the runtime's built-ins to tools=[] and
tool_choice=none; receipts retain the input count and the enforced wire count.
"""
from __future__ import annotations
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit


class ToolFreeGuard:
    def __init__(self,upstream,model,*,empty_catalog=False):
        self.upstream=urlsplit(upstream);self.model=model;self.receipts=[]
        if self.upstream.scheme!='https' or self.upstream.username or self.upstream.password or self.upstream.query or self.upstream.fragment:
            raise ValueError('BACKGROUND_UPSTREAM_INVALID')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=128000:self.send_error(413);return
                raw=self.rfile.read(size)
                try:
                    body=json.loads(raw)
                    if not isinstance(body,dict) or body.get('model')!=owner.model:raise ValueError()
                    tools=body.get('tools',[])
                    if tools not in (None,[]) and not empty_catalog:raise ValueError()
                    if self.path not in {'/responses','/chat/completions'}:raise ValueError()
                except (ValueError,TypeError):
                    candidates=body.get('tools',[]) if isinstance(locals().get('body'),dict) else []
                    names=[str(t.get('name') or t.get('function',{}).get('name') or t.get('type'))[:100] for t in candidates[:20] if isinstance(t,dict)] if isinstance(candidates,list) else []
                    owner.receipts.append({'forwarded':False,'reason_code':'BACKGROUND_TOOL_OR_MODEL_REFUSED',
                        'tool_count':len(candidates) if isinstance(candidates,list) else None,'tool_names':names,'model_matches':isinstance(locals().get('body'),dict) and body.get('model')==owner.model,'path_allowed':self.path in {'/responses','/chat/completions'}})
                    self.send_error(403,'BACKGROUND_TOOL_OR_MODEL_REFUSED');return
                connection=http.client.HTTPSConnection(owner.upstream.hostname,owner.upstream.port or 443,timeout=120)
                try:
                    source_tool_count=len(body.get('tools') or [])
                    if empty_catalog:
                        body['tools']=[];body['tool_choice']='none'
                        raw=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
                    headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','connection','transfer-encoding','content-length'}}
                    headers['Content-Length']=str(len(raw));headers['Accept-Encoding']='identity'
                    connection.request('POST',owner.upstream.path.rstrip('/')+self.path,body=raw,headers=headers)
                    response=connection.getresponse()
                    owner.receipts.append({'forwarded':True,'model':owner.model,'source_tool_count':source_tool_count,
                        'tool_count':0,'tool_policy':'explicit_empty_catalog' if empty_catalog else 'reject_nonempty','status':response.status})
                    self.send_response(response.status)
                    self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
                    self.send_header('Connection','close');self.end_headers();self.close_connection=True
                    while True:
                        chunk=response.read1(65536)
                        if not chunk:break
                        self.wfile.write(chunk);self.wfile.flush()
                except (OSError,http.client.HTTPException):
                    owner.receipts.append({'forwarded':True,'reason_code':'BACKGROUND_TRANSPORT_INCOMPLETE'})
                finally:connection.close()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    @property
    def base_url(self):return 'http://127.0.0.1:'+str(self.server.server_port)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
