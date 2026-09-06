(function(global){
'use strict';
function create({api,portableApi,state}){
  if(!api||!portableApi||!state)throw new Error('application-services requires api, portableApi and state');
  const transport=()=>state.portable?portableApi:api;
  return Object.freeze({
    setupStatus(){return transport().get('/setup/status')},
    createOwner(payload){return transport().post('/setup/owner',payload)},
    login(payload){return transport().post('/login',payload)},
    logout(){return transport().post('/logout',{})},
    bootstrap(){return transport().get('/bootstrap')},
    privateDataset(name){
      if(!/^[a-z0-9-]+$/.test(String(name||'')))throw new Error('invalid private dataset name');
      return transport().get('/private-data/'+name)
    },
    changePassword(currentPassword,password){return transport().post('/change-password',{current_password:currentPassword,password})},
    history(){return transport().get('/history')},
    addHistory(item){return transport().post('/history/add',item)},
    users(){return transport().get('/users')},
    createUser(payload){return transport().post('/users/create',payload)},
    updateUser(payload){return transport().post('/users/update',payload)},
    toggleUser(payload){return transport().post('/users/toggle',payload)},
    resetUserPassword(payload){return transport().post('/users/reset-password',payload)},
    saveData(payload){return transport().post('/data/save',payload)},
    health(){return transport().get('/health')}
  });
}
global.SazmanHRApplicationServices=Object.freeze({version:'4.9.0',create});
})(window);
