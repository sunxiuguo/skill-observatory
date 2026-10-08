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
from .runtime import state, tick
from .installations import rollback, recover


def create_app(store=None, web_root=None, daemon=True, reviewer=None):
    store=store or Store();sessions={}
    async def worker():
        while True:
            try:await asyncio.to_thread(tick,store,reviewer)
            except Exception as e:store.put('runtime_errors',{'id':str(time.time_ns()),'reason_code':type(e).__name__})
            await asyncio.sleep(1)
    @asynccontextmanager
    async def lifespan(app):
        recover(store)
        task=asyncio.create_task(worker()) if daemon else None
        try:yield
        finally:
            if task:task.cancel()
    app=FastAPI(lifespan=lifespan)
    app.state.store=store
    @app.middleware('http')
    async def guard(request:Request, call_next):
        host=request.headers.get('host','')
        if host.split(':')[0] not in {'127.0.0.1','localhost','testserver'}:
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
    async def get_state():return state(store)
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
