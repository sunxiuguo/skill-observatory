import plistlib
from pathlib import Path
from types import SimpleNamespace
from skill_observatory.store import Store,digest
from skill_observatory import service as owner


def test_stop_waits_for_original_process_after_launch_label_is_gone(tmp_path,monkeypatch):
    s=Store(tmp_path/'state');home=tmp_path/'home'
    target=home/'Library/LaunchAgents'/f'{owner.LABEL}.plist';target.parent.mkdir(parents=True);target.write_bytes(plistlib.dumps({'Label':owner.LABEL}))
    s.put('service_installations',{'id':owner.LABEL,'after_sha256':digest(target.read_bytes()),'status':'installed'})
    monkeypatch.setattr(owner.sys,'platform','darwin');monkeypatch.setattr(owner.Path,'home',lambda:home)
    calls=[];identities=iter(['original-start','original-start',None])
    monkeypatch.setattr(owner,'process_identity',lambda pid:next(identities))
    def launch(args,**kwargs):
        calls.append(args)
        first=len(calls)==1
        return SimpleNamespace(returncode=0 if first or args[1]=='bootout' else 1,stdout=' pid = 123\n' if first else '')
    monkeypatch.setattr(owner.subprocess,'run',launch);wait=[];monkeypatch.setattr(owner.time,'sleep',lambda value:wait.append(value))
    assert owner.service(s,'service-stop')['status']=='stop'
    assert len(wait)==1
