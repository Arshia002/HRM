(()=>{
'use strict';
const VERSION='4.9.0';
const DEFAULT_DB_NAME='SazmanHR-Standalone-v1';
const DEFAULT_DB_STORE='kv';
const MAX_DIAGNOSTIC_TEXT=2400;

function createStorage(win=globalThis){
 const memory=new Map();
 try{
  const s=win.localStorage,test='__sazmanhr_storage_test__';
  s.setItem(test,'1');s.removeItem(test);return s;
 }catch(e){
  return {getItem:k=>memory.has(k)?memory.get(k):null,setItem:(k,v)=>memory.set(k,String(v)),removeItem:k=>memory.delete(k),clear:()=>memory.clear()};
 }
}
function debounce(fn,wait=180){let t;return (...args)=>{clearTimeout(t);t=setTimeout(()=>fn(...args),wait)}}
function idleRun(fn){return (globalThis.requestIdleCallback||((cb)=>setTimeout(cb,40)))(fn)}
function safeText(value,max=MAX_DIAGNOSTIC_TEXT){
 let s=String(value??'').replace(/(["']?(?:password|passwd|token|authorization|secret)["']?\s*[:=]\s*)[^\s,;}]+/gi,'$1[REDACTED]');
 s=s.replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi,'Bearer [REDACTED]');
 return s.length>max?s.slice(0,max)+'…':s;
}
function createApi({state,getToken=()=>state?.token||'',prefix='/api'}={}){
 const headers=()=>{const t=getToken();return t?{'X-Token':t}:{}};
 return {
  async detect(timeoutMs=2600){
   if(globalThis.location?.protocol==='file:'){if(state){state.server=false;state.portable=false}return {server:false,portable:false,reason:'direct-file',version:VERSION}}
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
   try{const r=await fetch(prefix+'/status?_='+Date.now(),{cache:'no-store',signal:controller.signal});if(!r.ok)throw new Error('status-'+r.status);const j=await r.json();if(state){state.server=!!j.server;state.portable=!!j.portable}return j}
   catch(e){if(state){state.server=false;state.portable=false}return {server:false,portable:false,reason:e?.name==='AbortError'?'timeout':'unreachable',version:VERSION}}
   finally{clearTimeout(timer)}
  },
  async get(path){const r=await fetch(prefix+path,{cache:'no-store',headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()},
  async post(path,body,raw=false,extraHeaders={}){const opt={method:'POST',cache:'no-store',headers:{...extraHeaders,...headers()}};if(raw)opt.body=body;else{opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body||{})}const r=await fetch(prefix+path,opt);if(!r.ok)throw new Error(await r.text());const ct=r.headers.get('content-type')||'';return ct.includes('json')?r.json():r.text()}
 };
}
function createPortableApi({state,getToken=()=>state?.token||'',prefix='/portable-api'}={}){
 return {
  async request(path,{method='GET',body=null}={}){
   const headers={'Accept':'application/json'},token=getToken();if(token)headers['X-Portable-Token']=token;
   if(method!=='GET'&&token&&state?.csrf)headers['X-SazmanHR-CSRF']=state.csrf;
   const opt={method,cache:'no-store',headers};if(body!==null){headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
   const r=await fetch(prefix+path,opt),text=await r.text();let data={};try{data=text?JSON.parse(text):{}}catch(e){data={error:text}}
   if(!r.ok)throw new Error(data.error||data.message||text||`خطای ${r.status}`);return data
  },
  get(path){return this.request(path)},post(path,body={}){return this.request(path,{method:'POST',body})}
 };
}
function createStandaloneDb({name=DEFAULT_DB_NAME,store=DEFAULT_DB_STORE,indexedDB=globalThis.indexedDB}={}){
 function open(){return new Promise((resolve,reject)=>{if(!indexedDB)return reject(new Error('IndexedDB در دسترس نیست.'));const req=indexedDB.open(name,1);req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(store))db.createObjectStore(store)};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('بازکردن پایگاه محلی ناموفق بود.'))})}
 async function get(key){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store,'readonly'),req=tx.objectStore(store).get(key);req.onsuccess=()=>{db.close();resolve(req.result)};req.onerror=()=>{db.close();reject(req.error)}})}
 async function set(key,value){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store,'readwrite');tx.objectStore(store).put(value,key);tx.oncomplete=()=>{db.close();resolve(true)};tx.onerror=()=>{db.close();reject(tx.error)};tx.onabort=()=>{db.close();reject(tx.error||new Error('ذخیره محلی لغو شد.'))}})}
 async function del(key){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(store,'readwrite');tx.objectStore(store).delete(key);tx.oncomplete=()=>{db.close();resolve(true)};tx.onerror=()=>{db.close();reject(tx.error)}})}
 return Object.freeze({get,set,delete:del});
}
function createScriptLoader(){
 const promises=new Map();
 return function loadScriptOnce(src,ready){const current=typeof ready==='function'?ready():null;if(current)return Promise.resolve(current);if(promises.has(src))return promises.get(src);const promise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=src;script.async=true;script.onload=()=>{const value=typeof ready==='function'?ready():true;if(value)resolve(value);else reject(new Error('فایل بارگذاری شد اما داده معتبر نبود: '+src))};script.onerror=()=>reject(new Error('بارگذاری فایل ناموفق بود: '+src));document.head.appendChild(script)}).catch(err=>{promises.delete(src);throw err});promises.set(src,promise);return promise}
}
function installDiagnostics({state,version=VERSION,getPage=()=>state?.page||'',endpoint='/api/client-log'}={}){
 let sent=0,lastKey='',lastAt=0;
 async function report(kind,error,extra={}){
  try{
   const message=safeText(error?.message||error||kind),stack=safeText(error?.stack||'',4800),key=kind+'|'+message,now=Date.now();
   if(key===lastKey&&now-lastAt<5000)return false;if(sent>=30)return false;lastKey=key;lastAt=now;sent++;
   const payload={kind:safeText(kind,80),message,stack,source:safeText(extra.source||'',400),line:Number(extra.line||0),column:Number(extra.column||0),page:safeText(getPage?.()||'',120),version:safeText(version,40),time:new Date().toISOString()};
   if((state?.server||state?.portable)&&globalThis.fetch){await fetch(endpoint,{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).catch(()=>{})}
   return true;
  }catch(e){return false}
 }
 if(globalThis.addEventListener){
  globalThis.addEventListener('error',e=>{report('window_error',e.error||e.message,{source:e.filename,line:e.lineno,column:e.colno})});
  globalThis.addEventListener('unhandledrejection',e=>{report('unhandled_rejection',e.reason||'Promise rejection')});
 }
 return Object.freeze({report,safeText});
}

const api=Object.freeze({version:VERSION,createStorage,debounce,idleRun,safeText,createApi,createPortableApi,createStandaloneDb,createScriptLoader,installDiagnostics});
if(typeof window!=='undefined')window.SazmanHRRuntimeCore=api;
else globalThis.SazmanHRRuntimeCore=api;
})();
