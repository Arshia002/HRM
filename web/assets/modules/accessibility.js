(function(global){
'use strict';
function labelControls(root=document){
 root.querySelectorAll('button').forEach(button=>{
  const text=(button.textContent||'').replace(/\s+/g,' ').trim();
  if(!button.getAttribute('aria-label')&&!button.getAttribute('aria-labelledby')&&!text){
   button.setAttribute('aria-label',button.getAttribute('title')||'دکمه');
  }
 });
 const theme=document.getElementById('themeToggle');
 if(theme){theme.removeAttribute('aria-hidden');theme.setAttribute('aria-label','تغییر قالب نمایش')}
 const modal=document.getElementById('personModal');
 if(modal){modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label','پنجره جزئیات')}
 document.querySelectorAll('.modal-close').forEach(button=>button.setAttribute('aria-label','بستن پنجره'));
 ['loginError','toastStack'].forEach(id=>{const el=document.getElementById(id);if(el&&!el.hasAttribute('aria-live'))el.setAttribute('aria-live',id==='loginError'?'assertive':'polite')});
}
labelControls();
const observer=new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===Node.ELEMENT_NODE)labelControls(node)})));
observer.observe(document.body,{childList:true,subtree:true});
global.__SAZMANHR_ACCESSIBILITY__=Object.freeze({version:'4.9.0',audit(){const buttons=[...document.querySelectorAll('button')];return{buttons:buttons.length,unlabelled:buttons.filter(b=>!b.getAttribute('aria-label')&&!b.getAttribute('aria-labelledby')&&!(b.textContent||'').trim()).length,themeHidden:document.getElementById('themeToggle')?.getAttribute('aria-hidden')==='true'}}});
})(window);
