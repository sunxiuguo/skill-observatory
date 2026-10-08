"""Versioned stdio app-server adapter. No credentials copied into the runner."""
from __future__ import annotations
import json
import queue
import subprocess
import threading
import time


class AppServer:
    def __init__(self, executable='codex', args=(), env=None):
        self.proc=subprocess.Popen([executable,'app-server','--stdio',*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
        self.messages=queue.Queue();self.notifications=[];self.id=0
        threading.Thread(target=self._read,daemon=True).start()
        self.request('initialize',{'clientInfo':{'name':'skill_observatory','title':'Skill Observatory','version':'0.1.0'}})
        self.send({'method':'initialized','params':{}})
    def _read(self):
        for line in self.proc.stdout:
            try:self.messages.put(json.loads(line))
            except json.JSONDecodeError:pass
    def send(self,value):
        self.proc.stdin.write(json.dumps(value)+'\n');self.proc.stdin.flush()
    def request(self,method,params,timeout=20):
        self.id+=1;id=self.id;self.send({'method':method,'id':id,'params':params});deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:m=self.messages.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:break
            if m.get('id')==id:
                if 'error' in m:raise ValueError('APP_SERVER_ERROR:'+str(m['error'].get('code'))+':'+str(m['error'].get('message')))
                return m['result']
            # No unsolicited tool approval is ever accepted by this discovery client.
            if 'id' in m and 'method' in m:self.send({'id':m['id'],'error':{'code':-32601,'message':'Tool execution is not authorized by discovery'}})
            else:self.notifications.append(m)
        raise TimeoutError('APP_SERVER_TIMEOUT')
    def close(self):
        self.proc.stdin.close()
        try:self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:self.proc.terminate();self.proc.wait(timeout=3)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def discover(cwd):
    with AppServer() as c:
        skills=c.request('skills/list',{'cwds':[cwd],'forceReload':True})
        hooks=c.request('hooks/list',{'cwd':cwd})
        return {'skills':skills,'hooks':hooks,'claim':'discovered_only_not_executed'}
