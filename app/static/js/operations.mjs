import {apiRequest} from './auth.mjs';
import {money,date,escape as e,productById,documentTypes} from './domain.mjs';
import {currentUser,ownApplications,ownDocuments} from './store.mjs';
import {heading,empty,button,icon,badge,field} from './ui.mjs';

const cache=new Map(), challenges=new Map(),views=new Map();
let generation=0;
export function clearOperations(){generation++;cache.clear();challenges.clear();views.clear();}
export function invalidateOperations(){generation++;cache.clear();}
export const challengeFor=id=>challenges.get(id);
export function setChallenge(id,data){challenges.set(id,data);}
const currency=v=>new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(v))+' ₽';
const requestError=err=>`<p class="form-error" role="alert">${e(err)}</p>${button('Повторить','operations-refresh','secondary')}`;
const titleMap={loans:'Мои кредиты',documents:'Документы',messages:'Сообщения',notifications:'Уведомления',team:'Команда',analytics:'Аналитика',integrations:'Состояние интеграций',settings:'Правила рассмотрения',audit:'Аудит действий',review:'Карточка рассмотрения'};
export function pageData(section,id=''){return cache.get(section+':'+id)?.data;}
export async function loadOperations(section,id=''){
  const key=section+':'+id,old=cache.get(key);
  if(old?.loading||old?.data)return;
  const requestGeneration=generation;
  cache.set(key,{loading:true});
  try{
    let data;
    if(section==='loans')data=await apiRequest('/api/loans'+(id?'/'+encodeURIComponent(id):''));
    else if(section==='notifications')data=await apiRequest('/api/notifications');
    else if(section==='team')data=await apiRequest('/api/team');
    else if(section==='analytics')data=await apiRequest('/api/analyst/analytics');
    else if(section==='integrations')data=await Promise.all([apiRequest('/api/admin/integrations'),apiRequest('/api/analyst/operations')]);
    else if(section==='settings')data=await apiRequest('/api/admin/rules');
    else if(section==='audit')data=await apiRequest('/api/admin/audit');
    else if(section==='review')data=await Promise.all([apiRequest(`/api/analyst/applications/${id}`),apiRequest(`/api/applications/${id}/workflow`),apiRequest(`/api/applications/${id}/messages`)]);
    else if(section==='messages'&&id)data=await apiRequest(`/api/applications/${id}/messages`);
    else if(section==='messages')data=await apiRequest(currentUser()?.role==='client'?'/api/applications':'/api/analyst/applications?status=all');
    else data={};
    if(section==='review'&&data[0].version!==data[1].version)throw Error('Заявка изменилась во время загрузки. Обновите рассмотрение.');
    if(requestGeneration===generation)cache.set(key,{data});
  }catch(err){if(requestGeneration===generation)cache.set(key,{error:err.message});}
}

export function operationsPage(section,id=''){
  if(section==='documents')return documentPage();
  const state=cache.get(section+':'+id),head=heading(titleMap[section]||'Кабинет','',button('Обновить','operations-refresh','text'));
  if(state?.error)return head+requestError(state.error);
  if(!state?.data)return head+'<p role="status" class="muted">Загружаем данные…</p>';
  const data=state.data;
  if(section==='loans')return head+(id?loanDetail(data):loanList(data));
  if(section==='notifications')return head+notificationList(data);
  if(section==='team')return head+teamPage(data);
  if(section==='analytics')return head+analyticsPage(data);
  if(section==='integrations')return head+integrationPage(data);
  if(section==='settings')return head+settingsPage(data);
  if(section==='audit')return head+`<section class="panel"><div class="table-scroll"><table class="schedule-table"><thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Объект</th><th>Основание</th></tr></thead><tbody>${data.map(r=>`<tr><td>${date(r.created_at)}</td><td>${e(r.actor_id??'Worker')}</td><td>${e(r.action)}</td><td>${e(r.target)}</td><td>${e(JSON.stringify(r.details))}</td></tr>`).join('')}</tbody></table></div></section>`;
  if(section==='review')return reviewPage(data);
  if(section==='messages'&&id)return head+`<a href="#/${currentUser()?.role==='client'?'applications':'review'}/${e(id)}" class="text-link">Открыть заявку ${e(id.slice(0,8))}</a>`+chatPanel(id,data);
  if(section==='messages')return head+(data.length?`<div class="panel">${data.map(a=>`<a class="document-link" href="#/messages/${e(a.id)}"><span>Заявка ${e(a.id.slice(0,8).toUpperCase())}<small>${e(productById(a.productId).name)}</small></span>${badge(a.status)}</a>`).join('')}</div>`:empty('Переписки пока нет','Сообщения появятся после создания заявки.'));
  return head;
}

