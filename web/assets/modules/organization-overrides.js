(function(global){
'use strict';
const VERSION='1.0.0-rc.3';
const PUBLISHER_FA='ارشیا شهبازی';
const PUBLISHER_EN='Arshia Shahbazi';
const REPORTS_ISSUE_SELECTOR='#org450Kpis [data-org450-action="issue"]';
let reportsObserver=null;
let discoveryObserver=null;

function hideReportsInspectionKpi(root=document){
 const card=root.querySelector?.(REPORTS_ISSUE_SELECTOR);
 if(!card)return;
 card.hidden=true;
 card.disabled=true;
 card.setAttribute('aria-hidden','true');
 card.tabIndex=-1;
 card.style.setProperty('display','none','important');
}

function bindReportsKpis(){
 const host=document.querySelector('#org450Kpis');
 if(!host)return false;
 hideReportsInspectionKpi(host);
 if(reportsObserver)reportsObserver.disconnect();
 reportsObserver=new MutationObserver(()=>hideReportsInspectionKpi(host));
 reportsObserver.observe(host,{childList:true,subtree:true});
 return true;
}

function addPublisherInfo(){
 const info=document.querySelector('#page-settings .info-list');
 if(!info)return false;
 if(info.querySelector('[data-rc3-publisher]'))return true;
 const row=document.createElement('div');
 row.setAttribute('data-rc3-publisher','true');
 const label=document.createElement('dt');
 const value=document.createElement('dd');
 label.textContent='ناشر';
 value.textContent=PUBLISHER_FA;
 value.title=PUBLISHER_EN;
 row.append(label,value);
 info.appendChild(row);
 return true;
}

function install(){
 addPublisherInfo();
 if(bindReportsKpis())return;
 discoveryObserver=new MutationObserver(()=>{
  addPublisherInfo();
  if(!bindReportsKpis())return;
  discoveryObserver.disconnect();
  discoveryObserver=null;
 });
 discoveryObserver.observe(document.documentElement,{childList:true,subtree:true});
}

install();
global.__SAZMANHR_ORGANIZATION_OVERRIDES__=Object.freeze({
 version:VERSION,
 publisher:Object.freeze({fa:PUBLISHER_FA,en:PUBLISHER_EN}),
 reports:Object.freeze({hideInspectionKpi:true})
});
})(window);
