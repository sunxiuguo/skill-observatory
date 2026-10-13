"""Isolate the configured trusted reviewer under a host process-group deadline."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from .store import canonical, now


class IsolatedReviewer:
    def __init__(self,max_seconds,grace_seconds=45):self.max_seconds=max_seconds;self.grace_seconds=grace_seconds

    def review(self,store,run):
        process=subprocess.Popen([sys.executable,'-m','skill_observatory.review_worker',str(store.root),run['id']],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,
            env={**os.environ,'SKILLOBS_REVIEW_WORKER':'1'})
        try:
            output,_=process.communicate(timeout=self.max_seconds+self.grace_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=5)
            for attempt in store.list('review_attempts'):
                if attempt.get('run_id')==run['id'] and attempt.get('status') not in {'completed','failed_after_dispatch'}:
                    store.put('review_attempts',{**attempt,'status':'unknown_after_dispatch',
                        'reason_code':'REVIEW_PROCESS_DEADLINE_READBACK_REQUIRED','updated_at':now()})
            raise ValueError('REVIEW_PROCESS_DEADLINE_READBACK_REQUIRED')
        if len(output)>16000:raise ValueError('REVIEW_WORKER_OUTPUT_INVALID')
        data=json.loads(output or b'{}')
        if process.returncode==3:
            from .reviewer import ReviewDeferred
            raise ReviewDeferred(data['reason_code'],data['eligible_at'])
        if process.returncode:raise ValueError(data.get('reason_code','REVIEW_WORKER_READBACK_REQUIRED'))
        return store.get('reviews','rv_'+run['id'])


def main():
    from .store import Store
    from .configuration import load_reviewer
    from .reviewer import ReviewDeferred
    store=Store(sys.argv[1]);run=store.get('runs',sys.argv[2])
    try:
        reviewer=load_reviewer(store,isolated=False)
        if not run or not reviewer:raise ValueError('REVIEW_WORKER_INPUT_MISSING')
        reviewer.review(store,run)
        print(canonical({'status':'completed'}).decode());return 0
    except ReviewDeferred as ex:
        print(canonical({'reason_code':str(ex),'eligible_at':ex.eligible_at}).decode());return 3
    except Exception as ex:
        import re
        reason=str(ex) if re.fullmatch(r'[A-Z0-9_:-]{1,160}',str(ex)) else type(ex).__name__
        print(canonical({'reason_code':reason}).decode());return 2


if __name__=='__main__':sys.exit(main())
