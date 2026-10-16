"""Thin original-installer adapter. No duplicated Skill write/rollback implementation."""
import json
from pathlib import Path
import subprocess
from .installations import validate_verdict,authority_expired
from .store import canonical,digest,now

class SkillEvolutionInstaller:
    owner='skill-evolution-loop'
    def __init__(self,executable='skill-evolution'):self.executable=executable
    def call(self,*args):
        r=subprocess.run([self.executable,*args],capture_output=True,text=True,timeout=30)
        if r.returncode:raise ValueError('OWNER_INSTALLER_HOLD')
        if args[0]=='show':
            result={}
            for name in ('proposal','application','package_proposal','package_application'):
                marker='--- '+name+'.json ---\n'
                if marker in r.stdout:result[name]=json.JSONDecoder().raw_decode(r.stdout.split(marker,1)[1].lstrip())[0]
            if not result:raise ValueError('OWNER_PROPOSAL_MISSING')
            return result
        return json.loads(r.stdout)
    def apply(self,store,candidate_id):
        c=store.get('candidates',candidate_id)
        if not c:raise ValueError('CANDIDATE_NOT_FOUND')
        if c.get('parent_package') or c.get('candidate_package'):
            return self.apply_package(store,c)
        verdict=validate_verdict(store,store.get('verdicts',c['verdict_id']) or {})
        from .final_gate import assert_current_final
        assert_current_final(store,verdict)
        authority=store.get('authority_grants',c['authority_id'])
        if not authority or authority.get('status')!='authorized' or authority.get('owner')!=self.owner or authority.get('target')!=c['target'] or authority.get('surface')!='single_text_file' or authority_expired(authority.get('expires_at')):raise ValueError('OWNER_AUTHORITY_HOLD')
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
        item={**prepared,'status':'activation_pending','applied_at':now(),'owner_receipt_artifact':store.artifact(canonical(result))}
        store.put('installations',item);return item
    def rollback(self,store,installation):
        if installation.get('after_package'):return self.rollback_package(store,installation)
        target=Path(installation['target'])
        allowed={installation['after_sha256']}
        if installation['status']=='owner_rollback_prepared':allowed.add(installation['before_sha256'])
        if target.is_symlink() or digest(target.read_bytes()) not in allowed:raise ValueError('DRIFT_HOLD')
        installation.update(status='owner_rollback_prepared',updated_at=now())
        store.put('installations',installation)
        result=self.call('rollback',installation['owner_incident_id'])
        if digest(target.read_bytes())!=installation['before_sha256']:raise ValueError('OWNER_READBACK_FAILED')
        installation.update(status='rolled_back',updated_at=now(),rollback_receipt_artifact=store.artifact(canonical(result)))
        store.put('installations',installation);return installation


    def package_available(self):
        try:r=subprocess.run([self.executable,'--help'],capture_output=True,text=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):return False
        return r.returncode==0 and all(x in r.stdout for x in ('package-propose','package-apply','package-rollback'))

    def apply_package(self,store,c):
        from .packages import snapshot_package,changed_files
        if not self.package_available():raise ValueError('OWNER_PACKAGE_TRANSACTION_UNAVAILABLE')
        verdict=validate_verdict(store,store.get('verdicts',c['verdict_id']) or {})
        from .final_gate import assert_current_final
        assert_current_final(store,verdict)
        grant=store.get('authority_grants',c['authority_id']) or {}
        root=c['target']
        if grant.get('status')!='authorized' or grant.get('owner')!=self.owner or grant.get('surface')!='package' or grant.get('target')!=root or authority_expired(grant.get('expires_at')):raise ValueError('OWNER_PACKAGE_AUTHORITY_HOLD')
        before=c['parent_package'];after=c['candidate_package']
        changed=changed_files(store,before,after,grant.get('changed_files',[]))
        for side,manifest in (('parent',before),('candidate',after)):
            if grant.get(side+'_package_digest')!=manifest['package_digest'] or verdict.get(side+'_package_digest')!=manifest['package_digest']:raise ValueError('OWNER_PACKAGE_BINDING_DRIFT')
        store.read_artifact(grant['evidence_sha256'])
        original=self.call('show',c['owner_incident_id']).get('package_proposal') or {}
        if original.get('target_root')!=root or original.get('before_manifest')!=before or original.get('after_manifest')!=after or original.get('changed_files')!=changed:raise ValueError('OWNER_PACKAGE_PROPOSAL_DRIFT')
        existing=store.get('installations','owner_inst_'+c['id'])
        current=snapshot_package(store,root)
        if current!=before and not (existing and existing['status']=='owner_prepared' and current==after):raise ValueError('DRIFT_HOLD')
        prepared={'id':'owner_inst_'+c['id'],'owner':self.owner,'owner_incident_id':c['owner_incident_id'],'candidate_id':c['id'],
                  'target_root':root,'target':str(Path(root)/'SKILL.md'),'before_package':before,'after_package':after,
                  'before_sha256':c['parent_sha256'],'after_sha256':c['candidate_sha256'],'changed_files':changed,
                  'status':'owner_prepared','activated':False,'live_verified':False,'created_at':existing.get('created_at') if existing else now()}
        store.put('installations',prepared)
        result=self.call('package-apply',c['owner_incident_id'],'--allow-risk')
        if result.get('status')!='applied' or not result.get('applied_at') or snapshot_package(store,root)!=after:raise ValueError('OWNER_PACKAGE_READBACK_FAILED')
        return store.put('installations',{**prepared,'status':'activation_pending','applied_at':now(),'owner_applied_at':result['applied_at'],'owner_receipt_artifact':store.artifact(canonical(result))})

    def rollback_package(self,store,installation):
        from .packages import snapshot_package
        current=snapshot_package(store,installation['target_root'])
        allowed=[installation['after_package']]
        if installation['status']=='owner_rollback_prepared':allowed.append(installation['before_package'])
        if current not in allowed:raise ValueError('DRIFT_HOLD')
        installation.update(status='owner_rollback_prepared',updated_at=now());store.put('installations',installation)
        result=self.call('package-rollback',installation['owner_incident_id'])
        if result.get('status')!='rolled_back' or snapshot_package(store,installation['target_root'])!=installation['before_package']:raise ValueError('OWNER_PACKAGE_READBACK_FAILED')
        installation.update(status='rolled_back',updated_at=now(),rollback_receipt_artifact=store.artifact(canonical(result)))
        return store.put('installations',installation)


