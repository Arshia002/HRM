(()=>{
'use strict';
const norm=s=>String(s||'').replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/\s+/g,' ').trim().toLowerCase();
const classes=Object.freeze({
 technical:{label:'فنی و عملیاتی',icon:'⚡',color:'#27945C',soft:'#E2F3E7'},
 nontechnical:{label:'غیرفنی و اداری',icon:'▦',color:'#3378CF',soft:'#E5EFFD'},
 review:{label:'نیازمند تعیین گروه',icon:'؟',color:'#D8A11F',soft:'#FFF2C9'}
});
const families=Object.freeze([
 {key:'سیمبان',classKey:'technical',color:'#218A54'},
 {key:'قرائت و وصول مطالبات',classKey:'technical',color:'#2E78C7'},
 {key:'قطع‌ووصل، نصب و تست کنتور',classKey:'technical',color:'#D97820'},
 {key:'بهره‌برداری، دیسپاچینگ و فوریت‌ها',classKey:'technical',color:'#8557C7'},
 {key:'تعمیرات، شبکه و روشنایی',classKey:'technical',color:'#148E8E'},
 {key:'مهندسی، GIS و فناوری اطلاعات',classKey:'technical',color:'#3B8A9C'},
 {key:'خدمات مشترکین، فروش و وصول',classKey:'nontechnical',color:'#C45A83'},
 {key:'مالی، اداری و منابع انسانی',classKey:'nontechnical',color:'#52729A'},
 {key:'حقوقی، حراست، ایمنی و بازرسی',classKey:'nontechnical',color:'#9A6A42'},
 {key:'حمل‌ونقل، خدمات و پشتیبانی',classKey:'nontechnical',color:'#6A7B87'},
 {key:'مدیریت و سرپرستی',classKey:'nontechnical',color:'#8B6AB6'},
 {key:'مشاور',classKey:'nontechnical',color:'#B47259'},
 {key:'نیازمند تعیین گروه',classKey:'review',color:'#D8A11F'}
]);
const has=(text,...terms)=>terms.some(term=>text.includes(norm(term)));
let classificationCache=new WeakMap(),cacheHits=0,cacheMisses=0;
function classifyUncached(person){
 const title=norm(person?.position_title||''),activity=norm(person?.activity_area||''),unit=norm(person?.organizational_unit||''),location=norm(person?.actual_location||''),context=[title,activity,unit,location].join(' | ');
 const out=(category,classKey,source)=>({person,category,classKey,classLabel:classes[classKey].label,source});
 if(has(title,'سیمبان'))return out('سیمبان','technical','عنوان پست');
 if(has(title,'مامور قرائت','مأمور قرائت','قرائت کنتور','قرائت'))return out('قرائت و وصول مطالبات','technical','عنوان پست');
 if(has(title,'قطع و وصل','نصب کنتور','تست کنتور','تست دیماندی','تست ديماندی','لوازم اندازه گیری','لوازم اندازه‌گیری','کنتور'))return out('قطع‌ووصل، نصب و تست کنتور','technical','عنوان پست');
 if(has(title,'اپراتور 121','اپراتور فوریت','فوریت های برق','فوریتهای برق','دیسپاچ','بهره بردار','بهره‌بردار','بهره برداری','بهره‌برداری','مسئول شیفت','تکنسین شیفت','تکنیسین شیفت','بازار برق','کنترل بار','پدافند'))return out('بهره‌برداری، دیسپاچینگ و فوریت‌ها','technical','عنوان پست');
 if(has(title,'تعمیرات','نوسازی','شبکه','روشنایی','معابر','برقکار','برق کار','کارگر فنی','تکنسین برق','تکنیسین برق','عیب یابی','عیب‌یابی','حریم بان'))return out('تعمیرات، شبکه و روشنایی','technical','عنوان پست');
 if(has(title,'برآورد تجهیزات','برآورد تجهيزات','تجزیه و تحلیل آمار','تجزيه و تحليل آمار','مهندس','مهندسی','طراحی','gis','فناوری اطلاعات','شبکه و امنیت','it','اتوماسیون','نقشه بردار','نقشه‌بردار','برق روستایی','نظارت فنی','تولید پراکنده','پروژه','برنامه ریزی فنی','برنامه‌ریزی فنی'))return out('مهندسی، GIS و فناوری اطلاعات','technical','عنوان پست');
 if(has(title,'فروش','مشترکین','وصول مطالبات','انشعاب','مدیریت مصرف','خدمات مشترکین','اپراتور مشترکین'))return out('خدمات مشترکین، فروش و وصول','nontechnical','عنوان پست');
 if(has(title,'مالی','حسابرس','حسابدار','حسابداری','خزانه','بودجه','درآمد','ذیحساب','کارپرداز','تدارکات','انبار','اداری','متصدی امور دفتری','کارگزینی','منابع انسانی','امور کارکنان','آموزش','رفاه','طبقه بندی','طبقه‌بندی','حقوق و دستمزد','دبیرخانه','بایگانی'))return out('مالی، اداری و منابع انسانی','nontechnical','عنوان پست');
 if(has(title,'حقوقی','حراست','نگهبان','امنیت','ایمنی','بازرسی','کنترل ضایعات','کشف ماینر','دوربین','محرمانه'))return out('حقوقی، حراست، ایمنی و بازرسی','nontechnical','عنوان پست');
 if(has(title,'راننده','خدمات عمومی','تنظیفات','آبدارچی','کارگر چاله کن','تلفنچی','پشتیبانی','خدمتگزار','تایپیست','توزیع نامه'))return out('حمل‌ونقل، خدمات و پشتیبانی','nontechnical','عنوان پست');
 if(has(title,'مشاور'))return out('مشاور','nontechnical','عنوان پست');
 if(has(context,'اتفاقات و عملیات','بهره برداری','دیسپاچ','فوریت','تعمیرات','شبکه','مهندسی','gis','فناوری اطلاعات','لوازم اندازه گیری'))return out('بهره‌برداری، دیسپاچینگ و فوریت‌ها','technical','حوزه فعالیت / واحد');
 if(has(context,'مشترکین','فروش','وصول مطالبات'))return out('خدمات مشترکین، فروش و وصول','nontechnical','حوزه فعالیت / واحد');
 if(has(context,'مالی','اداری','منابع انسانی','تدارکات','کارکنان'))return out('مالی، اداری و منابع انسانی','nontechnical','حوزه فعالیت / واحد');
 if(has(context,'حراست','حقوقی','ایمنی'))return out('حقوقی، حراست، ایمنی و بازرسی','nontechnical','حوزه فعالیت / واحد');
 if(has(title,'مدیر','رئیس','سرپرست','مسئول','معاون','مجری'))return out('مدیریت و سرپرستی','nontechnical','عنوان مدیریتی عمومی');
 return out('نیازمند تعیین گروه','review','عنوان یا اطلاعات ناکافی');
}
function classify(person){
 if(!person||typeof person!=='object')return classifyUncached(person);
 const cached=classificationCache.get(person);
 if(cached){cacheHits++;return cached}
 const result=classifyUncached(person);classificationCache.set(person,result);cacheMisses++;return result;
}
function clearCache(){classificationCache=new WeakMap();cacheHits=0;cacheMisses=0}
function cacheStats(){return Object.freeze({hits:cacheHits,misses:cacheMisses})}
const records=people=>(people||[]).map(classify);
function summarize(people){
 const rec=records(people),counts={technical:0,nontechnical:0,review:0},familyCounts={};families.forEach(x=>familyCounts[x.key]=0);
 rec.forEach(x=>{counts[x.classKey]=(counts[x.classKey]||0)+1;familyCounts[x.category]=(familyCounts[x.category]||0)+1});
 return{records:rec,classes:counts,families:familyCounts,total:rec.length};
}
function filter(people,{classKey='',category='',employment='',search=''}={}){
 const q=norm(search);
 return records(people).filter(x=>{const p=x.person;if(classKey&&x.classKey!==classKey)return false;if(category&&x.category!==category)return false;if(employment&&p.employment_group!==employment)return false;if(!q)return true;return[p.full_name,p.personnel_no,p.position_title,p.activity_area,p.organizational_unit,p.actual_location,p.employment_group,x.category,x.classLabel].some(v=>norm(v).includes(q))});
}
window.SazmanHRJobFamilyEngine=Object.freeze({version:'4.9.0',classes,families,normalize:norm,classify,records,summarize,filter,clearCache,cacheStats});
})();
