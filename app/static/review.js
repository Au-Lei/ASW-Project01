let reviewVerified=new Set(),reviewInputs=new Map(),reviewConfirmButtons=new Map();
function reviewIssues(fields,values,verified=new Set()){
  let issues=[];
  for(const [key,entry] of Object.entries(fields)){
    const value=String(values[key]??entry.value??'').trim();
    if(!value)issues.push({key,type:'missing'});
    else if(!verified.has(key)&&entry.conflict)issues.push({key,type:'conflict'});
    else if(!verified.has(key)&&entry.review_reason)issues.push({key,type:'review'});
  }
  return issues
}
function updateReviewSummary(){
  for(const [key,button] of reviewConfirmButtons){let done=reviewVerified.has(key);button.textContent=done?'已核对 ✓':'标记已核对';button.setAttribute('aria-pressed',String(done))}
  const values={};for(const [key,input] of reviewInputs)values[key]=input.value;
  const issues=reviewIssues(currentExtraction.fields,values,reviewVerified);
  const counts={missing:0,conflict:0,review:0};for(const issue of issues)counts[issue.type]++;
  const summary=$('review-summary');summary.replaceChildren();
  let title=document.createElement('strong');title.textContent=issues.length
    ?`自动提取字段优先处理 ${issues.length} 项：待补充 ${counts.missing} · 来源冲突 ${counts.conflict} · 需核实 ${counts.review}`
    :'8 项自动提取字段已补齐或已标记核对；人工字段另填，下载前仍请对照原件。';summary.append(title);
  if(issues.length){
    let list=document.createElement('div');list.className='review-issue-list';
    const labels={missing:'待补充',conflict:'来源冲突',review:'需核实'};
    for(const issue of issues){
      let button=document.createElement('button');button.type='button';button.className=`review-issue ${issue.type}`;
      button.textContent=`${names[issue.key]||issue.key} · ${labels[issue.type]}`;
      button.addEventListener('click',()=>{let input=reviewInputs.get(issue.key);input.scrollIntoView({behavior:'smooth',block:'center'});input.focus({preventScroll:true})});
      list.append(button)
    }
    summary.append(list)
  }
}
function render(data){
  currentExtraction=data;
  reviewVerified=new Set();reviewInputs=new Map();reviewConfirmButtons=new Map();
  let warnings=$('review-warnings');warnings.replaceChildren();
  for(const warning of data.warnings||[]){let line=document.createElement('p');line.textContent=warning;warnings.append(line)}
  warnings.hidden=!warnings.childElementCount;
  let table=$('fields');table.replaceChildren();
  for(let [title,cls] of [['字段','th'],['提取结果（可修改）','th'],['来源与核对提示','th source-head']]){let d=document.createElement('div');d.className=cls;d.textContent=title;table.append(d)}
  for(let [key,label] of Object.entries(names)){
    let entry=data.fields[key]||{};
    let name=document.createElement('div');name.className='name';name.textContent=label;
    let value=document.createElement('div');let input=document.createElement('input');input.dataset.key=key;input.value=entry.value||'';input.placeholder='未找到，可手动填写';value.append(input);
    reviewInputs.set(key,input);input.addEventListener('input',()=>{reviewVerified.delete(key);updateReviewSummary()});
    let source=document.createElement('div');source.className='source';let note=document.createElement('small');note.textContent=[entry.source_label,entry.source,entry.evidence].filter(Boolean).join(' · ')||'原件未找到，保持空白';source.append(note);
    if(entry.conflict||entry.review_reason){let flag=document.createElement('div');flag.className='flag';flag.textContent=entry.review_reason||'两份单据存在不同值，请核对';source.append(flag)}
    if(entry.conflict&&Array.isArray(entry.candidates)){
      for(const candidate of entry.candidates){
        if(!candidate.value||candidate.value===entry.value)continue;
        let button=document.createElement('button');button.type='button';button.className='candidate-choice';button.textContent=`改用 ${candidate.value}`;
        button.title=[candidate.role,candidate.source,candidate.evidence].filter(Boolean).join(' · ');
        button.addEventListener('click',()=>{input.value=candidate.value;reviewVerified.delete(key);note.textContent=button.title;let flag=source.querySelector('.flag');if(flag)flag.textContent='已改用另一份单据的候选值，请核对原件';updateReviewSummary()});
        source.append(button)
      }
    }
    if(entry.conflict||entry.review_reason){
      let checked=document.createElement('button');checked.type='button';checked.className='review-confirm';checked.textContent='标记已核对';checked.setAttribute('aria-pressed','false');
      checked.addEventListener('click',()=>{if(reviewVerified.has(key))reviewVerified.delete(key);else reviewVerified.add(key);updateReviewSummary()});
      reviewConfirmButtons.set(key,checked);source.append(checked)
    }
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
  updateReviewSummary();$('review').hidden=false;$('review').scrollIntoView({behavior:'smooth'});
}
