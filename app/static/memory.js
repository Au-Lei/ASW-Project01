// Display only approved labels and fixed-format options; never render shipment values.
async function loadMemory(){
  try{
    const response=await networkFetch('/api/memory');
    if(!response.ok)throw Error('无法读取纠错记忆');
    renderMemory(await response.json());
    message('memory-message','');
  }catch(error){message('memory-message',error.message,true)}
}
function renderMemory(data){
  const list=$('memory-list');list.replaceChildren();list.hidden=false;
  let count=0;
  for(const [field,labels] of Object.entries(data.aliases||{})){
    for(const label of labels){
      count++;
      const row=document.createElement('div');row.className='memory-row';
      const text=document.createElement('span');text.textContent=`${(typeof names==='object'&&names[field])||field} ← ${label}`;
      const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='撤销';
      remove.setAttribute('aria-label',`撤销 ${label} 到 ${(typeof names==='object'&&names[field])||field} 的映射`);
      remove.addEventListener('click',async()=>{
        try{renderMemory(await (await api('/api/memory',{action:'remove_alias',field,source_label:label})).json());message('memory-message','标签映射已撤销')}
        catch(error){message('memory-message',error.message,true)}
      });
      row.append(text,remove);list.append(row);
    }
  }
  for(const rule of data.formats||[]){
    count++;
    const row=document.createElement('div');row.className='memory-row';
    const text=document.createElement('span');text.textContent=`箱型格式：${rule.source} → ${rule.target}`;
    const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='撤销';
    remove.addEventListener('click',async()=>{
      try{renderMemory(await (await api('/api/memory',{action:'remove_format',source:rule.source})).json());message('memory-message','格式规则已撤销')}
      catch(error){message('memory-message',error.message,true)}
    });
    row.append(text,remove);list.append(row);
  }
  if(!count){const empty=document.createElement('p');empty.textContent='尚无已确认记忆';list.append(empty)}
  const picker=$('format-option');const selected=picker.value;picker.replaceChildren();
  for(const option of data.format_options||[]){
    const item=document.createElement('option');item.value=option.source;item.textContent=`${option.source} → ${option.target}`;picker.append(item)
  }
  if([...picker.options].some(option=>option.value===selected))picker.value=selected;
}
$('load-memory').addEventListener('click',loadMemory);
$('add-format').addEventListener('click',async()=>{
  try{renderMemory(await (await api('/api/memory',{action:'add_format',source:$('format-option').value})).json());message('memory-message','格式规则已批准；之后的提取会使用该写法')}
  catch(error){message('memory-message',error.message,true)}
});
