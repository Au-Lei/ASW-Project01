// Retry only safe GET requests; never automatically resubmit a shipment.
async function networkFetch(path,options={}){
  const attempts=(!options.method||options.method==='GET')?3:1;
  for(let attempt=1;attempt<=attempts;attempt++){
    try{return await fetch(path,options)}
    catch(error){
      if(attempt===attempts)throw Error('无法连接本机服务，请确认程序仍在运行；刷新页面或重新启动后再试。');
      await new Promise(resolve=>setTimeout(resolve,attempt*400));
    }
  }
}
async function api(path,payload){
  const response=await networkFetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!response.ok){
    const body=await response.json().catch(()=>({error:'请求失败'}));
    throw Error(body.error||'请求失败');
  }
  return response;
}
