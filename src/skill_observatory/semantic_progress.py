"""Read-only material progress, independent from worker callbacks/heartbeats."""
import json
from datetime import datetime,timezone
from .store import now

# Each row is its own denominator. Counts do not add to a task/gain total.
STAGES=(
    ('facts','evidence_builds',"json_extract(data,'$.status')='built'",'completed_at','select_native_facts'),
    ('review','reviews',"json_extract(data,'$.status')='reviewed'",'created_at','supply_facts_and_review'),
    ('trial','task_family_attempts',"json_extract(data,'$.status')='completed'",'finished_at','run_frozen_task_family'),
    ('verdict','verdicts','1','created_at','reconcile_independent_truth_and_cost'),
    ('installation','installations',"json_extract(data,'$.applied_at') IS NOT NULL",'applied_at','obtain_owner_authority_and_transaction'),
    ('activation','installations',"json_extract(data,'$.activated')=1",'activated_at','complete_fresh_context_task'),
    ('natural','cohort_samples','1','created_at','observe_frozen_natural_cohort'),
    ('method','method_generations','1','created_at','record_real_method_generation'),
)


def project(store,stamp=None):
    stamp=stamp or now();rows=[]
    with store.connect() as db:
        db.execute('BEGIN')
        for id_,kind,where,timefield,action in STAGES:
            n,last=db.execute(f"SELECT count(*),max(json_extract(data,'$.{timefield}')) FROM entities WHERE kind=? AND ({where})",(kind,)).fetchone()
            age=None
            if last:
                try:age=max(0,(datetime.fromisoformat(stamp)-datetime.fromisoformat(last)).total_seconds())
                except (ValueError,TypeError):pass
            rows.append({'id':id_,'observed_count':n,'last_material_at':last,'age_seconds':age,'next_action':action})
        pending_facts=db.execute("SELECT count(*) FROM jobs WHERE reason_code IN ('DIAGNOSTIC_FACTS_REQUIRED','EVIDENCE_CAPSULE_RUN_DRIFT')").fetchone()[0]
        unknown_attempts=db.execute("SELECT count(*) FROM entities WHERE kind IN ('review_attempts','generation_attempts','broker_attempts','task_family_attempts') AND json_extract(data,'$.status') IN ('unknown_after_dispatch','dispatched','interrupted','unknown','failed_after_dispatch')").fetchone()[0]
        gaps=db.execute("SELECT count(*) FROM entities WHERE kind='transcript_gaps'").fetchone()[0]
        waiting=db.execute("SELECT count(*) FROM entities WHERE kind='outcome_followups' AND json_extract(data,'$.status')='pending'").fetchone()[0]
        items=[(r['kind'],json.loads(r['data'])) for r in db.execute("SELECT kind,data FROM entities WHERE kind IN ('evidence_builds','evaluations','verdicts','task_family_attempts','installations','candidates','experiments','owner_package_requests','owner_proposals') ORDER BY rowid DESC")]
    blocker='ATTEMPT_READBACK_REQUIRED' if unknown_attempts else 'DIAGNOSTIC_FACTS_REQUIRED' if pending_facts else 'SEMANTIC_COVERAGE_GAP' if gaps else None
    action={'ATTEMPT_READBACK_REQUIRED':'readback_unknown_attempt','DIAGNOSTIC_FACTS_REQUIRED':'select_native_facts','SEMANTIC_COVERAGE_GAP':'recover_explicit_source_gap'}.get(blocker)
    blocking_item=None;flow='waiting' if blocker else 'idle'
    # The latest decision per real chain supersedes its prior HOLD. Cumulative
    # stage counts remain independent and never imply that a chain passed.
    decisions={};facts={};trials={};installations=[];candidates={};experiments=[];requests=[];bound_requests=set()
    for kind,item in items:
        if kind in {'verdicts','evaluations'}:
            chain=item.get('protocol_id',item.get('candidate_id',item['id']))
            prior=decisions.get(chain)
            if prior is None or (kind=='verdicts' and prior[0]!='verdicts'):decisions[chain]=(kind,item)
        elif kind=='evidence_builds' and item.get('status')!='superseded':
            prior=facts.get(item['run_id'])
            if prior is None or item.get('status') in {'awaiting_native_selection','blocked'}:
                facts[item['run_id']]=item
        elif kind=='task_family_attempts':trials.setdefault(item['id'],item)
        elif kind=='installations':installations.append(item)
        elif kind=='candidates':candidates[item['id']]=item
        elif kind=='experiments':experiments.append(item)
        elif kind=='owner_package_requests':requests.append(item)
        elif kind=='owner_proposals' and item.get('package_request_id'):bound_requests.add(item['package_request_id'])
    if not blocker:
        pending=next((v for v in facts.values() if v.get('status') in {'awaiting_native_selection','blocked'}),None)
        if pending:blocker='DIAGNOSTIC_FACTS_REQUIRED';action='select_native_facts';blocking_item=pending
    if not blocker:
        pending=next((v for v in trials.values() if v.get('status') in {'prepared','dispatched','unknown_after_dispatch'}),None)
        if pending:blocker='TASK_FAMILY_READBACK_REQUIRED';action='run_frozen_task_family' if pending['status']=='prepared' else 'readback_unknown_attempt';blocking_item=pending
    if not blocker:
        pending=next((v for v in experiments if v.get('state')=='held' and not (v.get('missing') and set(v['missing'])<={'NO_CONFIRMED_GAIN','NO_GAIN'})),None)
        if pending:
            blocker=next(iter(pending.get('missing') or []),pending.get('reason_code') or 'INDEPENDENT_GAIN_AND_COST_REQUIRED');action='readback_unknown_attempt' if blocker in {'SIDE_EFFECT_READBACK_REQUIRED','ATTEMPT_READBACK_REQUIRED'} else 'reconcile_independent_truth_and_cost';blocking_item=pending
    if not blocker:
        for kind,decision in decisions.values():
            missing=decision.get('missing') or []
            actionable=[x for x in missing if x not in {'NO_CONFIRMED_GAIN','NO_GAIN'}]
            if actionable:
                blocker=actionable[0];action='reconcile_independent_truth_and_cost';blocking_item=decision;break
            if decision.get('status') in {'no_gain','rejected'} or (missing and not actionable):flow='no_gain';continue
            if decision.get('status')!='accepted':
                blocker='INDEPENDENT_GAIN_AND_COST_REQUIRED';action='reconcile_independent_truth_and_cost';blocking_item=decision;break
            matching=[i for i in installations if i.get('verdict_id')==decision['id'] or (candidates.get(i.get('candidate_id')) or {}).get('verdict_id')==decision['id']]
            if not matching:
                blocker='OWNER_AUTHORITY_AND_INSTALLATION_REQUIRED';action='obtain_owner_authority_and_transaction';blocking_item=decision;break
            pending=next((i for i in matching if i.get('status') not in {'rolled_back','failed'} and not i.get('applied_at')),None)
            if pending:
                blocker='OWNER_TRANSACTION_REQUIRED';action='obtain_owner_authority_and_transaction';blocking_item=pending;break
    if not blocker:
        pending=next((i for i in installations if i.get('applied_at') and i.get('status') not in {'rolled_back','failed'} and not i.get('activated')),None)
        if pending:blocker='FRESH_ACTIVATION_REQUIRED';action='complete_fresh_context_task';blocking_item=pending
    if not blocker and any(v.get('status')=='completed' and v.get('protocol_id') not in decisions for v in trials.values()):
        blocker='INDEPENDENT_GAIN_AND_COST_REQUIRED';action='reconcile_independent_truth_and_cost'
    if not blocker and waiting:blocker='NATURAL_FOLLOW_UP_PENDING';action='observe_frozen_natural_cohort'
    if not blocker:
        pending=next((v for v in requests if v['id'] not in bound_requests and v.get('status')=='blocked'),None)
        if pending:blocker=pending.get('reason_code') or 'OWNER_AUTHORITY_AND_INSTALLATION_REQUIRED';action='obtain_owner_authority_and_transaction';blocking_item=pending
    if not blocker:
        pending=next((v for v in experiments if v.get('state') in {'experiment_ready','candidate_ready','running','prepared'}),None)
        if pending:
            blocker='OWNER_PROPOSAL_REQUIRED' if pending['state']=='experiment_ready' else 'INDEPENDENT_GAIN_AND_COST_REQUIRED' if pending['state']=='candidate_ready' else 'ATTEMPT_READBACK_REQUIRED'
            action='obtain_owner_authority_and_transaction' if pending['state']=='experiment_ready' else 'reconcile_independent_truth_and_cost' if pending['state']=='candidate_ready' else 'readback_unknown_attempt';blocking_item=pending
    if blocker:flow='waiting'
    return {'schema_version':1,'stages':rows,'first_blocker':blocker,'pending_facts':pending_facts,'unknown_attempts':unknown_attempts,
            'semantic_gaps':gaps,'pending_followups':waiting,'coverage':'observed_receipts_only','global_denominator':None,
            'next_action':action or 'await_changed_input','flow_state':flow,
            'blocking_item':{k:blocking_item[k] for k in ('id','status','missing') if k in blocking_item} if blocking_item else None,
            'claim_layers':{'skill_gain':'HOLD','natural_gain':'UNKNOWN','method_rsi':'UNVERIFIED'}}
