"""Receipt-driven adapters for existing owners; no oracle, signing or installer copy."""
from __future__ import annotations
import json
from pathlib import Path
from .store import canonical,digest
from .pipeline import EvolutionPipeline,STATE_EXPERIMENT_READY,STATE_CANDIDATE_READY,STATE_ACTIVATION_PENDING,STATE_PROMOTION_READY
from .owner_installers import SkillEvolutionInstaller
from .final_gate import finalize
from .outcomes import validate_task_receipt


def bind_proposal(store,value,installer=None):
    required={'review_id','owner_incident_id'}
    if not required<=set(value) or set(value)-required-{'cost_attempt_ids','proposer_method_version_id','package_request_id','generation_id'}:
        raise ValueError('OWNER_PROPOSAL_INPUT_INVALID')
    review=store.get('reviews',value['review_id'])
    skill=store.get('skills',review.get('skill_id')) if review else None
    if not skill or review.get('status')!='reviewed' or review.get('decision')!='CANDIDATE':
        raise ValueError('OWNER_PROPOSAL_REVIEW_REQUIRED')
    costs=value.get('cost_attempt_ids')
    if costs is not None and (not isinstance(costs,list) or not costs or any(not isinstance(x,str) or not x or len(x)>256 for x in costs) or len(set(costs))!=len(costs)):
        raise ValueError('OWNER_PROPOSAL_COST_INPUT_INVALID')
    original=installer or SkillEvolutionInstaller()
    shown=original.call('show',value['owner_incident_id'])
    if value.get('package_request_id'):
        from .packages import snapshot_package,read_package,changed_files
        request=store.get('owner_package_requests',value['package_request_id'])
        snapshot=shown.get('package_proposal') or {}
        if not request or not original.package_available():raise ValueError('OWNER_PACKAGE_TRANSACTION_UNAVAILABLE')
        root=str(Path(skill['path']).resolve())
        if snapshot.get('operation')!='package_replace' or snapshot.get('target_root')!=root or request['target_root']!=root or any(snapshot.get(k)!=request[k] for k in ('changed_files',)):
            raise ValueError('OWNER_PACKAGE_PROPOSAL_DRIFT')
        before=request['parent_package'];after=request['candidate_package']
        if snapshot.get('before_manifest')!=before or snapshot.get('after_manifest')!=after or snapshot_package(store,root)!=before or snapshot_package(store,snapshot['candidate_tree'])!=after:
            raise ValueError('OWNER_PACKAGE_PROPOSAL_DRIFT')
        old_files=read_package(store,before);new_files=read_package(store,after)
        changed_files(store,before,after,request['changed_files'])
        if 'SKILL.md' not in old_files or 'SKILL.md' not in new_files:raise ValueError('OWNER_PACKAGE_SKILL_REQUIRED')
        item={'id':review['id'],**value,'review_sha256':digest(canonical(review)),
              'parent_sha256':digest(old_files['SKILL.md']),'candidate_sha256':digest(new_files['SKILL.md']),
              'parent_package':before,'candidate_package':after,'target_root':root,'authority_id':request['authority_id'],
              'owner_proposal_sha256':store.artifact(canonical(snapshot))}
        old=store.get('owner_proposals',item['id'])
        if old and old!=item:raise ValueError('OWNER_PROPOSAL_INPUT_COLLISION')
        return old or store.put('owner_proposals',item)
    snapshot=shown['proposal']
    if snapshot.get('schema_version')!=2 or snapshot.get('operation')!='replace':raise ValueError('OWNER_REPLACEMENT_PROPOSAL_REQUIRED')
    target=Path(skill['path'])/'SKILL.md'
    if target.is_symlink() or snapshot.get('target')!=str(target.resolve()) or snapshot.get('before_sha256')!=digest(target.read_bytes()):
        raise ValueError('OWNER_PROPOSAL_BINDING_HOLD')
    candidate=Path(snapshot.get('candidate',''))
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size>1024*1024:
        raise ValueError('OWNER_CANDIDATE_NOT_REGULAR')
    data=candidate.read_bytes();data.decode('utf-8')
    if digest(data)!=snapshot.get('candidate_sha256'):raise ValueError('OWNER_PROPOSAL_BINDING_HOLD')
    costs=value.get('cost_attempt_ids')
    if costs is not None and (not isinstance(costs,list) or not costs or any(not isinstance(x,str) or not x or len(x)>256 for x in costs) or len(set(costs))!=len(costs)):
        raise ValueError('OWNER_PROPOSAL_COST_INPUT_INVALID')
    item={'id':review['id'],**value,'review_sha256':digest(canonical(review)),
        'parent_sha256':snapshot['before_sha256'],'candidate_sha256':store.artifact(data),
        'owner_proposal_sha256':store.artifact(canonical(snapshot))}
    old=store.get('owner_proposals',item['id'])
    if old and old!=item:raise ValueError('OWNER_PROPOSAL_INPUT_COLLISION')
    return store.put('owner_proposals',item)


