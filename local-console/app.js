'use strict';
const $ = id => document.getElementById(id);
let settings, documentState, results, reviewState, reviewPreview, transaction, busy = false;
const choices = new Map();
const messages = {policy_blocked:'来源未在当前有效策略允许范围内',body_policy_blocked:'仅允许元数据发现，尚未获准获取正文',trusted_egress_required:'尚未配置受信任的网络出口',robots_blocked:'robots 规则不允许访问',robots_unavailable:'无法确认 robots 规则',operation_timeout:'已超过本次处理时间预算',input_too_large:'材料过大：原始文件 ≤512 KB，正文 ≤40,000 字符',empty_input:'未能解析出正文，请粘贴纯文本',missing_server_api_key:'服务端尚未配置 API 密钥',invalid_input:'请输入无凭据的 HTTPS 来源链接与有效材料',install_optional_openai_dependency:'服务端尚未安装可选 OpenAI 依赖',provider_failed:'提供方调用失败；未产生候选，请检查配置或稍后重试',stale_or_missing_document:'原文已变更或清空，请重新预览',operation_in_progress:'另一个操作尚未完成，请等待'};
function status(text) { $('status').textContent = text; }
function updateButtons() {
  for (const id of ['fetch','import','demo','reset','export']) $(id).disabled = busy || !settings;
  for (const id of ['reviewPreview','exportPreview']) $(id).disabled = busy || !results;
  $('commit').disabled = busy || !reviewPreview || !$('confirmCommit').checked;
  $('rollback').disabled = busy || !transaction || transaction.status !== 'applied' || !$('confirmRollback').checked;
  $('extract').disabled = busy || !documentState || !$('reviewed').checked || (!documentState.demo && (!$('consent').checked || !settings?.provider_ready));
}
async function request(path, data) {
  const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':settings.csrf_token},body:JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) { const error = new Error((messages[value.error] || '操作未完成') + ' ['+value.error+']'); error.fallback = value.fallback; throw error; }
  return value;
}
function clearView() { documentState = null; results = null; choices.clear(); reviewPreview=null; transaction=null; $('commitSection').hidden=true; $('transactionSection').hidden=true; $('workspaceMode').textContent='本地工作副本 · 原始 323 题基线只读'; $('previewSection').hidden = true; $('resultsSection').hidden = true; $('preview').textContent = ''; $('candidates').replaceChildren(); $('provenance').replaceChildren(); $('reviewed').checked = false; $('consent').checked = false; }
async function operate(action) {
  if (busy) return;
  busy = true; updateButtons(); status('正在本地处理，请稍候…');
  try { await action(); } catch (error) { status(error.message); $('status').scrollIntoView({behavior:'smooth',block:'center'}); if (error.fallback) { $('blocked').textContent = '获取受阻：'+error.message+'。请使用下方粘贴正文 / 导入 HTML，不会尝试绕过访问限制。'; $('blocked').hidden = false; $('fallback').open = true; } }
  finally { busy = false; updateButtons(); }
}
function showDocument(doc) {
  documentState = doc;
  $('previewSection').hidden = false; $('demoNotice').hidden = !doc.demo; $('consentLabel').hidden = doc.demo;
  $('preview').textContent = doc.text;
  const fields = {'来源链接':doc.source_url,'来源方式':doc.input_kind,'解析器':doc.used_parser || 'plain_text / HTML fallback','解析器版本':doc.parser_version || '内置','解析回退原因':doc.parser_fallback_reason || '无','来源核验状态':doc.access_status || '未核验','正文 SHA-256':doc.text_sha256};
  for (const [name,value] of Object.entries(fields)) { const dt=document.createElement('dt'), dd=document.createElement('dd'); dt.textContent=name; dd.textContent=value; $('provenance').append(dt,dd); }
  $('extract').textContent = doc.demo ? '运行演示提取（不调用 API）' : '确认并提取候选题';
  status('正文已准备，请先审核第 02 步。'); $('previewSection').scrollIntoView({behavior:'smooth',block:'start'});
}
$('fetch').onclick = () => operate(async () => { clearView(); $('blocked').hidden=true; showDocument(await request('/api/fetch',{url:$('url').value})); });
$('import').onclick = () => operate(async () => { clearView(); $('blocked').hidden=true; showDocument(await request('/api/import',{url:$('url').value,text:$('source').value,kind:$('kind').value})); });
$('demo').onclick = () => operate(async () => { clearView(); $('blocked').hidden=true; showDocument(await request('/api/demo',{})); });
$('file').onchange = async () => { const file=$('file').files[0]; if (!file) return; if (file.size>512000) { status(messages.input_too_large); $('file').value=''; return; } $('source').value=await file.text(); $('kind').value=/\.html?$/i.test(file.name)?'html':'text'; status('文件已在本地读取；点击“解析并预览”继续。'); };
$('reviewed').onchange = updateButtons; $('consent').onchange = updateButtons;
$('extract').onclick = () => operate(async () => {
  invalidatePreview(); transaction=null; $('transactionSection').hidden=true; choices.clear();
  results=null; $('resultsSection').hidden=true; $('candidates').replaceChildren();
  const doc=documentState;
  results=await request('/api/extract',{document_id:doc.document_id,mode:doc.demo?'demo':'provider',confirm_transfer:!doc.demo && $('consent').checked});
  $('consent').checked=false;
  $('summary').textContent=`${results.question_candidates.length} 道待审核候选；自动排除 ${results.excluded.length} 条（个人项目细节 / 非通用项）。${results.demo?' 演示 / 人工测试模拟。':''}`;
  reviewState=await request('/api/review/state',{document_id:doc.document_id});
  renderCandidates();
  $('resultsSection').hidden=false; status('候选已生成，尚未批准或发布。'); $('resultsSection').scrollIntoView({behavior:'smooth',block:'start'});
});
$('export').onclick = () => operate(async () => {
  const excluded_ids=Array.from(choices).filter(([id,value])=>value.action==='exclude').map(([id])=>id);
  const value=await request('/api/export',{document_id:documentState.document_id,excluded_ids});
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}));
  const anchor=document.createElement('a'); anchor.href=url; anchor.download=value.demo?'algowen-DEMO-review-pending.json':'algowen-review-pending.json'; anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  status(`已生成 ${value.question_candidates.length} 道候选的私有下载；仍待审核，未发布。`);
});
$('reset').onclick = () => operate(async () => { await request('/api/reset',{}); clearView(); $('url').value=''; $('source').value=''; $('file').value=''; $('blocked').hidden=true; status('本次会话材料与候选已清空；本地工作副本、审核记录及已下载文件保留。'); });
fetch('/api/settings').then(response=>{ if(!response.ok)throw new Error(); return response.json(); }).then(value=>{ settings=value; $('settings').textContent=`提供方：${value.provider} · 模型：${value.model} · 服务端密钥：${value.key_configured?'已配置':'未配置'} · ${value.provider_ready?'本地配置就绪（尚未验证在线权限；仍需逐次确认）':'当前可用演示；真实提取需完成服务端配置'} · OpenAI SDK：${value.openai_sdk_available?'已检测到':'未安装'} · Node.js 校验器：${value.node_available?'已检测到':'缺失，审核入库不可用'} · HTML 解析：${value.parser_available?'可选解析器已检测到':'内置安全回退'}`; updateButtons(); }).catch(()=>{status('无法连接本地服务，请用启动信息中的 127.0.0.1 地址访问。');});
updateButtons();