def prepare_package_change(store,value,installer=None):
    """Freeze a complete owner request; never emulate a package with file writes."""
    from .packages import read_package,changed_files,snapshot_package
    required={'id','owner','target_root','parent_package','candidate_package','changed_files','authority_id'}
    if set(value)!=required:raise ValueError('OWNER_PACKAGE_REQUEST_INVALID')
    grant=store.get('authority_grants',value['authority_id'])
    if not grant or grant.get('status')!='authorized' or grant.get('owner')!=value['owner'] or grant.get('surface')!='package' or grant.get('target')!=value['target_root'] or authority_expired(grant.get('expires_at')):
        raise ValueError('OWNER_PACKAGE_AUTHORITY_HOLD')
    store.read_artifact(grant['evidence_sha256'])
    changed_files(store,value['parent_package'],value['candidate_package'],value['changed_files'])
    if grant.get('changed_files')!=value['changed_files'] or grant.get('parent_package_digest')!=value['parent_package']['package_digest'] or grant.get('candidate_package_digest')!=value['candidate_package']['package_digest']:
        raise ValueError('OWNER_PACKAGE_AUTHORITY_BINDING_DRIFT')
    if snapshot_package(store,value['target_root'])!=value['parent_package']:raise ValueError('OWNER_PACKAGE_PARENT_DRIFT')
    available=(installer or SkillEvolutionInstaller()).package_available()
    row={**value,'schema_version':2,'status':'prepared' if available else 'blocked','reason_code':None if available else 'OWNER_PACKAGE_TRANSACTION_UNAVAILABLE',
         'request_sha256':store.artifact(canonical(value)),'automatic_apply':False}
    old=store.get('owner_package_requests',value['id'])
    if old and old!=row:raise ValueError('OWNER_PACKAGE_REQUEST_COLLISION')
    return old or store.put('owner_package_requests',row)


def import_engineering_repair(store,value):
    """Readback only: managed history never becomes independent gain/activation."""
    required={'id','owner','incident_id','incident_sha256','transaction_sha256','version_id','target','actual_sha256','run_id'}
    if set(value)!=required:raise ValueError('ENGINEERING_REPAIR_INPUT_INVALID')
    incident=json.loads(store.read_artifact(value['incident_sha256']))
    transaction=json.loads(store.read_artifact(value['transaction_sha256']))
    run=store.get('runs',value['run_id'])
    if incident.get('id')!=value['incident_id'] or not run or incident.get('project')!=run.get('cwd'):raise ValueError('ENGINEERING_REPAIR_SOURCE_DRIFT')
    version=store.get('capability_versions',value['version_id'])
    cap=store.get('capability_catalog',version['capability_id']) if version else None
    if not version or not cap or cap['name'] not in incident.get('skills',[]) or value['actual_sha256'] not in version['manifest']['files'].values():raise ValueError('ENGINEERING_REPAIR_VERSION_DRIFT')
    target=Path(value['target'])
    if target.resolve()!=(Path(cap['path'])/'SKILL.md').resolve():raise ValueError('ENGINEERING_REPAIR_TARGET_DRIFT')
    if target.is_symlink() or not target.is_file() or digest(target.read_bytes())!=value['actual_sha256']:raise ValueError('ENGINEERING_REPAIR_READBACK_DRIFT')
    changes=transaction.get('changes') or []
    matching=[x for x in changes if x.get('target')==str(target.resolve()) and x.get('after_sha256')==value['actual_sha256']]
    if transaction.get('status') not in {'installed','applied'} or len(matching)!=1 or matching[0].get('before_sha256')==matching[0].get('after_sha256'):raise ValueError('ENGINEERING_REPAIR_TRANSACTION_DRIFT')
    from datetime import datetime
    try:
        at=datetime.fromisoformat(transaction.get('applied_at') or transaction['activated_at'])
        if not datetime.fromisoformat(run['first_source_at'])<=at<=datetime.fromisoformat(run['updated_at']):raise ValueError()
    except (KeyError,ValueError,TypeError):raise ValueError('ENGINEERING_REPAIR_RUN_WINDOW_DRIFT')
    backup=Path(matching[0]['backup'])
    if backup.is_symlink() or not backup.is_file() or digest(backup.read_bytes())!=matching[0]['before_sha256']:raise ValueError('ENGINEERING_REPAIR_BACKUP_DRIFT')
    row={**value,'status':'engineering_verified','independently_improved':False,'activated':False,'applied_at':transaction.get('applied_at'),
         'historical_transaction_at':transaction.get('activated_at'),'missing':[] if transaction.get('applied_at') else ['INSTALLATION_APPLY_TIME_REQUIRED']}
    old=store.get('engineering_repairs',value['id'])
    if old and old!=row:raise ValueError('ENGINEERING_REPAIR_INPUT_COLLISION')
    return old or store.put('engineering_repairs',row)