def bind_evaluation(store,value):
    if not {'candidate_id','evaluation_id'}<=set(value) or set(value)-{'candidate_id','evaluation_id','domain_receipt','cost_receipt'}:
        raise ValueError('OWNER_EVALUATION_INPUT_INVALID')
    candidate=store.get('candidates',value['candidate_id']);evaluation=store.get('evaluations',value['evaluation_id'])
    if not candidate or not evaluation:raise ValueError('FINAL_INPUT_MISSING')
    protocol=store.get('protocols',evaluation['protocol_id']) or {}
    if protocol.get('arm_files',{}).get('parent',{}).get('SKILL.md')!=candidate['parent_sha256'] or protocol.get('arm_files',{}).get('candidate',{}).get('SKILL.md')!=candidate['candidate_sha256']:
        raise ValueError('FINAL_CANDIDATE_HASH_MISMATCH')
    if candidate.get('candidate_package'):
        from .packages import read_package
        for arm in ('parent','candidate'):
            package=candidate[arm+'_package'];files=read_package(store,package)
            if protocol.get(arm+'_package_digest')!=package['package_digest'] or protocol['arm_files'][arm]!={**{n:digest(b) for n,b in files.items()},**protocol.get('harness_files',{})}:
                raise ValueError('FINAL_PACKAGE_PROTOCOL_BINDING_DRIFT')
    item={'id':candidate['id'],'candidate_id':candidate['id'],'evaluation_id':evaluation['id'],
        'evaluation_sha256':store.artifact(canonical(evaluation)),
        'domain_receipt':value.get('domain_receipt'),'cost_receipt':value.get('cost_receipt')}
    old=store.get('owner_evaluations',item['id'])
    if old:
        if old['evaluation_sha256']!=item['evaluation_sha256']:raise ValueError('OWNER_EVALUATION_INPUT_COLLISION')
        for field in ('domain_receipt','cost_receipt'):
            if old.get(field) is not None and item.get(field) is None:item[field]=old[field]
            if old.get(field) is not None and old[field]!=item[field]:raise ValueError('OWNER_EVALUATION_INPUT_COLLISION')
    return store.put('owner_evaluations',item)


