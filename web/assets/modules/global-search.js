(function(global){
'use strict';
const VERSION='4.9.0';
const norm=v=>String(v??'').toLowerCase().replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d));
function mount(bridge){
 if(document.getElementById('globalSearchPalette'))return;
 const palette=document.createElement('div');palette.id='globalSearchPalette';palette.className='global-search-palette hidden';palette.setAttribute('role','dialog');palette.setAttribute('aria-modal','true');palette.setAttribute('aria-label','جست‌وجوی سراسری');
 palette.innerHTML='<div class="global-search-dialog"><div class="global-search-field"><input id="globalSearch" type="search" autocomplete="off" placeholder="جست‌وجوی نام، شماره پرسنلی، پست یا واحد…"/><span>Esc</span></div><div id="globalSearchResults" class="global-search-results"><div class="global-search-empty">برای جست‌وجو حداقل دو نویسه وارد کنید.</div></div></div>';
 document.body.appendChild(palette);
 const input=palette.querySelector('#globalSearch'),results=palette.querySelector('#globalSearchResults');
 const clearResults=()=>{results.innerHTML='<div class="global-search-empty">برای جست‌وجو حداقل دو نویسه وارد کنید.</div>'};
 const close=()=>{palette.classList.add('hidden');input.value='';clearResults()};
 const open=()=>{palette.classList.remove('hidden');requestAnimationFrame(()=>{input.focus();input.select()})};
 function run(){const q=norm(input.value).trim();if(q.length<2){clearResults();return}const rows=bridge.people().filter(p=>norm([p.full_name,p.personnel_no,p.position_title,p.organizational_unit,p.actual_location,p.activity_area].join(' ')).includes(q)).slice(0,12);results.innerHTML=rows.length?rows.map(p=>`<button type="button" data-person="${bridge.escape(p.id)}"><b>${bridge.escape(p.full_name||'—')}</b><span>${bridge.escape(p.personnel_no||'—')} • ${bridge.escape(p.position_title||'—')}</span><small>${bridge.escape(p.organizational_unit||p.actual_location||'—')}</small></button>`).join(''):'<div class="global-search-empty">نتیجه‌ای پیدا نشد.</div>';results.querySelectorAll('[data-person]').forEach(b=>b.onclick=()=>{const id=b.dataset.person;close();bridge.openPerson(id)})}
 input.addEventListener('input',run);
 input.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close()}});
 palette.addEventListener('mousedown',e=>{if(e.target===palette)close()});
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();palette.classList.contains('hidden')?open():close()}else if(e.key==='Escape'&&!palette.classList.contains('hidden'))close()});
 global.__SAZMANHR_OPEN_GLOBAL_SEARCH__=open;
}
global.SazmanHRGlobalSearch={version:VERSION,mount};
window.addEventListener('load',()=>global.SazmanHRAppBridge&&mount(global.SazmanHRAppBridge));
})(window);
