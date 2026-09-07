(function(global){
'use strict';
const VERSION='1.0.0-rc.3';
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

function install(){
 if(bindReportsKpis())return;
 discoveryObserver=new MutationObserver(()=>{
  if(!bindReportsKpis())return;
  discoveryObserver.disconnect();
  discoveryObserver=null;
 });
 discoveryObserver.observe(document.documentElement,{childList:true,subtree:true});
}

install();
global.__SAZMANHR_ORGANIZATION_OVERRIDES__=Object.freeze({
 version:VERSION,
 reports:Object.freeze({hideInspectionKpi:true})
});
})(window);