function node(tag,text,className) { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(className)el.className=className; return el; }
function invalidatePreview() { reviewPreview=null; $('commitSection').hidden=true; $('confirmCommit').checked=false; updateButtons(); }
function renderCandidates() {
  choices.clear();
  $('workspaceMode').textContent=results.demo?'隔离演示沙盒 · 虚构材料 · 不写入真实工作副本 / 原始 323 题':'本地工作副本 · 原始 323 题基线只读 · 不公开发布';
  for (const row of results.question_candidates) {
    const choice={candidate_id:row.id,action:'pending',source_reviewed:false,common_question:false,target_question_id:'',reason:''}; choices.set(row.id,choice);
    const card=node('article'), title=node('h3',row.question), select=node('select');
    select.setAttribute('aria-label',row.question+'：审核决定');
    for(const [value,label] of [['pending','待定（默认，不批准）'],['add','新增题卡'],['merge','合并到已有题'],['exclude','排除']]) { const opt=node('option',label); opt.value=value; select.append(opt); }
    card.append(title,node('p','模型建议仅供参考：'+row.proposed_action+'；最终由你逐题决定。','hint'),select);
    const merge=node('div'); merge.hidden=true;
    const search=node('input');search.type='search';search.placeholder='搜索已有题标题或编号';search.setAttribute('aria-label','搜索合并目标');
    const targets=node('select');targets.setAttribute('aria-label','选择合并目标');
    const targetPreview=node('p','','hint');
    function populate(){targets.replaceChildren();const blank=node('option','请选择目标（不自动选择）');blank.value='';targets.append(blank);const query=search.value.toLowerCase(); for(const q of reviewState.questions.filter(q=>(q.id+' '+q.title).toLowerCase().includes(query))){const option=node('option',q.id+' · '+q.title);option.value=q.id;targets.append(option);}targets.value=choice.target_question_id;}
    search.oninput=populate; targets.onchange=()=>{choice.target_question_id=targets.value;const q=reviewState.questions.find(q=>q.id===targets.value);targetPreview.textContent=q?'合并目标：'+q.id+' · '+q.title:'尚未选择';invalidatePreview();};populate();merge.append(search,targets,targetPreview);card.append(merge);
    const commonLabel=node('label',undefined,'check'), common=node('input');common.type='checkbox';commonLabel.append(common,node('span','我确认这是通用算法 / 技术问题，且已核对证据与合并语义。'));commonLabel.hidden=true;common.onchange=()=>{choice.common_question=common.checked;invalidatePreview();};card.append(commonLabel);
    const sourceLabel=node('label',undefined,'check'),sourceCheck=node('input');sourceCheck.type='checkbox';sourceLabel.append(sourceCheck,node('span','我已核对来源与证据；不代表独立真实性验证。'));sourceLabel.hidden=true;sourceCheck.onchange=()=>{choice.source_reviewed=sourceCheck.checked;invalidatePreview();};card.append(sourceLabel);
    const reason=node('input');reason.type='text';reason.placeholder='排除理由（必填）';reason.setAttribute('aria-label','排除理由');reason.hidden=true;reason.oninput=()=>{choice.reason=reason.value;invalidatePreview();};card.append(reason);
    select.onchange=()=>{choice.action=select.value;merge.hidden=choice.action!=='merge';commonLabel.hidden=!['add','merge'].includes(choice.action);reason.hidden=choice.action!=='exclude';sourceLabel.hidden=!['add','merge'].includes(choice.action);invalidatePreview();};
    const evidenceBox=node('details');evidenceBox.open=true;evidenceBox.append(node('summary','来源证据（请逐项核对）'));
    for (const evidence of row.evidence) { evidenceBox.append(node('blockquote',evidence.quote),node('p',`${evidence.url} · ${evidence.locator}`,'hint')); }
    card.append(evidenceBox); $('candidates').append(card);
  }
}
$('reviewer').oninput=invalidatePreview;
$('reviewPreview').onclick=()=>operate(async()=>{
  const decisions=[];
  if(!$('reviewer').value.trim())throw new Error('请填写审核人。');
  for(const c of choices.values()) {
    if(c.action==='pending')throw new Error('仍有待定候选：请逐题选择新增、合并或排除。');
    if(c.action!=='exclude'&&!c.common_question)throw new Error('请逐题确认通用性与来源证据。');
    if(c.action!=='exclude'&&!c.source_reviewed)throw new Error('请逐题确认已核对来源与证据。');
    if(c.action==='merge'&&!c.target_question_id)throw new Error('请搜索并选择已有合并目标。');
    if(c.action==='exclude'&&!c.reason.trim())throw new Error('请填写排除理由。');
    const d={candidate_id:c.candidate_id,action:c.action};
    if(c.action==='exclude')d.reason=c.reason;else {d.common_question=true;d.source_reviewed=true;}
    if(c.action==='merge')d.target_question_id=c.target_question_id;
    decisions.push(d);
  }
  reviewPreview=await request('/api/review/preview',{document_id:documentState.document_id,decisions:{schema_version:1,reviewer:$('reviewer').value.trim(),decisions}});
  const c=reviewPreview.counts;
  $('diffSummary').textContent=`${results.demo?'演示沙盒':'本地工作副本'}：新增题卡 ${c.new_questions} · 新增登记来源 ${c.new_sources} · 新增题目–来源组 ${c.new_question_source_pairs} · 新增证据 ${c.evidence_added} · 排除 ${c.excluded}。题卡数、证据数、独立来源组不是同一计数。`;
  const totals=reviewPreview.totals;
  if(totals) {
    const before=totals.before,after=totals.after;
    $('diffSummary').append(node('p',`基线 → 结果：题卡 ${before.question_count} → ${after.question_count}；登记来源 ${before.source_count} → ${after.source_count}；独立题目–来源组 ${before.question_source_pairs} → ${after.question_source_pairs}。`));
    $('diffSummary').append(node('p',`记录条数 ${before.record_count} → ${after.record_count}；审核证据片段 ${before.review_evidence_count} → ${after.review_evidence_count}。审核证据只统计显式附加的片段，不把旧记录条数当成证据片段数。`,'hint'));
  }
  $('diffItems').replaceChildren();
  for(const change of reviewPreview.changes){const row=results.question_candidates.find(r=>r.id===change.candidate_id);const article=node('article');article.append(node('strong',row?.question||change.candidate_id),node('p',`${({add:'新增',merge:'合并',exclude:'排除'})[change.action]} → ${change.question_id||'不入库'} · 来源组新增 ${change.pair_added||0} · 证据新增 ${change.evidence_added||0}`));$('diffItems').append(article);}
  $('diffJson').textContent=JSON.stringify(reviewPreview,null,2);$('confirmCommit').checked=false;$('commitSection').hidden=false;status('预览已生成，尚未写入。更改决定后必须重新预览。');$('commitSection').scrollIntoView({behavior:'smooth'});
});
$('confirmCommit').onchange=updateButtons;$('confirmRollback').onchange=updateButtons;
$('commit').onclick=()=>operate(async()=>{
  if(!$('confirmCommit').checked||!reviewPreview)return;
  transaction=await request('/api/review/apply',{document_id:documentState.document_id,preview_id:reviewPreview.preview_id,confirmed:true});
  reviewPreview=null;$('confirmCommit').checked=false;$('commitSection').hidden=true;
  showTransaction();status((transaction.replayed?'此事务已提交，本次为安全重放，未重复入库。':'已写入')+(results.demo?'隔离演示沙盒':'本地工作副本')+'，原始基线未变，未公开发布。');
});
function showTransaction(){$('transactionSection').hidden=false;$('transactionInfo').textContent=`${results.demo?'隔离演示沙盒':'本地工作副本'} · 事务 ${transaction.transaction_id} · ${transaction.status==='applied'?'已写入（未发布）':'已回滚'}`;$('transactionJson').textContent=JSON.stringify(transaction,null,2);$('confirmRollback').checked=false;}
$('rollback').onclick=()=>operate(async()=>{
  if(!$('confirmRollback').checked||!transaction)return;
  transaction=await request('/api/review/rollback',{document_id:documentState.document_id,transaction_id:transaction.transaction_id,confirmed:true});showTransaction();status('最后一次入库已回滚；原始基线未变。');
});
$('exportPreview').onclick=()=>{if(!reviewPreview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(reviewPreview,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='algowen-local-preview-NOT-PUBLISHED.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('已导出入库预览，不是公开发布产物。');};
Object.assign(messages,{schema_validator_unavailable:'本地数据校验器不可用：请确认 Node.js 已安装且位于服务端 PATH；不会绕过校验',explicit_confirmation_required:'必须显式确认后才能写入或回滚',working_copy_changed_since_apply:'当前副本已变化，与提交后哈希不一致；拒绝覆盖或回滚',working_copy_changed_since_rollback:'回滚后副本已变化，请核对本地文件',preview_already_rolled_back:'此预览已回滚，不能再次提交；请重新生成预览',missing_decisions:'仍有待定候选，请逐题决定',confirmation_required:'必须显式确认后才能写入或回滚',baseline_changed:'工作副本已变化，旧预览已失效，请重新预览',stale_preview:'预览已过期，请重新生成',preview_already_applied:'此预览已提交，禁止重复写入',rollback_conflict:'当前文件与事务哈希不符，已拒绝覆盖，请保留现场核对',not_latest_transaction:'只能回滚最后一次有效事务'});
