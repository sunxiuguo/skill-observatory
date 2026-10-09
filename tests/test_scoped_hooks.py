"""User-level hook placement must never authorize the user's entire home."""
import json
from skill_observatory.cli import install_hooks, uninstall_hooks
from skill_observatory.store import Store
from skill_observatory.runtime import spool


def test_shared_hook_keeps_other_hooks_and_explicit_directory_boundary(tmp_path):
    home=tmp_path/'home'; target=home/'.codex/hooks.json'
    target.parent.mkdir(parents=True)
    previous=b'{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"existing-owner"}]}]}}'
    target.write_bytes(previous)
    scope=home/'privatecode'; scope.mkdir()
    store=Store(tmp_path/'state')
    install_hooks(store,home,scope)
    assert store.settings()['scopes']==[str(scope)]
    assert json.loads(target.read_bytes())['hooks']['Stop'][0]['hooks'][0]['command']=='existing-owner'
    event={'hook_event_name':'Stop','session_id':'fixture','turn_id':'fixture'}
    assert spool(store,{**event,'cwd':str(scope/'new-project')})['status']=='spooled'
    assert spool(store,{**event,'cwd':str(home/'workcode')})['status']=='excluded'
    assert spool(store,{**event,'cwd':str(home/'privatecode-other')})['status']=='excluded'
    installed=target.read_bytes()
    store.settings({'scopes':[]})
    assert install_hooks(store,home,scope)['status']=='already_installed'
    assert target.read_bytes()==installed and store.settings()['scopes']==[str(scope)]
    uninstall_hooks(store,home)
    assert target.read_bytes()==previous
