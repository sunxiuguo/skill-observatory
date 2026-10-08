import {afterAll,expect,test} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {App} from './App.jsx';
const nativeFetch=globalThis.fetch;
const origin=process.env.SKILLOBS_TEST_ORIGIN||'http://127.0.0.1:8776';
let cookie='';
// Real loopback API. Only relative-URL and browser-cookie transport are adapted.
globalThis.fetch=async(input,options={})=>{
 const headers=new Headers(options.headers);if(cookie)headers.set('cookie',cookie);
 const res=await nativeFetch(new URL(input,origin),{...options,headers});
 const next=res.headers.get('set-cookie');if(next)cookie=next.split(';')[0];return res;
};
afterAll(async()=>{cleanup();const session=await(await fetch('/api/session')).json();await fetch('/api/settings',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':session.csrf},body:JSON.stringify({locale:'zh-CN'})});globalThis.fetch=nativeFetch});
test('live API locale change preserves filter, draft, navigation and refresh recovery',async()=>{
 localStorage.clear();sessionStorage.clear();location.hash='#settings';
 const boot=await(await fetch('/api/session')).json();await fetch('/api/settings',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':boot.csrf},body:JSON.stringify({locale:'zh-CN'})});
 const app=render(<App/>);
 await screen.findByLabelText('时区');
 fireEvent.change(screen.getByLabelText('时区'),{target:{value:'Asia/Tokyo'}});
 fireEvent.change(screen.getByLabelText('搜索运行、Skill 或 ID…'),{target:{value:'pilot-marker'}});
 fireEvent.click(screen.getByRole('button',{name:'English',exact:true}));
 await screen.findByLabelText('Time zone');
 expect(screen.getByLabelText('Time zone').value).toBe('Asia/Tokyo');
 expect(screen.getByLabelText('Search runs, skills, or IDs…').value).toBe('pilot-marker');
 expect(location.hash).toBe('#settings');
 await waitFor(async()=>{const current=await(await fetch('/api/state')).json();expect(current.settings.locale).toBe('en')});
 app.unmount();render(<App/>);
 await screen.findByLabelText('Time zone');
 expect(screen.getByLabelText('Time zone').value).toBe('Asia/Tokyo');
 expect(screen.getByLabelText('Search runs, skills, or IDs…').value).toBe('pilot-marker');
 fireEvent.click(screen.getByRole('button',{name:'中文',exact:true}));
 await screen.findByLabelText('时区');expect(screen.getByLabelText('时区').value).toBe('Asia/Tokyo');
});
