(() => {
'use strict';
/* Binary backup transport is isolated from the main UI bundle. */
function saveBlob(blob,name){
  const url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=name||'SazmanHR-Backup.sazhr.zip';a.rel='noopener';a.style.display='none';
  document.body.appendChild(a);requestAnimationFrame(()=>a.click());
  setTimeout(()=>{a.remove();URL.revokeObjectURL(url)},60000);
}
async function errorText(response){
  const text=await response.text();
  try{const j=JSON.parse(text);return j.error||j.message||text}catch(e){return text||`خطای ${response.status}`}
}
async function download({token}={}){
  const headers={'Accept':'application/zip'};if(token)headers['X-Portable-Token']=token;
  const r=await fetch('/portable-api/backup',{method:'POST',cache:'no-store',headers});
  if(!r.ok)throw new Error(await errorText(r));
  const blob=await r.blob();
  const name=r.headers.get('X-SazmanHR-Backup-File')||'SazmanHR-Backup.sazhr.zip';
  const sha256=r.headers.get('X-SazmanHR-Backup-SHA256')||'';
  if(blob.size<500)throw new Error('فایل پشتیبان کامل ساخته نشد.');
  saveBlob(blob,name);
  return {filename:name,size:blob.size,sha256};
}
async function inspect({token,file}={}){
  if(!file)throw new Error('فایل پشتیبان انتخاب نشده است.');
  const raw=await file.arrayBuffer();if(raw.byteLength<500)throw new Error('فایل پشتیبان بسیار کوچک یا نامعتبر است.');
  const headers={'Accept':'application/json','Content-Type':'application/zip'};if(token)headers['X-Portable-Token']=token;
  const r=await fetch('/portable-api/backup/inspect',{method:'POST',cache:'no-store',headers,body:raw});
  if(!r.ok)throw new Error(await errorText(r));
  return r.json();
}

async function restore({token,file}={}){
  if(!file)throw new Error('فایل پشتیبان انتخاب نشده است.');
  const raw=await file.arrayBuffer();if(raw.byteLength<500)throw new Error('فایل پشتیبان بسیار کوچک یا نامعتبر است.');
  const headers={'Accept':'application/json','Content-Type':'application/zip'};if(token)headers['X-Portable-Token']=token;
  const r=await fetch('/portable-api/backup/restore',{method:'POST',cache:'no-store',headers,body:raw});
  if(!r.ok)throw new Error(await errorText(r));
  return r.json();
}
window.SazmanHRBackupClient={version:'4.9.0',download,inspect,restore,saveBlob};
})();
