import {useStore} from './store.tsx';
export function OverviewLoading(){
 const s=useStore(),zh=s.locale==='zh-CN';
 return <section className="overview-loading" aria-busy="true" aria-label={zh?'正在读取观测台状态…':'Loading Observatory state…'}>
  <p role="status">{zh?'正在读取观测台状态…':'Loading Observatory state…'}</p>
  <div aria-hidden="true" className="overview-skeleton">
   <div className="sk-title skeleton-block"/><div className="sk-subtitle skeleton-block"/>
   <div className="sk-actions">{[1,2,3].map(n=><div key={n} className="skeleton-block"/>)}</div>
   <div className="sk-progress"><div className="sk-heading skeleton-block"/><div className="material-stages">{Array.from({length:8},(_,i)=><div key={i}><span className="sk-label skeleton-block"/><span className="sk-number skeleton-block"/><span className="sk-date skeleton-block"/></div>)}</div><div className="sk-heading skeleton-block"/><div className="sk-subtitle skeleton-block"/></div>
   <div className="sk-kpis">{[1,2,3,4].map(n=><div key={n}><span className="sk-label skeleton-block"/><span className="sk-number skeleton-block"/></div>)}</div>
  </div>
 </section>
}