function loanList(rows){
  if(!rows.length)return empty('Выданных кредитов пока нет','После демонстрационной выдачи здесь появятся условия и график платежей.');
  return `<div class="product-grid">${rows.map(l=>`<a class="panel loan-card" href="#/loans/${e(l.id)}"><span class="badge green">Демо-кредит</span><h2>${e(productById(l.product_id).name)}</h2><strong class="loan-amount">${money(l.amount)}</strong><p>${l.months} мес. · ${e(l.annual_rate)}% годовых</p><small>${e(l.contract_number)}</small><span class="text-link">График платежей ${icon('arrow')}</span></a>`).join('')}</div>`;
}
function loanDetail(l){
  const schedule=l.schedule,interest=schedule.reduce((s,r)=>s+Number(r.interest),0),total=schedule.reduce((s,r)=>s+Number(r.payment),0);
  const view=views.get(l.id)||'table',month=Math.min(schedule.length,Math.max(1,Number(views.get(l.id+':month')||1))),selected=schedule[month-1];
  const graph=`<div class="schedule-chart" aria-label="График основного долга и процентов">${schedule.map((r,i)=>`<button class="schedule-column ${i+1===month?'selected':''}" style="height:${Math.max(3,Number(r.payment)/Math.max(...schedule.map(x=>Number(x.payment)))*100)}%" data-op="schedule-month" data-loan="${e(l.id)}" data-value="${i+1}" aria-label="Платёж ${i+1}: ${e(r.payment)} рублей"><span style="height:${Number(r.interest)/Number(r.payment)*100}%"></span></button>`).join('')}</div><label class="field"><span>Месяц ${month}: ${e(selected.date)} · платёж ${currency(selected.payment)}</span><input type="range" min="1" max="${schedule.length}" value="${month}" data-schedule-range="${e(l.id)}" aria-label="Месяц графика"></label><p>Основной долг ${currency(selected.principal)} · проценты ${currency(selected.interest)} · остаток ${currency(selected.closing)}</p>`;
  const table=`<div class="table-scroll"><table class="schedule-table"><thead><tr><th>Дата</th><th>Остаток</th><th>Проценты</th><th>Основной долг</th><th>Платёж</th><th>После платежа</th></tr></thead><tbody>${schedule.map(r=>`<tr><td>${e(r.date)}</td><td>${currency(r.opening)}</td><td>${currency(r.interest)}</td><td>${currency(r.principal)}</td><td>${currency(r.payment)}</td><td>${currency(r.closing)}</td></tr>`).join('')}</tbody></table></div>`;
  return `<a class="back-link" href="#/loans">${icon('arrow')} Мои кредиты</a><section class="panel"><h2>${e(productById(l.product_id).name)}</h2><p>${e(l.contract_number)}</p><dl class="details"><div><dt>Выдано</dt><dd>${money(l.amount)} · ${date(l.issued_at)}</dd></div><div><dt>Срок и ставка</dt><dd>${l.months} мес. · ${e(l.annual_rate)}%</dd></div><div><dt>Плановое завершение</dt><dd>${e(schedule.at(-1).date)}</dd></div><div><dt>Первый платёж</dt><dd>${currency(schedule[0].payment)}</dd></div><div><dt>Всего процентов</dt><dd>${currency(interest)}</dd></div><div><dt>Всего выплат</dt><dd>${currency(total)}</dd></div></dl><p class="footnote">${l.product_id==='overdraft'?'Проценты ежемесячно, основной долг в конце срока.':'Аннуитетный график с корректировкой последнего платежа.'} Информационный график демонстрационного кредита.</p></section><section class="panel"><div class="section-title"><h2>График платежей</h2><a class="button secondary" href="/api/loans/${e(l.id)}/schedule.csv">Экспорт CSV</a></div><div class="tabs" role="group" aria-label="Вид графика">${[['table','Таблица'],['chart','График']].map(([id,label])=>`<button class="tab ${view===id?'active':''}" data-op="schedule-view" data-loan="${e(l.id)}" data-value="${id}">${label}</button>`).join('')}</div>${view==='chart'?graph:table}</section>`;
}
export function changeSchedule(id,value,month=false){views.set(id+(month?':month':''),value);}
function notificationList(data){return `<div class="section-title"><p>${data.unread} непрочитанных</p><button class="button secondary" data-op="notifications-read-all">Прочитать все</button></div>${data.items.length?`<div class="panel">${data.items.map(n=>`<article class="notification ${n.read?'':'unread'}"><a href="#/${currentUser()?.role==='client'?'applications':'review'}/${e(n.application_id)}">${e(n.text)}<small>${date(n.created_at)}</small></a><div><button class="button text" data-op="notification-read" data-id="${e(n.id)}">Прочитано</button><button class="button text" data-op="notification-archive" data-id="${e(n.id)}">В архив</button></div></article>`).join('')}</div>`:empty('Уведомлений пока нет','Решения, сообщения и запросы банка появятся здесь.')}`;}
function documentPage(){const user=currentUser(),docs=ownDocuments();return heading('Документы','PDF сохраняются на сервере и доступны для новых заявок.')+`<section class="panel">${documentTypes(user.type,'equipment').map(t=>`<div class="document-slot"><h3>${e(t.name)}</h3>${docs.filter(d=>d.type===t.id).map(d=>`<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${e(d.name)} · ${date(d.createdAt)}</button>`).join('')}<label class="upload-label">Загрузить PDF<input class="file-input" type="file" data-upload="${t.id}" accept=".pdf"></label></div>`).join('')}</section>`;}
function teamPage(data){return `<section class="panel"><h2>Пользователи организации</h2>${data.map(u=>`<div class="notification"><span>${e(u.email)}</span><span class="badge neutral">${u.can_sign?'Уполномоченный подписант':'Подготовка заявки'}</span></div>`).join('')}</section>${currentUser().can_sign?`<section class="panel"><h2>Пригласить сотрудника</h2><form id="team-invite-form" class="form-stack">${field('Почта сотрудника','email','',{type:'email',required:true})}<p class="muted">Сотрудник сможет готовить заявки и отвечать банку. Подписание останется у уполномоченного представителя.</p><button type="submit" class="button primary">Создать приглашение</button></form><div id="invite-result" aria-live="polite"></div></section>`:''}`;}
export function joinPage(){return `<main class="auth-main"><div class="panel join-panel"><h1>Присоединиться к организации</h1><form id="team-join-form" class="form-stack">${field('Почта','email','',{type:'email',required:true})}${field('Приглашение','token','',{required:true,attrs:'maxlength="128"'})}${field('Новый пароль','password','',{type:'password',required:true,attrs:'minlength="8" maxlength="128"'})}<button class="button primary" type="submit">Создать аккаунт сотрудника</button><p class="form-error" id="join-error" role="alert"></p></form><a href="#/home" class="back-link">Вернуться ко входу</a></div></main>`;}
function analyticsPage(d){const metrics=[['Всего заявок',d.total],['Новых',d.new],['На проверке',d.checking],['Ручное рассмотрение',d.manual],['На согласовании',d.escalated],['Одобрено / предложение',d.approved],['Отказано',d.rejected],['Нужны сведения',d.needs_info],['Подписано',d.signed],['Выдано',d.disbursed],['Сумма выдач',money(d.disbursed_amount)],['Автоматические решения',(d.auto_decision_share*100).toFixed(1)+'%'],['Медиана до решения',d.median_decision_seconds==null?'—':d.median_decision_seconds.toFixed(1)+' с'],['Средняя обработка',d.mean_processing_seconds==null?'—':d.mean_processing_seconds.toFixed(1)+' с'],['Технические ошибки',d.technical_errors]];const max=Math.max(1,...d.funnel.map(f=>f.count));return `<a class="button secondary" href="/api/analyst/analytics.csv">Экспорт CSV</a><div class="metrics-grid">${metrics.map(([label,value])=>`<article class="panel metric"><span>${label}</span><strong>${e(value)}</strong></article>`).join('')}</div><div class="two-column"><section class="panel"><h2>Воронка</h2>${d.funnel.map(f=>`<div class="funnel-row"><span>${e(f.stage)}</span><div><i style="width:${f.count/max*100}%"></i></div><b>${f.count}</b></div>`).join('')}<p class="footnote">${e(d.definitions)}</p></section><section class="panel"><h2>По продуктам</h2>${Object.entries(d.by_product).map(([id,count])=>`<div class="notification"><span>${e(productById(id).name)}</span><strong>${count}</strong></div>`).join('')}<h3>Ошибки источников за всю историю</h3>${Object.entries(d.integration_error_attempts||{}).map(([source,count])=>`<p>${e(source)}: ${count}</p>`).join('')||'<p>Нет ошибок</p>'}<h3>Очередь обработки</h3>${Object.entries(d.queue).map(([status,count])=>`<p>${e(status)}: ${count}</p>`).join('')}</section></div>`;}
const sourceLabels={egrul:'ЕГРЮЛ / ЕГРИП',fns:'ФНС',bki:'БКИ',financials:'Финансовые сведения',turnover:'Обороты',issuance:'Регистрация демо-выдачи'};
const modes=[['success','Работает'],['unavailable','Недоступен'],['timeout','Таймаут'],['malformed','Некорректный ответ'],['missing','Нет сведений'],['negative','Негативные сведения'],['transient','Временный отказ']];
function integrationPage([sources,worker]){const canEdit=currentUser().role==='admin';return `<section class="panel"><h2>Фоновая обработка</h2><p class="notice ${worker.worker_healthy?'success':''}">${worker.worker_healthy?'Worker работает':'Нет свежего сигнала worker'}</p>${worker.jobs.length?`<div class="table-scroll"><table class="schedule-table"><thead><tr><th>Заявка</th><th>Задача</th><th>Этап</th><th>Попытки</th><th>Причина</th></tr></thead><tbody>${worker.jobs.map(j=>`<tr><td><a href="#/review/${e(j.application_id)}">${e(j.application_id.slice(0,8))}</a></td><td>${e(j.status)}</td><td>${j.stage}</td><td>${j.attempts}</td><td>${e(j.last_error||'—')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">Очередь обработана.</p>'}</section><section class="panel"><h2>Синтетические источники</h2>${sources.map(s=>`<form class="source-form notification" data-source="${e(s.name)}"><label class="field"><span>${e(sourceLabels[s.name])}</span><select name="mode" ${canEdit?'':'disabled'}>${modes.map(([id,label])=>`<option value="${id}" ${s.mode===id?'selected':''}>${label}</option>`).join('')}</select></label><span>Сбоев подряд: ${s.failures}${s.open_until?' · circuit breaker открыт':''}</span>${canEdit?'<button type="submit" class="button secondary">Применить</button>':''}</form>`).join('')}<p class="footnote">Изменения влияют только на демонстрационные адаптеры и сохраняются между перезапусками.</p></section>`;}
function settingsPage(data){const labels={max_debt_burden:'Максимальная долговая нагрузка',min_cash_buffer:'Минимальный финансовый запас, ₽',auto_limit:'Лимит автоматического решения, ₽',underwriter_limit:'Лимит аналитика, ₽',min_business_months:'Минимальный срок работы, мес.',offer_valid_days:'Срок предложения, дней'};return `<section class="panel"><h2>Демонстрационные правила · версия ${data.version}</h2><form id="policy-form" class="form-stack"><div class="form-grid">${Object.entries(data.definition).map(([key,value])=>field(labels[key]||key,key,value,{type:'number',required:true,attrs:`step="${key==='max_debt_burden'?'.01':'1'}" min="0" ${currentUser().role==='admin'?'':'readonly'}`})).join('')}</div>${currentUser().role==='admin'?'<button type="submit" class="button primary">Опубликовать новую версию</button>':''}<p class="footnote">Действующие заявки сохраняют версию правил, с которой началась обработка. Это не политика Альфа-Банка.</p></form></section><section class="panel"><h2>История версий</h2>${data.history.map(v=>`<p>Версия ${v.id} · ${date(v.created_at)}</p>`).join('')}</section>`;}

export function modelPanel(flow){const m=flow?.ml?.at(-1);if(!m)return '';const r=m.result;const top=r.contributions?.[0];return `<section class="panel"><h3>Результат LightGBM</h3>${r.available?`<p class="loan-amount">${Number(r.scores[0]).toFixed(6)}</p><p>Технический score класса 1. Смысл целевой переменной и порог не подтверждены. Это не вероятность одобрения или дефолта.</p><p class="footnote">${m.provenance.synthetic?'Синтетический финансовый профиль':'Предоставленный финансовый профиль'} · период ${e(m.provenance.period||'—')} · модель ${e(m.model_sha256?.slice(0,16))}…</p>${top?`<details><summary>Вклады признаков в raw-score</summary><dl class="details">${Object.entries(top.values).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,8).map(([name,value])=>`<div><dt>${e(name)}</dt><dd>${Number(value).toFixed(4)}</dd></div>`).join('')}</dl><p class="footnote">Сумма вкладов и базового значения сверена с raw-score. Это не вклады в кредитное решение.</p></details>`:''}`:`<p class="muted">Совместимые признаки или веса недоступны. Решение принимается по отдельным демонстрационным правилам.</p>`}</section>`;}
export function tasksPanel(a){const tasks=a.workflow?.tasks||[];if(!tasks.length)return '';return `<section class="panel"><h3>Задачи банка</h3>${tasks.map(t=>`<article class="application-task"><strong>${t.status==='DONE'?'✓ ':''}${e(t.title)}</strong><p>${e(t.description)}</p>${t.due_at?`<small>До ${date(t.due_at)}</small>`:''}${t.status==='OPEN'&&a.status==='needs_info'?`<form class="task-answer-form form-stack" data-application="${e(a.id)}" data-task="${e(t.id)}">${t.kind==='document'?`<label class="upload-label">Прикрепить ${e(t.document_type)} PDF<input class="file-input" type="file" data-upload="${e(t.document_type)}" data-application="${e(a.id)}" accept=".pdf"></label><select name="document_id"><option value="">Выбрать файл из заявки</option>${a.workflow.documents.filter(d=>d.document_type===t.document_type).map(d=>`<option value="${e(d.id)}">${e(d.filename)}</option>`).join('')}</select>`:field('Ответ','answer','',{required:true,attrs:'maxlength="4000"'})}<button type="submit" class="button secondary">Выполнить задачу</button></form>`:`<small>${t.status==='DONE'?'Выполнено':'Ожидает выполнения'}</small>`}</article>`).join('')}</section>`;}
export function chatPanel(id,data){return `<section class="panel"><h3>Переписка с банком ${data?.unread?`· ${data.unread} новых`:''}</h3><div class="bank-chat" role="log">${data?.messages?.map(m=>`<article class="chat-message ${m.author_role==='client'?'client':'bank'}"><small>${m.author_role==='client'?'Представитель компании':'Банк'} · ${date(m.created_at)}</small><p>${e(m.text)}</p></article>`).join('')||'<p class="muted">Сообщений пока нет.</p>'}</div><form class="bank-message-form form-stack" data-application="${e(id)}"><label class="field"><span>Сообщение</span><textarea name="text" required maxlength="4000" rows="2"></textarea></label><div class="section-title"><button type="submit" class="button primary">Отправить</button><button type="button" class="button text" data-op="messages-read" data-id="${e(id)}">Отметить прочитанным</button></div></form></section>`;}
export function clientExtra(a){return modelPanel(a.workflow)+tasksPanel(a)+`<section class="panel"><h3>Связь с банком</h3><a class="button secondary" href="#/messages/${e(a.id)}">Открыть переписку</a></section>`;}
export function reviewPage([a,flow,messages]){const run=flow.assessments.at(-1),isApprover=['admin','approver'].includes(currentUser().role),actions=a.status==='escalated'&&!isApprover?false:['pending','escalated'].includes(a.status);return `${heading('Рассмотрение '+a.id.slice(0,8).toUpperCase(),a.business?.name||'',badge(a.status))}<div class="section-title"><a class="back-link" href="#/current">${icon('arrow')} Очередь</a>${!a.assignedToUserId&&actions?`<button class="button secondary" data-op="assign" data-id="${e(a.id)}">Взять в работу</button>`:''}</div><div class="two-column"><div><section class="panel"><h2>${e(productById(a.productId).name)}</h2><dl class="details">${[['Сумма',money(a.amount)],['Срок',a.months+' мес.'],['Выручка',money(a.revenue)],['Расходы',money(a.expenses)],['Другие платежи',money(a.debtPayment)],['Цель',a.purpose]].map(([key,value])=>`<div><dt>${key}</dt><dd>${e(value)}</dd></div>`).join('')}</dl><h3>Демо-политика и стоп-факторы</h3><p>${e(run?.policy.reasons.join('. ')||'Проверка ещё не завершена')}</p><p>Версия правил ${run?.policy.version||'—'} · баллы риска ${run?.risk.points??'—'}/100</p>${run?.policy.alternative_amount?`<p>Рекомендуемая сумма: ${money(run.policy.alternative_amount)}</p>`:''}<details><summary>Результаты источников</summary>${run?.checks.map(c=>`<p>${e(c.source)}: ${e(c.status)} · ${date(c.received_at)}</p>`).join('')||''}</details><h3>Документы</h3>${flow.documents.map(d=>`<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${e(d.filename)} · ${e(d.signature.status)}</button>`).join('')||'<p class="muted">Не приложены</p>'}</section>${modelPanel(flow)}${chatPanel(a.id,messages)}</div><div>${actions?decisionForm({...a,reviewVersion:flow.version},run):`<section class="panel"><h2>Состояние рассмотрения</h2><p>${e(a.comment||'Заявка не ожидает решения этой роли.')}</p>${a.status==='escalated'?'<p>Решение принимает согласующий.</p>':''}${['approved','counter_offer'].includes(a.status)?`<button class="button secondary" data-op="revoke" data-id="${e(a.id)}">Отозвать предложение на доработку</button>`:''}</section>`}<section class="panel"><h3>Задачи</h3>${flow.tasks.map(t=>`<p>${t.status==='DONE'?'✓':'○'} ${e(t.title)}${t.answer?' · '+e(t.answer):''}</p>`).join('')||'<p class="muted">Нет задач</p>'}</section><section class="panel"><h3>История</h3><ol class="timeline">${flow.history.filter(h=>h.reason!=='Данные заявки обновлены').map(h=>`<li><span class="timeline-dot"></span><strong>${e(h.reason)}</strong><small>${date(h.created_at)}</small></li>`).join('')}</ol></section></div></div>`;}
const flowVersion=a=>a.reviewVersion;
function decisionForm(a,run){return `<section class="panel"><h2>Решение сотрудника</h2><form class="bank-decision-form form-stack" data-application="${e(a.id)}" data-version="${flowVersion(a)}"><label class="field"><span>Действие</span><select name="status"><option value="approved">Одобрить</option><option value="counter_offer">Встречное предложение</option><option value="needs_info">Запросить сведения</option><option value="rejected">Отказать</option>${a.status==='escalated'?'<option value="pending">Вернуть аналитику</option>':'<option value="escalated">Передать на согласование</option>'}</select></label><label class="field"><span>Мотивировка</span><textarea name="comment" required minlength="3" maxlength="1500" rows="3"></textarea></label><details><summary>Предложенные условия</summary><div class="form-stack">${field('Сумма, ₽','alternativeAmount',run?.policy.alternative_amount||a.amount,{type:'number',attrs:'min="1"'})}${field('Срок, мес.','months',a.months,{type:'number',attrs:'min="1" max="120"'})}${field('Ставка, %','annual_rate',productById(a.productId).rate,{type:'number',attrs:'min="1" max="60" step=".01"'})}<label class="field"><span>Продукт</span><select name="product_id">${['working','equipment','overdraft'].map(id=>`<option value="${id}" ${a.productId===id?'selected':''}>${e(productById(id).name)}</option>`).join('')}</select></label>${field('Предложение действует, дней','valid_days',7,{type:'number',attrs:'min="1" max="30"'})}</div></details><details><summary>Задача клиенту при запросе сведений</summary><div class="form-stack"><label class="field"><span>Тип</span><select name="task_kind"><option value="information">Вопрос</option><option value="document">Документ</option></select></label>${field('Заголовок задачи','task_title','',{attrs:'maxlength="255"'})}<label class="field"><span>Документ</span><select name="document_type">${['statement','accounts','tax','invoice'].map(t=>`<option>${t}</option>`).join('')}</select></label></div></details><button type="submit" class="button primary">Сохранить решение</button></form></section>`;}

export const needsOperationsLoad=(section,id='')=>!cache.has(section+':'+id);
export function installOperations(refresh){
  document.addEventListener('click',async event=>{
    const target=event.target.closest('[data-op]');if(!target||target.disabled)return;
    const {op,id,loan,value}=target.dataset;
    try{
      if(op==='schedule-view'||op==='schedule-month'){changeSchedule(loan,value,op==='schedule-month');refresh(false);return;}
      target.disabled=true;
      if(op==='notifications-read-all')await apiRequest('/api/notifications/read-all',{method:'POST'});
      if(op==='notification-read')await apiRequest(`/api/notifications/${id}/read`,{method:'POST'});
      if(op==='notification-archive')await apiRequest(`/api/notifications/${id}`,{method:'DELETE'});
      if(op==='messages-read')await apiRequest(`/api/applications/${id}/messages/read`,{method:'POST'});
      if(op==='assign')await apiRequest(`/api/analyst/applications/${id}/assign`,{method:'POST'});
      if(op==='revoke'){
        const comment=prompt('Причина отзыва предложения');if(!comment)return;
        await apiRequest(`/api/analyst/applications/${id}/revoke`,{method:'POST',body:{comment}});
      }
      await refresh(true);
    }catch(error){globalThis.dispatchEvent(new CustomEvent('delora:error',{detail:error.message}));}
    finally{if(target.isConnected)target.disabled=false;}
  });
  document.addEventListener('input',event=>{
    const id=event.target.dataset.scheduleRange;if(id){changeSchedule(id,event.target.value,true);refresh(false);}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(!form.matches('.bank-message-form,.task-answer-form,.bank-decision-form,.source-form,#team-invite-form,#team-join-form,#policy-form'))return;
    event.preventDefault();if(!form.reportValidity()||form.dataset.busy)return;
    const data=Object.fromEntries(new FormData(form)),submit=form.querySelector('[type="submit"]');
    form.dataset.busy='true';submit.disabled=true;
    try{
      if(form.matches('.bank-message-form')){
        const requestId=form.dataset.requestId||crypto.randomUUID();form.dataset.requestId=requestId;
        await apiRequest(`/api/applications/${form.dataset.application}/messages`,{method:'POST',body:{text:data.text,request_id:requestId}});
      }else if(form.matches('.task-answer-form')){
        await apiRequest(`/api/applications/${form.dataset.application}/tasks/${form.dataset.task}/complete`,{method:'POST',body:{answer:data.answer||'',document_id:data.document_id||null}});
      }else if(form.matches('.bank-decision-form')){
        if(!confirm('Сохранить решение по заявке?'))return;
        const body={status:data.status,comment:data.comment,expectedVersion:Number(form.dataset.version)};
        if(['approved','counter_offer'].includes(data.status))Object.assign(body,{alternativeAmount:Number(data.alternativeAmount),months:Number(data.months),annual_rate:Number(data.annual_rate),product_id:data.product_id,valid_days:Number(data.valid_days)});
        if(data.status==='needs_info')body.tasks=[{kind:data.task_kind,title:data.task_title||data.comment,description:data.comment,required:true,...(data.task_kind==='document'?{document_type:data.document_type}:{})}];
        await apiRequest(`/api/analyst/applications/${form.dataset.application}/decision`,{method:'POST',body});
      }else if(form.matches('.source-form')){
        await apiRequest(`/api/admin/integrations/${form.dataset.source}`,{method:'PUT',body:{mode:data.mode}});
      }else if(form.id==='policy-form'){
        await apiRequest('/api/admin/rules',{method:'POST',body:Object.fromEntries(Object.entries(data).map(([k,v])=>[k,Number(v)]))});
      }else if(form.id==='team-invite-form'){
        const invitation=await apiRequest('/api/team/invitations',{method:'POST',body:data});
        document.getElementById('invite-result').innerHTML=`<p>Приглашение для ${e(invitation.email)} действует 24 часа. Передайте сотруднику код один раз:</p><code class="invite-token">${e(invitation.token)}</code><p>Сотрудник открывает раздел «Присоединиться по приглашению» на странице входа.</p>`;
        return;
      }else if(form.id==='team-join-form'){
        await apiRequest('/api/team/join',{method:'POST',body:data});location.hash='/home';return;
      }
      await refresh(true);
    }catch(error){
      if(form.id==='team-join-form')document.getElementById('join-error').textContent=error.message;
      else globalThis.dispatchEvent(new CustomEvent('delora:error',{detail:error.message}));
    }finally{delete form.dataset.busy;if(submit.isConnected)submit.disabled=false;}
  });
}
