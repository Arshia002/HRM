(function(global){
'use strict';const VERSION='4.9.0';
function decorateUserForm(form,user=null){
 if(!form||user?.role==='owner'||form.querySelector('[name="role"]'))return;
 const grid=form.querySelector('.form-grid');if(!grid)return;
 const label=document.createElement('label');label.className='security-role-field';label.innerHTML='<span>نقش حساب</span><select name="role"><option value="admin">کاربر مدیریتی</option><option value="viewer">مشاهده‌گر فقط‌خواندنی</option></select>';
 const select=label.querySelector('select');select.value=user?.role==='viewer'?'viewer':'admin';grid.insertBefore(label,grid.children[2]||null);
 const fieldset=form.querySelector('.permission-fieldset');const toggle=()=>{if(fieldset)fieldset.classList.toggle('hidden',select.value==='viewer')};select.addEventListener('change',toggle);toggle();
}
function mount(bridge){
 const cp=document.getElementById('changePassword');if(cp)cp.onclick=async()=>{const u=bridge.currentUser();if(!u)return;const current=window.prompt('رمز فعلی را وارد کنید:');if(!current)return;const first=window.prompt('رمز جدید حداقل ۶ نویسه و بدون فاصله:');if(!first)return;const second=window.prompt('رمز جدید را دوباره وارد کنید:');if(first!==second)return bridge.toast('تکرار رمز یکسان نیست','','error');try{await bridge.post('/change-password',{current_password:current,password:first});bridge.toast('رمز شخصی تغییر کرد','رمز جدید پس از خروج، Restart و Upgrade حفظ می‌شود.')}catch(e){bridge.toast('تغییر رمز ناموفق',e.message||String(e),'error')}};
}
global.SazmanHRSecurityUI={version:VERSION,mount,decorateUserForm};window.addEventListener('load',()=>global.SazmanHRAppBridge&&mount(global.SazmanHRAppBridge));
})(window);
