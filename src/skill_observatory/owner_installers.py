"""Thin original-installer adapter. No duplicated Skill write/rollback implementation."""
import json
from pathlib import Path
import subprocess
from .installations import validate_verdict
from .store import canonical,digest,now

class SkillEvolutionInstaller:
    owner='skill-evolution-loop'
    def __init__(self,executable='skill-evolution'):self.executable=executable
    def call(self,*args):
        r=subprocess.run([self.executable,*args],capture_output=True,text=True,timeout=30)
        if r.returncode:raise ValueError('OWNER_INSTALLER_HOLD')
        if args[0]=='show':
            marker='--- proposal.json ---\n'
            if marker not in r.stdout:raise ValueError('OWNER_PROPOSAL_MISSING')
            return {'proposal':json.JSONDecoder().raw_decode(r.stdout.split(marker,1)[1].lstrip())[0]}
        return json.loads(r.stdout)
    def apply(self,store,candidate_id):
        c=store.get('candidates',candidate_id)
        if not c:raise ValueError('CANDIDATE_NOT_FOUND')
        verdict=validate_verdict(store,store.get('verdicts',c['verdict_id']) or {})
        authority=store.get('authority_grants',c['authority_id'])
        if not authority or authority.get('status')!='authorized' or authority.get('owner')!=self.owner or authority.get('target')!=c['target'] or authority.get('surface')!='single_text_file' or (authority.get('expires_at') and authority['expires_at']<now()):raise ValueError('OWNER_AUTHORITY_HOLD')
        store.read_artifact(authority['evidence_sha256'])
        target=Path(c['target'])
        existing=store.get('installations','owner_inst_'+candidate_id)
        allowed={c['parent_sha256']}
        if existing and existing['status']=='owner_prepared':allowed.add(c['candidate_sha256'])
        if target.is_symlink() or target.name!='SKILL.md' or digest(target.read_bytes()) not in allowed:raise ValueError('DRIFT_HOLD')
        if verdict['parent_sha256']!=c['parent_sha256'] or verdict['candidate_sha256']!=c['candidate_sha256']:raise ValueError('VERDICT_BINDING_MISMATCH')
        incident=c['owner_incident_id'];snapshot=self.call('show',incident)
        proposal=snapshot.get('proposal') or {}
        if proposal.get('target')!=str(target.resolve()) or proposal.get('before_sha256')!=c['parent_sha256'] or proposal.get('candidate_sha256')!=c['candidate_sha256']:raise ValueError('OWNER_PROPOSAL_BINDING_HOLD')
        prepared={'id':'owner_inst_'+candidate_id,'owner':self.owner,'owner_incident_id':incident,'candidate_id':candidate_id,'target':str(target),'before_sha256':c['parent_sha256'],'after_sha256':c['candidate_sha256'],'status':'owner_prepared','activated':False,'live_verified':False,'created_at':now()}
        store.put('installations',prepared)
        # --allow-risk only acknowledges the matched human grant already checked above.
        result=self.call('apply',incident,'--allow-risk')
        if digest(target.read_bytes())!=c['candidate_sha256']:raise ValueError('OWNER_READBACK_FAILED')
        item={**prepared,'status':'activation_pending','owner_receipt_artifact':store.artifact(canonical(result))}
        store.put('installations',item);return item
    def rollback(self,store,installation):
        target=Path(installation['target'])
        if target.is_symlink() or digest(target.read_bytes())!=installation['after_sha256']:raise ValueError('DRIFT_HOLD')
        result=self.call('rollback',installation['owner_incident_id'])
        if digest(target.read_bytes())!=installation['before_sha256']:raise ValueError('OWNER_READBACK_FAILED')
        installation.update(status='rolled_back',updated_at=now());store.put('installations',installation);return installation
