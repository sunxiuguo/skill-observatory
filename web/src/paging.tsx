import {useEffect,useState} from 'react';
import {getCsrf} from './api.ts';

export const entityKinds:Record<string,string>={capability:'capability_catalog',capture:'captures',invocation:'capability_invocations',run:'runs',review:'reviews',skill:'skills',experiment:'experiments',job:'jobs',installation:'installations',environment:'environments'};

async function read(url:string,signal:AbortSignal){
 const response=await fetch(url,{credentials:'same-origin',signal,headers:{Accept:'application/json','X-CSRF-Token':getCsrf()||''}});
 if(!response.ok)throw new Error(`HTTP ${response.status}`);
 return response.json();
}

export function useEntityPage(kind:string|undefined,filters:Record<string,unknown>,page:number,revision?:number){
 const [value,setValue]=useState<{items:any[],total:number,loading:boolean,error:string|null}>({items:[],total:0,loading:!!kind,error:null});
 const key=JSON.stringify(filters);
 useEffect(()=>{
  if(!kind)return;
  const controller=new AbortController();let current=true;
  setValue(v=>({...v,loading:true,error:null}));
  const params=new URLSearchParams({offset:String((page-1)*12),limit:'12'});
  for(const [k,v] of Object.entries(JSON.parse(key))){
   if(v&&v!=='all'&&k!=='page')params.set(k==='kind'?'capability_kind':k,k==='canary'?(v==='canary'?'only':v==='user'?'exclude':String(v)):String(v));
  }
  read(`/api/entities/${kind}?${params}`,controller.signal).then(data=>{if(current)setValue({...data,loading:false,error:null});}).catch(e=>{if(current&&!controller.signal.aborted)setValue(v=>({...v,loading:false,error:e.message}));});
  return ()=>{current=false;controller.abort();};
 },[kind,key,page,revision]);
 return value;
}

export function useEntityDetail(target:{kind:string,id:string}|null,revision?:number){
 const [value,setValue]=useState<{record:any,loading:boolean,error:string|null}>({record:null,loading:false,error:null});
 useEffect(()=>{
  if(!target){setValue({record:null,loading:false,error:null});return;}
  const controller=new AbortController();let current=true;
  setValue({record:null,loading:true,error:null});
  read(`/api/entities/${entityKinds[target.kind]}/${encodeURIComponent(target.id)}`,controller.signal).then(record=>{if(current)setValue({record,loading:false,error:null});}).catch(e=>{if(current&&!controller.signal.aborted)setValue({record:null,loading:false,error:e.message});});
  return ()=>{current=false;controller.abort();};
 },[target?.kind,target?.id,revision]);
 return value;
}
