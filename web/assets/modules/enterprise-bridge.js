(function(global){
'use strict';
const VERSION='1.0.0-rc.3';
const pre=global.__SAZMANHR_PREAUTH__||{};
const token=String(pre.token||'');
const user=pre.user||{};
const permissions=pre.permissions||user.permissions||{};
const $=s=>document.querySelector(s);
const esc=(value)=>String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
const fa=(value)=>Number(value||0).toLocaleString('fa-IR');
let lastPreview=null;

function notify(title,text,type){
 if(typeof global.toast==='function')global.toast(title,text,type);
 else if(type==='error')global.alert(`${title}\n${text||''}`);
}
async function errorText(response){
 const text=await response.text();
 try{const j=JSON.parse(text);return j.error||j.message||text}catch(_){return text||`خطای ${response.status}`}
}
async function json(path,{method='GET',body=null,headers={}}={}){
 const h={'Accept':'application/json','X-Token':token,...headers};
 let payload=body;
 if(body!==null && !(body instanceof ArrayBuffer) && !(body instanceof Uint8Array)){
  h['Content-Type']='application/json';payload=JSON.stringify(body);
 }
 const r=await fetch(path,{method,cache:'no-store',headers:h,body:payload});
 if(!r.ok)throw new Error(await errorText(r));
 const text=await r.text();return text?JSON.parse(text):{};
}
function setImportStep(step){
 const root=$('#org460ImportSteps');if(!root)return;
 root.querySelectorAll('[data-step]').forEach(el=>{const n=+el.dataset.step;el.classList.toggle('active',n===step);el.classList.toggle('done',n<step)});
}
function importBox(){return $('#importPreview')}
function importError(message){
 const box=importBox();if(!box)return;
 setImportStep(2);box.innerHTML=`<div class="empty-state"><div>!</div><h3>فایل قابل پردازش نبود</h3><p>${esc(message)}</p></div>`;
 notify('Dry Run ناموفق بود',message,'error');
}

async function enterprisePreviewImport(input){
 const file=input?.files?.[0];if(!file)return;
 const box=importBox();if(!box)return;
 lastPreview=null;setImportStep(2);
 box.innerHTML='<div class="empty-state"><div class="loader"></div><h3>در حال Dry Run و اعتبارسنجی…</h3><p>اطلاعات فردی، تکرارها، مقصدهای جانمایی و تفاوت با داده جاری بررسی می‌شوند.</p></div>';
 if(!permissions.edit_data){importError('این عملیات نیازمند مجوز ویرایش داده است.');return}
 if(!/\.xlsx$/i.test(file.name)){importError('فقط فایل استاندارد .xlsx پذیرفته می‌شود.');return}
 if(file.size>24*1024*1024){importError('حداکثر حجم فایل ماهانه ۲۴ مگابایت است.');return}
 try{
  const r=await fetch('/api/import/preview',{method:'POST',cache:'no-store',headers:{'X-Token':token,'X-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream','Accept':'application/json'},body:await file.arrayBuffer()});
  if(!r.ok)throw new Error(await errorText(r));
  const preview=await r.json();lastPreview=preview;
  if(typeof global.renderImportPreview!=='function')throw new Error('رندر پیش‌نمایش نسخه 4.9 در دسترس نیست.');
  global.renderImportPreview(preview);
  if(typeof global.renderImports==='function')await global.renderImports();
 }catch(error){importError(String(error?.message||error))}
}

async function enterpriseApplyImport(){
 const box=importBox();const id=String(box?.dataset.preview||lastPreview?.preview_id||'');
 if(!id||!lastPreview)return;
 const s=lastPreview.summary||{};
 if(!global.confirm(`تأیید نهایی اعمال Excel؟\n\nنیروی جدید: ${s.new_people||0}\nافراد تغییرکرده: ${s.updated_people||0}\nجانمایی/جابه‌جایی: ${s.assignment_moves||0}\n\nقبل از اعمال، پشتیبان کامل ساخته می‌شود.`))return;
 const btn=$('#applyImport');if(btn)btn.disabled=true;setImportStep(4);
 try{
  const result=await json('/api/import/apply',{method:'POST',body:{preview_id:id}});
  const data=await json('/api/bootstrap');
  if(typeof global.hydrate==='function')global.hydrate(data);
  if(typeof global.renderAll==='function')global.renderAll();
  if(typeof global.resetDerivedCaches==='function')global.resetDerivedCaches();
  if(typeof global.captureStatusSnapshot==='function')await global.captureStatusSnapshot('به‌روزرسانی Excel ماهانه').catch(()=>{});
  setImportStep(5);
  if(box)box.innerHTML=`<div class="empty-state"><div>✓</div><h3>به‌روزرسانی ماهانه با موفقیت اعمال شد</h3><p>${fa(result.new_people)} نیروی جدید، ${fa(result.updated_people)} فرد تغییرکرده و ${fa(result.assignments)} جانمایی اعمال شد. لیست پرسنل، چارت، وضعیت چارت و گزارش‌ها اکنون از داده جدید استفاده می‌کنند.</p><small>Batch: ${esc(result.batch_id||'—')} • پشتیبان ایمنی: ${esc(result.backup||'—')} • تعداد فعلی: ${fa(result.people_after)}</small></div>`;
  lastPreview=null;
  if(typeof global.renderImports==='function')await global.renderImports();
  notify('Excel ماهانه اعمال شد',`${fa(result.people_after)} نفر در داده جاری`);
 }catch(error){setImportStep(3);if(btn)btn.disabled=false;notify('اعمال تغییرات ناموفق بود',String(error?.message||error),'error')}
}

async function enterpriseBackup(){
 if(!permissions.backup_restore){notify('دسترسی محدود','حساب شما مجوز تهیه پشتیبان کامل را ندارد.','error');return}
 try{
  const client=global.SazmanHRBackupClient;if(!client)throw new Error('ماژول پشتیبان‌گیری بارگذاری نشده است.');
  const result=await client.download({token});
  notify('پشتیبان کامل ساخته شد',`${result.filename} — داده، حساب‌ها و سوابق`);
  if(typeof global.renderHistory==='function')global.renderHistory();
 }catch(error){notify('پشتیبان‌گیری ناموفق بود',String(error?.message||error),'error')}
}

async function enterpriseRestore(input){
 const file=input?.files?.[0];if(!file)return;
 try{
  if(String(user.role||'')!=='owner')throw new Error('بازیابی پشتیبان فقط برای مدیر ارشد مجاز است.');
  const client=global.SazmanHRBackupClient;if(!client)throw new Error('ماژول پشتیبان‌گیری بارگذاری نشده است.');
  const meta=await client.inspect({token,file});
  const summary=`نسخه ${meta.app_version||'—'} • ${fa(meta.people)} نفر • ${fa(meta.slides)} صفحه • ${meta.created_at||'—'}`;
  if(!global.confirm(`پشتیبان «${file.name}» بازیابی شود؟\n${summary}\n\nپیش از بازیابی یک نسخه ایمنی خودکار ساخته می‌شود. پس از بازیابی باید دوباره وارد سامانه شوید.`))return;
  const result=await client.restore({token,file});
  notify('پشتیبان کامل بازیابی شد',`نسخه ایمنی: ${result.safety_backup||'ایجاد شد'}`);
  setTimeout(()=>global.location.reload(),500);
 }catch(error){notify('بازیابی ناموفق بود',String(error?.message||error),'error')}
 finally{input.value=''}
}

// Replace behavior only.  DOM, CSS and the locked v4.9 app bundle remain
// untouched, which keeps visual parity auditable by hash and screenshot.
global.previewImport=enterprisePreviewImport;
global.applyImport=enterpriseApplyImport;
const backup=$('#backupNow');if(backup)backup.onclick=enterpriseBackup;
const restore=$('#restoreBackup'),restoreInput=$('#restoreBackupInput');
if(restore&&restoreInput){
 if(String(user.role||'')!=='owner')restore.classList.add('hidden');
 else restore.onclick=()=>restoreInput.click();
 restoreInput.onchange=()=>enterpriseRestore(restoreInput);
}

global.__SAZMANHR_ENTERPRISE_BRIDGE__=Object.freeze({
 version:VERSION,
 mode:'central-server',
 capabilities:{monthlyImport:true,binaryBackup:true,ownerRestore:true,movementBoundary:true},
 role:String(user.role||''),
});
})(window);
