"""Loopback API, same-origin browser sessions, CSRF, no arbitrary shell input."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response, FileResponse
from .store import Store
from .runtime import state, collect, process_one, progress
from .installations import rollback, recover

ENTITY_KINDS={'skills','runs','reviews','experiments','installations','environments','capability_catalog',
              'capability_versions','capability_invocations','captures','jobs','review_attempts','adapter_errors'}


def summary(store):
    """Bounded transport and SQL aggregate denominators; detail stays on demand."""
    from .store import now
    result={};pagination={}
    # One read transaction prevents revision/count/page mixing during collection.
    with store.connect() as db:
        db.execute('BEGIN')
        result['revision']=db.execute('SELECT value FROM ledger_revision WHERE id=1').fetchone()[0]
        counts={r[0]:r[1] for r in db.execute('SELECT kind,count(*) FROM entities GROUP BY kind')}
        for kind in ENTITY_KINDS-{'jobs','review_attempts','adapter_errors'}:
            rows=db.execute('SELECT data FROM entities WHERE kind=? ORDER BY rowid DESC LIMIT 50',(kind,)).fetchall()
            items=[]
            for row in rows:
                from .store import list_projection
                value=list_projection(json.loads(row[0]))
                items.append(value)
            result[kind]=items;pagination[kind]={'total':counts.get(kind,0),'offset':0,'limit':50}
        result['settings']=json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        result['jobs']=[dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 50')]
        jobcounts={r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM jobs GROUP BY status')}
        pagination['jobs']={'total':sum(jobcounts.values()),'offset':0,'limit':50}
        reviewcounts={r[0]:r[1] for r in db.execute("SELECT json_extract(data,'$.status'),count(*) FROM entities WHERE kind='reviews' GROUP BY 1")}
        bounds=db.execute("SELECT min(json_extract(data,'$.created_at')),max(json_extract(data,'$.created_at')) FROM entities WHERE kind='runs'").fetchone()
        runtime=[json.loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind='runtime'")]
        daemon=next((r for r in runtime if r['id']=='daemon'),{})
        errors=[json.loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind='runtime_errors'")]
        stagecounts={r[0]:r[1] for r in db.execute("SELECT j.value,count(*) FROM entities e,json_each(e.data,'$.stages') j WHERE e.kind='capability_invocations' GROUP BY j.value")}
        capstats=db.execute("SELECT sum(json_extract(data,'$.status')='active'),sum(json_extract(data,'$.born_at') IS NULL) FROM entities WHERE kind='capability_catalog'").fetchone()
        result['lifecycle_metrics']={'catalog':counts.get('capability_catalog',0),'captures':counts.get('captures',0),'active':capstats[0] or 0,
            'invocations':counts.get('capability_invocations',0),'unknown_births':capstats[1] or 0,'stage_counts':stagecounts,
            'capture_holds':db.execute("SELECT count(*) FROM entities WHERE kind='captures' AND json_extract(data,'$.status') IN ('hold','failed')").fetchone()[0]}
        # Per-capability counters include all logical invocations, not the first page.
        for cap in result['capability_catalog']:
            args=(cap['id'],)
            cap['usage_counts']={r[0]:r[1] for r in db.execute("SELECT j.value,count(*) FROM entities e,json_each(e.data,'$.stages') j WHERE e.kind='capability_invocations' AND json_extract(e.data,'$.capability_id')=? GROUP BY j.value",args)}
            cap['invocation_count']=db.execute("SELECT count(*) FROM entities WHERE kind='capability_invocations' AND json_extract(data,'$.capability_id')=?",args).fetchone()[0]
        result['facets']={'projects':[r[0] for r in db.execute("SELECT DISTINCT COALESCE(json_extract(data,'$.cwd'),json_extract(data,'$.origin.project')) FROM entities WHERE kind IN ('capability_invocations','captures','runs') AND COALESCE(json_extract(data,'$.cwd'),json_extract(data,'$.origin.project')) IS NOT NULL ORDER BY 1")]}
        result['metrics']={'observed_runs':counts.get('runs',0),'reviewed_runs':reviewcounts.get('reviewed',0),'triaged_runs':reviewcounts.get('triaged',0),
            'global_coverage':None,'coverage_reason':'GLOBAL_DENOMINATOR_UNKNOWN','queued_jobs':jobcounts.get('queued',0),'deferred_jobs':jobcounts.get('deferred',0),
            'daemon_running':time.time()-daemon.get('heartbeat',0)<30,'heartbeat_age':time.time()-daemon['heartbeat'] if daemon.get('heartbeat') else None,
            'adapter_error_causes':counts.get('adapter_errors',0),'spool_count':daemon.get('spool_count'),
            'window_start':bounds[0],'window_end':now()}
    result.update(runtime=runtime,runtime_errors=errors,pagination=pagination,
        capabilities={'semantic_review':next((r.get('status') for r in runtime if r['id']=='reviewer'),'unconfigured'),
            'strong_sandbox':'requires_current_environment_receipt','promotion':'requires_frozen_independent_final','hook_trust':'native_review_required','recursive_gain':'UNVERIFIED'})
    return result


def create_app(store=None, web_root=None, daemon=True, reviewer=None,pipeline=None):
    store=store or Store();sessions={}
    if pipeline is None:
        from .pipeline import EvolutionPipeline
        pipeline=EvolutionPipeline(store)
    async def worker(lane,callback,phase):
        while True:
            try:
                progress(store,lane,phase)
                await asyncio.to_thread(callback)
                progress(store,lane,'idle')
            except Exception as e:store.put('runtime_errors',{'id':lane,'reason_code':type(e).__name__,'created_at':time.time()})
            await asyncio.sleep(1)
    async def watch():
        while True:
            for lane in ('review_worker','evolution_worker'):
                row=store.get('runtime',lane) or {}
                bound=getattr(reviewer,'max_seconds',120)+50 if lane=='review_worker' else 300
                if row.get('phase')!='idle' and time.time()-row.get('phase_started_at',time.time())>bound:
                    store.put('runtime_errors',{'id':lane,'reason_code':'WORKER_DEADLINE_READBACK_REQUIRED','phase':row.get('phase'),'created_at':time.time()})
            await asyncio.sleep(2)
    @asynccontextmanager
    async def lifespan(app):
        recover(store)
        tasks=[asyncio.create_task(worker('daemon',lambda:collect(store),'collect')),
               asyncio.create_task(worker('review_worker',lambda:process_one(store,reviewer),'review')),
               asyncio.create_task(worker('evolution_worker',pipeline.tick,'evolution')),
               asyncio.create_task(watch())] if daemon else []
        try:yield
        finally:
            for task in tasks:task.cancel()
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
    app=FastAPI(lifespan=lifespan)
    app.state.store=store
    @app.middleware('http')
    async def guard(request:Request, call_next):
        host=request.headers.get('host','')
        if host.split(':')[0] not in {'127.0.0.1','localhost'}:
            return JSONResponse({'reason_code':'HOST_REJECTED'},status_code=403)
        origin=request.headers.get('origin')
        expected=f"{request.url.scheme}://{host}"
        if origin and origin!=expected:return JSONResponse({'reason_code':'ORIGIN_REJECTED'},status_code=403)
        if request.headers.get('sec-fetch-site') in {'cross-site'}:return JSONResponse({'reason_code':'CROSS_SITE_REJECTED'},status_code=403)
        if request.url.path.startswith('/api/') and request.url.path!='/api/session':
            sid=request.cookies.get('skillobs_session');s=sessions.get(sid)
            if not s or s['expires']<time.time():return JSONResponse({'reason_code':'SESSION_REQUIRED'},status_code=401)
            if request.method not in {'GET','HEAD'} and not secrets.compare_digest(request.headers.get('x-csrf-token',''),s['csrf']):return JSONResponse({'reason_code':'CSRF_REJECTED'},status_code=403)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"})
        return response
    @app.get('/api/session')
    async def session():
        sid=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        # Expired browser sessions are not retained forever.
        for k in list(sessions):
            if sessions[k]['expires']<time.time():sessions.pop(k)
        if len(sessions)>256:raise HTTPException(429,detail={'reason_code':'SESSION_LIMIT'})
        sessions[sid]={'csrf':csrf,'expires':time.time()+3600}
        r=JSONResponse({'csrf':csrf});r.set_cookie('skillobs_session',sid,httponly=True,samesite='strict',max_age=3600);return r
    @app.get('/api/state')
    async def get_state():return await asyncio.to_thread(state,store)
    @app.get('/api/summary')
    async def get_summary():return await asyncio.to_thread(summary,store)
    @app.get('/api/entities/{kind}')
    async def entity_page(kind:str,offset:int=0,limit:int=12,status:str|None=None,query:str|None=None,
                          stage:str|None=None,project:str|None=None,capability_id:str|None=None,
                          canary:str|None=None,order:str='newest',capability_kind:str|None=None,bucket:str|None=None):
        if kind not in ENTITY_KINDS or not 0<=offset<=10000000 or not 1<=limit<=50 or (query and len(query)>200):
            raise HTTPException(422,detail={'reason_code':'PAGE_CONTRACT_INVALID'})
        return await asyncio.to_thread(store.entity_page,kind,offset,limit,status,query,stage,project,capability_id,canary,order,capability_kind,bucket)
    @app.get('/api/entities/{kind}/{id}')
    async def entity(kind:str,id:str):
        if kind not in ENTITY_KINDS:raise HTTPException(404,detail={'reason_code':'ENTITY_KIND_NOT_ALLOWED'})
        if kind=='jobs':
            with store.connect() as db:
                row=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone();value=dict(row) if row else None
        else:value=await asyncio.to_thread(store.get,kind,id)
        if not value:raise HTTPException(404,detail={'reason_code':'ENTITY_NOT_FOUND'})
        if kind=='capability_catalog':
            from .capabilities import capability_projection
            with store.connect() as db:value=capability_projection(store,value,db)
        if kind=='experiments' and value.get('state'):value['status']=value['state']
        if kind=='runs':
            with store.connect() as db:
                row=db.execute("SELECT data FROM entities WHERE kind='reviews' AND json_extract(data,'$.run_id')=? ORDER BY rowid DESC LIMIT 1",(id,)).fetchone()
                value['related_review']=json.loads(row[0]) if row else None
                row=db.execute('SELECT * FROM jobs WHERE run_id=? ORDER BY created_at DESC LIMIT 1',(id,)).fetchone()
                value['related_job']=dict(row) if row else None
        return value
    @app.post('/api/settings')
    async def settings(request:Request):
        b=await request.json()
        if set(b)-{'locale','timezone','paused','automatic_review'}:raise HTTPException(422,detail={'reason_code':'SETTING_NOT_AUTHORIZED'})
        if 'locale' in b and b['locale'] not in {'zh-CN','en'}:raise HTTPException(422,detail={'reason_code':'INVALID_LOCALE'})
        try:
            if 'timezone' in b:ZoneInfo(b['timezone'])
        except (ZoneInfoNotFoundError,TypeError):raise HTTPException(422,detail={'reason_code':'INVALID_TIMEZONE'})
        for k in {'paused','automatic_review'}&set(b):
            if type(b[k]) is not bool:raise HTTPException(422,detail={'reason_code':'INVALID_SETTING_TYPE'})
        return store.settings(b)
    @app.get('/api/artifacts/{hash}')
    async def artifact(hash:str):
        try:return Response(store.read_artifact(hash),media_type='application/json')
        except (ValueError,FileNotFoundError):raise HTTPException(404,detail={'reason_code':'ARTIFACT_NOT_FOUND'})
    @app.post('/api/jobs/{id}/retry')
    async def retry(id:str):
        with store.connect() as db:
            j=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
            if not j:raise HTTPException(404,detail={'reason_code':'JOB_NOT_FOUND'})
            if j['reason_code']=='INTERRUPTED_ATTEMPT':raise HTTPException(409,detail={'reason_code':'SIDE_EFFECT_READBACK_REQUIRED'})
            if j['reason_code']=='SEMANTIC_REVIEW_REQUIRED':raise HTTPException(409,detail={'reason_code':'REVIEWER_SETUP_REQUIRED'})
            if j['status'] not in {'hold','failed'}:raise HTTPException(409,detail={'reason_code':'JOB_NOT_RETRYABLE'})
            # A model timeout, malformed response or connection loss can consume
            # money and produce output. A browser click cannot authorize replay.
            attempts=db.execute("SELECT data FROM entities WHERE kind='review_attempts'").fetchall()
            if any(json.loads(a[0]).get('run_id')==j['run_id'] and
                   json.loads(a[0]).get('admission_sha256') for a in attempts):
                raise HTTPException(409,detail={'reason_code':'ATTEMPT_READBACK_REQUIRED'})
            db.execute("UPDATE jobs SET status='queued',reason_code=NULL WHERE id=?",(id,))
        return {'id':id,'status':'queued'}
    @app.post('/api/installations/{id}/rollback')
    async def revert(id:str):
        try:return await asyncio.to_thread(rollback,store,id)
        except ValueError as e:raise HTTPException(409,detail={'reason_code':str(e)})
    root=Path(web_root or Path(__file__).parent/'static').resolve()
    @app.get('/{path:path}')
    async def ui(path:str):
        if path=='api' or path.startswith('api/'):raise HTTPException(404)
        p=(root/path).resolve()
        if root not in p.parents and p!=root:raise HTTPException(404)
        if not p.is_file():p=root/'index.html'
        if not p.exists():raise HTTPException(503,detail={'reason_code':'UI_NOT_BUILT'})
        return FileResponse(p)
    return app
