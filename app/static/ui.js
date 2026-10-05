const $=id=>document.getElementById(id);
async function fileData(file){return new Promise((resolve,reject)=>{let r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(Error('无法读取所选文件，请确认文件仍存在且有读取权限。'));r.readAsDataURL(file)})}
function message(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('error',error)}