class OwnerReceiptPipeline(EvolutionPipeline):
    """Consume original-owner proposals, measured evaluations and accepted results.

    Preparing a candidate and running a domain task remain with their existing
    owners. This bridge never invents truth or spends a model call while waiting.
    Missing inputs leave the original ready state and attempts unchanged.
    """
    adapter_mode='owner_receipt_inputs'
    required_inputs=['owner_prepared_proposal','measured_evaluation_and_signed_domain_cost_receipts','accepted_fresh_context_task_receipt']

    def __init__(self,store,installer=None):
        self.original=installer or SkillEvolutionInstaller()
        super().__init__(store,self.propose,self.evaluate,self.activation_run)

    def _adapter_for(self,stage):
        state=stage.get('state')
        if state==STATE_PROMOTION_READY:return self.store.settings().get('auto_promote') is True or getattr(self,'_explicit_installation',None)==stage['id']
        if state==STATE_EXPERIMENT_READY:return self.store.get('owner_proposals',stage['review_id']) is not None
        if state==STATE_CANDIDATE_READY:
            row=self.store.get('owner_evaluations',stage.get('candidate_id')) or {}
            return row.get('domain_receipt') is not None and row.get('cost_receipt') is not None
        if state==STATE_ACTIVATION_PENDING:return self._accepted_run(stage.get('installation_id')) is not None
        return super()._adapter_for(stage)

    def propose(self,review_bytes,parent_bytes):
        review=json.loads(review_bytes);row=self.store.get('owner_proposals',review['id'])
        if not row or row['review_sha256']!=digest(review_bytes) or row['parent_sha256']!=digest(parent_bytes):
            raise ValueError('OWNER_PROPOSAL_BINDING_HOLD')
        snapshot=self.original.call('show',row['owner_incident_id'])['package_proposal' if row.get('parent_package') else 'proposal']
        if digest(canonical(snapshot))!=row['owner_proposal_sha256']:raise ValueError('OWNER_PROPOSAL_DRIFT')
        result={'candidate_bytes':self.store.read_artifact(row['candidate_sha256']),
            'candidate_sha256':row['candidate_sha256'],'owner_incident_id':row['owner_incident_id'],
            'cost_attempt_ids':row.get('cost_attempt_ids'),'proposer_method_version_id':row.get('proposer_method_version_id'),'generation_id':row.get('generation_id')}
        if row.get('parent_package'):result.update({k:row[k] for k in ('parent_package','candidate_package','package_request_id')})
        return result

    def _matching_authority(self,db,review,skill,target):
        proposal=self.store.get('owner_proposals',review['id'],db)
        if not proposal or not proposal.get('parent_package'):return super()._matching_authority(db,review,skill,target)
        from .installations import authority_expired
        grant=self.store.get('authority_grants',proposal['authority_id'],db)
        if not grant or grant.get('status')!='authorized' or grant.get('owner')!='skill-evolution-loop' or grant.get('surface')!='package' or grant.get('target')!=str(Path(skill['path']).resolve()) or authority_expired(grant.get('expires_at')):return None
        if grant.get('parent_package_digest')!=proposal['parent_package']['package_digest'] or grant.get('candidate_package_digest')!=proposal['candidate_package']['package_digest']:return None
        self.store.read_artifact(grant['evidence_sha256'])
        return grant

    def _create_experiment(self,db,review,skill,authority,parent):
        stage=super()._create_experiment(db,review,skill,authority,parent)
        proposal=self.store.get('owner_proposals',review['id'],db)
        if proposal and proposal.get('parent_package'):
            stage.update({k:proposal[k] for k in ('parent_package','candidate_package','target_root','package_request_id')})
            self.store.put('experiments',stage,db)
        return stage

    def evaluate(self,payload):
        row=self.store.get('owner_evaluations',payload['candidate_id'])
        evaluation=self.store.get('evaluations',row['evaluation_id']) if row else None
        if not evaluation or digest(canonical(evaluation))!=row['evaluation_sha256']:raise ValueError('OWNER_EVALUATION_INPUT_DRIFT')
        return finalize(self.store,payload['candidate_id'],row['evaluation_id'],row['domain_receipt'],row['cost_receipt'])

    def _accepted_run(self,installation_id):
        if not installation_id:return None
        with self.store.connect() as db:
            rows=db.execute("SELECT data FROM entities WHERE kind='task_receipts' AND json_extract(data,'$.installation_id')=? ORDER BY id",(installation_id,)).fetchall()
        for raw in rows:
            receipt=json.loads(raw[0])
            if receipt.get('status')!='accepted':continue
            try:validated=validate_task_receipt(self.store,receipt)
            except (ValueError,KeyError,OSError):continue
            return validated['run_id']
        return None

    def activation_run(self,candidate_id,installation_id):
        installation=self.store.get('installations',installation_id)
        if not installation or installation.get('candidate_id')!=candidate_id:raise ValueError('INSTALLATION_BINDING_MISMATCH')
        run_id=self._accepted_run(installation_id)
        if not run_id:raise ValueError('ACTIVATION_TASK_RECEIPT_REQUIRED')
        return run_id
