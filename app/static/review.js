function render(data){
  currentExtraction=data;
  let table=$('fields');table.replaceChildren();
  for(let [title,cls] of [['字段','th'],['提取结果（可修改）','th'],['来源与核对提示','th source-head']]){let d=document.createElement('div');d.className=cls;d.textContent=title;table.append(d)}
  for(let [key,label] of Object.entries(names)){
    let entry=data.fields[key]||{};
    let name=document.createElement('div');name.className='name';name.textContent=label;
    let value=document.createElement('div');let input=document.createElement('input');input.dataset.key=key;input.value=entry.value||'';input.placeholder='未找到，可手动填写';value.append(input);
    let source=document.createElement('div');source.className='source';let note=document.createElement('small');note.textContent=[entry.source_label,entry.source,entry.evidence].filter(Boolean).join(' · ')||'原件未找到，保持空白';source.append(note);
    if(entry.conflict||entry.review_reason){let flag=document.createElement('div');flag.className='flag';flag.textContent=entry.review_reason||'两份单据存在不同值，请核对';source.append(flag)}
    if(data.mode==='ai'&&entry.source_label&&entry.value){let choice=document.createElement('label');choice.className='alias-choice';let checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.aliasField=key;checkbox.checked=true;choice.append(checkbox,document.createTextNode('记住标签：'+entry.source_label));source.append(choice)}
    table.append(name,value,source)
  }
  for(let [key,label] of Object.entries(manualFields)){
    let name=document.createElement('div');name.className='name';name.textContent=label;
    let value=document.createElement('div');let control;
    if(staffNames[key]){
      control=document.createElement('select');
      let blank=document.createElement('option');blank.value='';blank.textContent='请选择'+label;control.append(blank);
      for(const person of staffNames[key]){let option=document.createElement('option');option.value=person;option.textContent=person;control.append(option)}
    }else{control=document.createElement('input');control.placeholder='请根据邮件或聊天填写'}
    control.dataset.key=key;value.append(control);
    let source=document.createElement('div');source.className='source';let note=document.createElement('small');note.textContent=staffNames[key]?'从内部通讯录英文名中选择；本次不自动识别':'人工填写，不自动识别';source.append(note);
    table.append(name,value,source)
  }
  $('review').hidden=false;$('review').scrollIntoView({behavior:'smooth'});
}
