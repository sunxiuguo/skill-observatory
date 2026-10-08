"""User launchd lifecycle with content-hash ownership and reversible uninstall."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
from .store import atomic_write,digest,now

LABEL='org.skill-observatory.runtime'

def service(store,action,port=8765,web_root=None):
    if sys.platform!='darwin':raise ValueError('LAUNCHD_UNAVAILABLE_USE_FOREGROUND_DAEMON')
    target=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    domain=f'gui/{os.getuid()}';ref=domain+'/'+LABEL
    receipt=store.get('service_installations',LABEL)
    def current():
        if target.is_symlink():raise ValueError('SERVICE_DRIFT_HOLD')
        if not receipt or not target.exists() or digest(target.read_bytes())!=receipt['after_sha256']:raise ValueError('SERVICE_DRIFT_HOLD')
    def launch(*args):
        p=subprocess.run(['launchctl',*args],capture_output=True,text=True,timeout=15)
        return p
    def stop():
        launch('bootout',ref)
        deadline=time.monotonic()+10
        while launch('print',ref).returncode==0:
            if time.monotonic()>deadline:raise ValueError('SERVICE_STOP_NOT_CONFIRMED')
            time.sleep(.1)
    if action=='service-install':
        args=[sys.executable,'-m','skill_observatory.cli','--state',str(store.root),'serve','--port',str(port)]
        if web_root:args+=['--web-root',str(Path(web_root).resolve())]
        data=plistlib.dumps({'Label':LABEL,'ProgramArguments':args,'RunAtLoad':True,'KeepAlive':True,'WorkingDirectory':str(store.root),'StandardOutPath':str(store.root/'service.stdout.log'),'StandardErrorPath':str(store.root/'service.stderr.log'),'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin')}})
        before=target.read_bytes() if target.exists() else None
        if receipt and receipt['status']=='uninstalled':
            actual=digest(before) if before is not None else None
            if actual!=receipt['before_sha256']:raise ValueError('SERVICE_DRIFT_HOLD')
        elif receipt:current()
        elif before:raise ValueError('EXISTING_SERVICE_OWNER_REQUIRED')
        if receipt and before==data:return receipt
        if receipt:stop()
        receipt={'id':LABEL,'target':str(target),'before_sha256':receipt.get('before_sha256') if receipt else (store.artifact(before) if before else None),'after_sha256':store.artifact(data),'created_at':now(),'status':'prepared'}
        store.put('service_installations',receipt);atomic_write(target,data)
        if digest(target.read_bytes())!=receipt['after_sha256']:raise ValueError('SERVICE_READBACK_FAILED')
        receipt['status']='installed';store.put('service_installations',receipt)
        p=launch('bootstrap',domain,str(target))
        if p.returncode:raise ValueError('SERVICE_BOOTSTRAP_FAILED:'+str(p.returncode))
        return receipt
    if action=='service-status':
        p=launch('print',ref);return {'installed':bool(receipt),'loaded':p.returncode==0,'claim':'loaded_not_business_verified'}
    current()
    if action=='service-start':
        if launch('print',ref).returncode:
            if launch('bootstrap',domain,str(target)).returncode:raise ValueError('SERVICE_BOOTSTRAP_FAILED')
        p=launch('kickstart',ref)
        if p.returncode:raise ValueError('SERVICE_START_FAILED')
    elif action=='service-stop':stop()
    elif action=='service-uninstall':
        stop()
        if receipt['before_sha256']:atomic_write(target,store.read_artifact(receipt['before_sha256']))
        else:target.unlink()
        receipt['status']='uninstalled';store.put('service_installations',receipt)
    return {'status':action.removeprefix('service-'),'state_retained':True}
