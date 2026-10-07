window.aswCsrf='';
async function checkSession(){
  const data=await (await networkFetch('/api/session',{cache:'no-store'})).json();
  window.aswCsrf=data.csrf||'';
  document.getElementById('login-panel').hidden=!!data.authenticated||!!data.setup_required;
  document.getElementById('setup-panel').hidden=!data.setup_required;
  document.querySelector('main').hidden=!data.authenticated;
  document.querySelector('header').hidden=!data.authenticated;
  document.querySelector('.account-bar').hidden=!data.authenticated;
  document.getElementById('account-name').textContent=data.username||'';
  return data.authenticated;
}
document.getElementById('setup-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try{
    await api('/api/setup',{username:document.getElementById('setup-username').value,
      password:document.getElementById('setup-password').value});
    document.getElementById('setup-password').value='';
    await checkSession();
  }catch(error){document.getElementById('setup-error').textContent=error.message}
});
document.getElementById('login-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const username=document.getElementById('login-username').value;
  const password=document.getElementById('login-password').value;
  try{
    const response=await api('/api/login',{username,password});
    const data=await response.json();window.aswCsrf=data.csrf;
    document.getElementById('login-password').value='';
    document.getElementById('login-error').textContent='';
    await checkSession();await initialize();
  }catch(error){document.getElementById('login-error').textContent=error.message}
});
document.getElementById('logout').onclick=async()=>{await api('/api/logout',{});window.aswCsrf='';location.reload()};
