let names={},manualFields={},staffNames={},reviewReady=false;
const stages=['read','prepare','extract','normalize','complete'];
let progressTimer=null,progressStartedAt=0;
function formatSeconds(ms){return `${(ms/1000).toFixed(1)}s`}
function resetProgress(){
  $('progress').hidden=false;progressStartedAt=performance.now();
  $('progress-time').textContent='0.0s';$('progress-detail').textContent='正在提交文件…';
  $('progress-log').replaceChildren();
  document.querySelectorAll('#progress-steps li').forEach(li=>li.className='');
  $('progress-fill').style.width='0%';
  clearInterval(progressTimer);
  progressTimer=setInterval(()=>$('progress-time').textContent=formatSeconds(performance.now()-progressStartedAt),100);
}
function updateProgress(job){
  const index=stages.indexOf(job.stage);
  document.querySelectorAll('#progress-steps li').forEach((li,i)=>{
    li.className=i<index?'done':i===index?(job.status==='failed'?'failed':'active'):'';
    if(job.status==='completed')li.className='done';
  });
  $('progress-fill').style.width=job.status==='completed'?'100%':`${Math.max(8,(index+1)*18)}%`;
  $('progress-detail').textContent=job.status==='failed'?`处理失败：${job.error||'未知错误'}`:job.detail;
  const log=$('progress-log');log.replaceChildren();
  for(const event of job.events||[]){let line=document.createElement('div');let time=document.createElement('time');time.textContent=`+${formatSeconds(event.elapsed_ms)}`;line.append(time,document.createTextNode(event.detail));log.append(line)}
  log.scrollTop=log.scrollHeight;
  if(job.status!=='running'){$('progress-time').textContent=formatSeconds(job.elapsed_ms);clearInterval(progressTimer);progressTimer=null}
}
async function loadStats(){
  try{
    const stats=await (await networkFetch('/api/stats',{cache:'no-store'})).json();
    $('stat-total').textContent=stats.total;
    $('stat-outcomes').textContent=`${stats.completed} / ${stats.failed}`;
    $('stat-average').textContent=formatSeconds(stats.average_ms);
    $('stat-fields').textContent=`${stats.field_rate}%`;
  }catch{ /* 页面仍可提取；下次完成任务后重试刷新统计 */ }
}
async function waitForJob(jobId){
  for(;;){
    const response=await networkFetch(`/api/extract/status?job_id=${encodeURIComponent(jobId)}`,{cache:'no-store'});
    const job=await response.json();
    if(!response.ok)throw Error(job.error||'无法读取提取进度');
    updateProgress(job);
    if(job.status==='completed')return job.result;
    if(job.status==='failed')throw Error(job.error||'提取失败');
    await new Promise(resolve=>setTimeout(resolve,350));
  }
}
let selectionVersion=0,extracting=false,currentExtraction=null;
let settingsDirty=false,aiReady=false;
function updateMode(){const selected=$('ai-mode').checked;$('ai-settings').hidden=!selected;$('mode-pill').hidden=!selected}
document.querySelectorAll('input[name="mode"]').forEach(input=>input.addEventListener('change',updateMode));
function applyConfig(config){
  if(config.base_url)$('ai-base-url').value=config.base_url;
  if(config.model)$('ai-model').value=config.model;
  settingsDirty=false;aiReady=!!config.ai_available;
  $('mode-pill').textContent=aiReady?`${config.model} 已通过连接测试`:'未连接，请填写设置并测试';
  if(!config.template_ready)message('upload-message','缺少 Excel 模板，请检查 assets 目录',true);
}
for(const id of ['ai-base-url','ai-key','ai-model'])$(id).addEventListener('input',()=>{settingsDirty=true;$('mode-pill').textContent='设置已修改，需重新测试连接'});
$('save-ai').onclick=async()=>{
  const base_url=$('ai-base-url').value.trim(),model=$('ai-model').value.trim(),api_key=$('ai-key').value.trim();
  if(!base_url||!model||!api_key){message('config-message','请填写 base_url、api_key 和 model',true);return}
  $('save-ai').disabled=true;message('config-message','正在连接并测试所填模型，请稍候……');
  try{const config=await (await api('/api/config',{action:'test',base_url,model,api_key})).json();$('ai-key').value='';applyConfig(config);message('config-message','连接测试成功，已保存本次配置。')}
  catch(e){message('config-message',e.message,true)}finally{$('save-ai').disabled=false}
};
$('clear-ai').onclick=async()=>{
  $('clear-ai').disabled=true;
  try{const config=await (await api('/api/config',{action:'clear'})).json();$('ai-key').value='';applyConfig(config);message('config-message','配置已清除，请重新填写并测试。')}
  catch(e){message('config-message',e.message,true)}finally{$('clear-ai').disabled=false}
};
function selectionChanged(){
  selectionVersion++;
  currentExtraction=null;
  $('review').hidden=true;
  if(!extracting)$('progress').hidden=true;
  $('fields').replaceChildren();
  message('export-message','');
  for(let id of ['entrust','notice']){
    let file=$(id).files[0];
    $(id+'-name').textContent=file?file.name:'未选择';
    $(id+'-remove').disabled=!file;
    $(id+'-remove').hidden=!file;
  }
  $('extract').disabled=!reviewReady||extracting||!($('entrust').files.length||$('notice').files.length);
  message('upload-message','文件选择已更新。本次只会处理当前显示的文件。');
}
for(let id of ['entrust','notice']){
  $(id).addEventListener('change',selectionChanged);
  $(id+'-remove').onclick=()=>{$(id).value='';selectionChanged()};
}
$('clear-files').onclick=()=>{$('entrust').value='';$('notice').value='';selectionChanged()};
$('extract').onclick=async()=>{
  if(!reviewReady){message('upload-message','页面配置未加载，请刷新页面后重试',true);return}
  const selected=[['entrust','订舱委托书'],['notice','入货通知']].filter(([id])=>$(id).files[0]);
  if(!selected.length){message('upload-message','请至少选择一份单据',true);return}
  if(selected.some(([id])=>$(id).files[0].size>12*1024*1024)){message('upload-message','每份文件须小于 12 MB',true);return}
  const version=selectionVersion,mode=document.querySelector('input[name="mode"]:checked').value;
  if(mode==='ai'&&(!aiReady||settingsDirty)){message('upload-message','请先填写 AI 设置并通过连接测试',true);$('ai-settings').scrollIntoView({behavior:'smooth'});return}
  extracting=true;$('extract').disabled=true;$('review').hidden=true;
  resetProgress();$('progress').scrollIntoView({behavior:'smooth',block:'nearest'});
  message('upload-message',mode==='ai'?'AI 正在提取，请稍候……':'正在读取文件并提取……');
  try{
    const documents=[];
    for(let [id,role] of selected){let file=$(id).files[0];documents.push({name:file.name,role,data:await fileData(file)})}
    const {job_id}=await (await api('/api/extract/start',{documents,mode})).json();
    const result=await waitForJob(job_id);
    await loadStats();
    if(version===selectionVersion){render(result);message('upload-message',`提取完成：本次处理 ${documents.length} 份文件，耗时 ${$('progress-time').textContent}。请逐项核对。${(result.warnings||[]).join('；')}`)}
    else message('upload-message','提取已完成，但文件选择已更改；旧结果不会覆盖新单据。');
  }catch(e){clearInterval(progressTimer);progressTimer=null;await loadStats();if(version===selectionVersion){message('upload-message',e.message,true);$('progress-detail').textContent=`处理失败：${e.message}`}}
  finally{extracting=false;$('extract').disabled=!reviewReady||!($('entrust').files.length||$('notice').files.length)}
};
$('export').onclick=async()=>{
  let values={};document.querySelectorAll('#fields [data-key]').forEach(input=>values[input.dataset.key]=input.value);
  let confirmed_aliases=[];
  if(currentExtraction?.mode==='ai')document.querySelectorAll('#fields input[data-alias-field]:checked').forEach(input=>{let field=input.dataset.aliasField;confirmed_aliases.push({field,source_label:currentExtraction.fields[field].source_label})});
  $('export').disabled=true;message('export-message','正在生成 Excel……');
  try{
    let response=await api('/api/export',{values,confirmed_aliases});let blob=await response.blob();let url=URL.createObjectURL(blob);
    let a=document.createElement('a');a.href=url;a.download=`业务联系单_${values.bl_number||'待确认'}.xlsx`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    const unresolved=reviewIssues(currentExtraction.fields,values,reviewVerified).length;
    let notice=response.headers.get('X-Alias-Memory-Warning')?'Excel 已下载，但字段别名保存失败。':'已下载，请打开核对版式。';
    if(unresolved)notice+=`另有 ${unresolved} 项待补充或核实，请转交前确认。`;
    message('export-message',notice);
  }catch(e){message('export-message',e.message,true)}finally{$('export').disabled=false}
};
async function initialize(){
  try{
    const config=await (await networkFetch('/api/review-config')).json();
    names=config.fields;manualFields=config.manual_fields;staffNames=config.staff_names;
    reviewReady=true;selectionChanged();
    applyConfig(await (await networkFetch('/api/config')).json());
    await loadStats();
  }catch(error){message('upload-message',error.message,true)}
}
selectionChanged();
updateMode();
initialize();
