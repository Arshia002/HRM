(function(global){
'use strict';
const VERSION='4.9.0';
const $=selector=>document.querySelector(selector);
const state={portable:false,server:false,token:'',csrf:''};
const runtime=global.SazmanHRRuntimeCore;
if(!runtime)throw new Error('Runtime Core برای ورود امن در دسترس نیست.');
const api=runtime.createApi({state,getToken:()=>state.token});
const portableApi=runtime.createPortableApi({state,getToken:()=>state.token});
const services=global.SazmanHRApplicationServices?.create({api,portableApi,state});
if(!services)throw new Error('Application Services برای ورود امن در دسترس نیست.');

const moduleScripts=[
 'assets/modules/xlsx-engine.js',
 'assets/modules/backup-client.js',
 'assets/modules/job-family-engine.js',
 'assets/modules/access-control.js'
];
const postAppScripts=[
 'assets/modules/enterprise-bridge.js',
 'assets/modules/global-search.js',
 'assets/modules/audit-center.js',
 'assets/modules/system-health.js',
 'assets/modules/security-ui.js',
 'assets/modules/accessibility.js',
 'assets/modules/organization-overrides.js'
];

function message(value){
 const raw=String(value?.message||value||'خطای ناشناخته').replace(/^Error:\s*/, '');
 try{const parsed=JSON.parse(raw);return parsed.error||parsed.message||raw}catch(_){return raw}
}
function busy(active,label='در حال بررسی…'){
 document.body.classList.toggle('login-busy',!!active);
 ['#passwordSubmit','#setupSubmit'].forEach(id=>{const el=$(id);if(el)el.disabled=!!active});
 if(active&&$('#loginDesc'))$('#loginDesc').textContent=label;
}
function showError(text){if($('#loginError'))$('#loginError').textContent=text||''}
function showLogin(){
 $('#ownerSetupForm')?.classList.add('hidden');
 $('#passwordForm')?.classList.remove('hidden');
 if($('#loginTitle'))$('#loginTitle').textContent='ورود به سامانه';
 if($('#loginDesc'))$('#loginDesc').textContent='نام کاربری و رمز عبور خود را وارد کنید.';
 showError('');
}
function showSetup(mode){
 $('#passwordForm')?.classList.add('hidden');
 $('#ownerSetupForm')?.classList.remove('hidden');
 const identity=$('#setupIdentityFields');
 identity?.classList.toggle('hidden',mode==='upgrade');
 if($('#setupUsername'))$('#setupUsername').required=mode!=='upgrade';
 if($('#setupFullName'))$('#setupFullName').required=mode!=='upgrade';
 if($('#loginTitle'))$('#loginTitle').textContent=mode==='upgrade'?'ایمن‌سازی حساب مدیر اصلی':'راه‌اندازی مدیر اصلی';
 if($('#loginDesc'))$('#loginDesc').textContent=mode==='upgrade'?'رمز مشترک نسخه قبلی غیرفعال شده است؛ یک رمز اختصاصی تعیین کنید.':'این نصب حساب پیش‌فرض ندارد؛ مدیر اصلی را همین حالا ایجاد کنید.';
 $('#ownerSetupForm').dataset.mode=mode||'fresh';
 showError('');
}
function loadScript(path){
 return new Promise((resolve,reject)=>{
  const nativeAdd=global.addEventListener;
  let restored=false;
  const restore=()=>{if(!restored){global.addEventListener=nativeAdd;restored=true}};
  // app.js contains legacy load hooks. Because it is intentionally fetched
  // after authentication (often after window.load), replay only registrations
  // made by this late-loaded script instead of dispatching a second global
  // load event to the whole document.
  if(document.readyState==='complete')global.addEventListener=function(type,listener,options){
   if(type==='load'){
    queueMicrotask(()=>{try{if(typeof listener==='function')listener.call(global,new Event('load'));else listener?.handleEvent?.(new Event('load'))}catch(error){setTimeout(()=>{throw error})}});
    return;
   }
   return nativeAdd.call(global,type,listener,options);
  };
  const script=document.createElement('script');script.src=path+'?v='+encodeURIComponent(VERSION);script.defer=true;
  script.onload=()=>{restore();resolve(path)};script.onerror=()=>{restore();reject(new Error('بارگذاری ماژول ناموفق بود: '+path))};document.head.appendChild(script);
 });
}
async function completeRequiredPasswordChange(login,currentPassword){
 if(!(login?.must_change||login?.user?.must_change_password))return;
 const first=String(global.prompt('رمز موقت را تغییر دهید. رمز جدید حداقل ۶ نویسه و بدون فاصله باشد:')||'').trim();
 if(!first)throw new Error('تغییر رمز اولیه لغو شد.');
 if([...first].length<6||/\s/u.test(first))throw new Error('رمز جدید باید حداقل ۶ نویسه و بدون فاصله باشد.');
 const second=String(global.prompt('رمز جدید را دوباره وارد کنید:')||'').trim();
 if(first!==second)throw new Error('تکرار رمز عبور یکسان نیست.');
 await services.changePassword(currentPassword,first);
 login.must_change=false;if(login.user){login.user.must_change=false;login.user.must_change_password=0}
}
async function startApplication(login,currentPassword=''){
 state.token=login.token||'';state.csrf=login.csrf||'';
 if(!state.token||!state.csrf)throw new Error('پاسخ ورود فاقد توکن‌های امنیتی لازم است.');
 await completeRequiredPasswordChange(login,currentPassword);
 const moduleReady=(async()=>{for(const path of moduleScripts)await loadScript(path)})();
 const [bootstrap,placement,education]=await Promise.all([
  services.bootstrap(),services.privateDataset('placement-models'),services.privateDataset('person-education'),moduleReady
 ]);
 global.SazmanHRPlacementModels=Object.freeze(placement);
 global.PERSON_EDUCATION_V4149=education;
 global.__SAZMANHR_PREAUTH__={token:state.token,csrf:state.csrf,user:login.user,permissions:login.permissions||{},bootstrap,portable:state.portable,server:state.server};
 await loadScript('assets/app.js');
 for(const path of postAppScripts)await loadScript(path);
 const form=$('#passwordForm');if(form)form.onsubmit=null;
}
async function submitLogin(event){
 event.preventDefault();showError('');
 const username=String($('#usernameInput')?.value||'').trim().toLowerCase();
 const password=String($('#passwordInput')?.value||'').trim();
 if(!username||!password){showError('نام کاربری و رمز عبور را کامل وارد کنید.');return}
 busy(true,'در حال ورود و دریافت امن اطلاعات…');
 try{await startApplication(await services.login({username,password}),password);busy(false)}
 catch(error){try{if(state.token)await services.logout()}catch(_){}state.token='';state.csrf='';showError(message(error));busy(false,'نام کاربری و رمز عبور خود را وارد کنید.')}
}
async function submitSetup(event){
 event.preventDefault();showError('');
 const mode=$('#ownerSetupForm')?.dataset.mode||'fresh';
 const password=String($('#setupPassword')?.value||'').trim();
 const confirm=String($('#setupPasswordConfirm')?.value||'').trim();
 if([...password].length<6){showError('رمز عبور باید حداقل ۶ نویسه و بدون فاصله باشد.');return}
 if(/\s/u.test(password)){showError('رمز عبور نباید فاصله داشته باشد.');return}
 if(password!==confirm){showError('تکرار رمز عبور یکسان نیست.');return}
 const payload={password};
 if(mode!=='upgrade'){
  payload.username=String($('#setupUsername')?.value||'').trim().toLowerCase();
  payload.full_name=String($('#setupFullName')?.value||'').trim();
  payload.title=String($('#setupTitle')?.value||'').trim();
  payload.phone=String($('#setupPhone')?.value||'').trim();
 }
 busy(true,'در حال ایجاد امن مدیر اصلی…');
 try{
  const result=await services.createOwner(payload);
  showLogin();if($('#usernameInput'))$('#usernameInput').value=result.username||payload.username||'';
  if($('#passwordInput'))$('#passwordInput').focus();
  if($('#loginDesc'))$('#loginDesc').textContent='راه‌اندازی امن تکمیل شد؛ اکنون وارد شوید.';
 }catch(error){showError(message(error))}
 finally{busy(false)}
}
async function boot(){
 const login=$('#loginScreen');login?.classList.remove('hidden');$('#appShell')?.classList.add('hidden');
 const status=await api.detect();
 if(!status.portable&&!status.server){
  showLogin();showError('سرور محلی در دسترس نیست؛ برنامه SazmanHR.exe را اجرا کنید.');
  if($('#passwordSubmit'))$('#passwordSubmit').disabled=true;return;
 }
 state.portable=!!status.portable;state.server=!!status.server;
 const setup=await services.setupStatus();
 if(setup.required)showSetup(setup.mode);else showLogin();
}

$('#passwordForm').onsubmit=submitLogin;
$('#ownerSetupForm').onsubmit=submitSetup;
$('#togglePassword')?.addEventListener('click',()=>{const input=$('#passwordInput');if(input)input.type=input.type==='password'?'text':'password'});
global.__SAZMANHR_AUTH_SHELL__=Object.freeze({version:VERSION,state:()=>({...state})});
boot().catch(error=>{showError(message(error));busy(false)});
})(window);
