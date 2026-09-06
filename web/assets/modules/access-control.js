(function(global){
  'use strict';
  const VERSION='4.9.0';
  const KEYS={editData:'edit_data',viewHistory:'view_history',backupRestore:'backup_restore',manageUsers:'manage_users',shutdown:'shutdown'};
  const DELEGABLE=[KEYS.editData,KEYS.viewHistory,KEYS.backupRestore];
  const LABELS={edit_data:'ویرایش اطلاعات و ورود Excel',view_history:'مشاهده سوابق فعالیت',backup_restore:'پشتیبان‌گیری و بازیابی کامل',manage_users:'مدیریت کاربران',shutdown:'بستن کامل سامانه'};
  const DESCRIPTIONS={edit_data:'اجازه ثبت تغییرات پرسنلی، جانمایی و اعمال فایل‌های Excel',view_history:'اجازه مشاهده تاریخچه ورودها و تغییرات ثبت‌شده کاربران',backup_restore:'اجازه تهیه و بازیابی پشتیبان کامل داده‌ها، حساب‌ها و سوابق'};
  function roleOf(role){role=String(role||'').toLowerCase();return role==='owner'?'owner':role==='viewer'?'viewer':'admin'}
  function normalize(role,raw){
    role=roleOf(role);
    if(role==='owner')return {edit_data:true,view_history:true,backup_restore:true,manage_users:true,shutdown:true};
    if(role==='viewer')return {edit_data:false,view_history:false,backup_restore:false,manage_users:false,shutdown:false};
    const src=raw&&typeof raw==='object'?raw:{};
    return {edit_data:Object.prototype.hasOwnProperty.call(src,'edit_data')?!!src.edit_data:true,view_history:Object.prototype.hasOwnProperty.call(src,'view_history')?!!src.view_history:true,backup_restore:Object.prototype.hasOwnProperty.call(src,'backup_restore')?!!src.backup_restore:false,manage_users:false,shutdown:false};
  }
  function can(perms,key){return !!(perms&&perms[key])}
  function roleLabel(role){role=roleOf(role);return role==='owner'?'مدیر اصلی سامانه':role==='viewer'?'مشاهده‌گر':'کاربر مدیریتی'}
  function permissionSummary(role,raw){role=roleOf(role);if(role==='owner')return 'دسترسی کامل مدیر اصلی';if(role==='viewer')return 'فقط مشاهده اطلاعات؛ بدون ویرایش، تاریخچه و پشتیبان';const p=normalize(role,raw),enabled=DELEGABLE.filter(k=>p[k]).map(k=>LABELS[k]);return enabled.length?enabled.join('، '):'کاربر مدیریتی بدون مجوز عملیاتی'}
  function formValues(role,raw){const p=normalize(role,raw);return DELEGABLE.map(key=>({key,label:LABELS[key],description:DESCRIPTIONS[key],checked:!!p[key]}))}
  global.SazmanHRAccessControl={version:VERSION,keys:KEYS,delegable:DELEGABLE,labels:LABELS,descriptions:DESCRIPTIONS,normalize,can,roleLabel,permissionSummary,formValues,roleOf};
})(window);
