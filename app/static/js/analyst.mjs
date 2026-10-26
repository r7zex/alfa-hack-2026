import { apiRequest } from "./auth.mjs";
import { money, date, productById, escape as e } from "./domain.mjs";
import { heading, icon, badge, empty } from "./ui.mjs";

let rows = [];
let organizations = [];
let loaded = false;
let analystView="current";
let error = "";
const filters = { status: "pending", businessId: "", userId: "", query: "", sort: "newest" };

export async function loadAnalyst() {
  const params = new URLSearchParams({ status: filters.status, sort: filters.sort });
  if(analystView==="mine")params.set("mine","true");
  if (filters.businessId) params.set("business_id", filters.businessId);
  if (filters.userId) params.set("created_by_user_id", filters.userId);
  if (filters.query) params.set("query", filters.query);
  try {
    [rows, organizations] = await Promise.all([
      apiRequest("/api/analyst/applications?" + params),
      apiRequest("/api/analyst/organizations"),
    ]);
    rows = await Promise.all(rows.map(async a => ({...a, workflow: await apiRequest(`/api/applications/${a.id}/workflow`)})));
    if(rows.some(a=>a.version!==a.workflow.version))throw Error("Заявка изменилась во время загрузки. Обновите очередь.");
    loaded = true;
    error = "";
  } catch (err) {
    error = err.message;
    loaded = true;
    throw err;
  }
}
export function resetAnalyst() {
  loaded = false;
  rows = [];
  organizations = [];
  error = "";
  Object.assign(filters, { status: "pending", businessId: "", userId: "", query: "", sort: "newest" });
}
export function changeAnalystFilter(name, value) {
  if (!Object.hasOwn(filters, name)) return;
  filters[name] = value;
  if (name === "businessId") filters.userId = "";
}
export function analystPendingCount() {
  return rows.filter(a => a.status === "pending").length;
}
export function analyst(history = false) {
  const business = organizations.find(o => String(o.id) === String(filters.businessId));
  const users = business?.users || [];
  const option = (value, label, active) => `<option value="${e(value)}" ${String(value) === String(active) ? "selected" : ""}>${e(label)}</option>`;
  return `${heading(({history:"История решений",mine:"Мои заявки",escalations:"Эскалации",current:"Заявки на рассмотрении"}[analystView]||"Очередь заявок"),
      "Просматривайте проверки, документы и обращения клиентов.")}
    <div class="analyst-filters">
      <label>Организация<select data-analyst-filter="businessId">${option("", "Все компании", filters.businessId)}${organizations.map(o => option(o.id, o.name + " · " + o.inn + " (" + o.applications + ")", filters.businessId)).join("")}</select></label>
      <label>Автор заявки<select data-analyst-filter="userId" ${business ? "" : "disabled"}>${option("", "Все пользователи", filters.userId)}${users.map(u => option(u.id, u.email, filters.userId)).join("")}</select></label>
      <label>Сортировка<select data-analyst-filter="sort">${[
        ["newest", "Сначала новые"], ["oldest", "Сначала старые"],
        ["amount_desc", "Сумма по убыванию"], ["amount_asc", "Сумма по возрастанию"],
        ["organization", "По организациям"],
      ].map(([id, label]) => option(id,label,filters.sort)).join("")}</select></label>
      <label>Поиск<input data-analyst-search type="search" value="${e(filters.query)}" placeholder="Название, ИНН или email"></label>
      <button class="button text" type="button" data-action="analyst-refresh">${icon("cycle")} Обновить</button>
    </div>
    ${error ? `<p class="form-error">${e(error)}</p>` : ""}
    ${!loaded ? '<p class="muted">Загрузка заявок…</p>' : analystRows(history)}
    <p class="footnote">Решения и документы сохранены на сервере. Оценка риска и выдача демонстрационные.</p>`;
}
export function analystRows(history = false) {
  const list = rows.filter(a => analystView === "mine" || analystView === "escalations" ? true : history ? ["approved","counter_offer","rejected","needs_info","offer_accepted","offer_declined","signed","disbursed","completed","processing_error","cancelled"].includes(a.status) : a.status === "pending");
  if (!list.length) return empty("Заявки не найдены", "Проверьте фильтры или дождитесь новых заявок.");
  return `<div class="review-list"><div class="review-table-head"><span>Заявка / дата</span><span>Организация</span><span>Продукт</span><span>Сумма</span><span>Статус</span><span></span></div>
    ${list.map(a => `<details class="review-row"><summary>
    <span><strong>${e(a.id.slice(0,8))}</strong><small>${date(a.createdAt)}</small></span>
    <span><strong>${e(a.business?.name || "Без привязки")}</strong><small>${e(a.business?.inn || "—")} · ${e(a.creator?.email || "—")}</small></span>
    <span>${e(productById(a.productId).name)}<small>${a.months} мес.</small></span>
    <span class="nowrap">${money(a.amount)}</span><span>${badge(a.status)}</span>${icon("chevron")}
    </summary><div class="review-expanded"><div class="review-data"><section>
      <a class="button secondary" href="#/review/${e(a.id)}">Открыть рассмотрение</a><h3>Организация и заявитель</h3><dl class="details compact">
      <div><dt>Компания</dt><dd>${e(a.business?.name || "Не указана")}</dd></div>
      <div><dt>ИНН</dt><dd>${e(a.business?.inn || "—")}</dd></div>
      <div><dt>Автор</dt><dd>${e(a.creator?.email || "Не определён")}</dd></div>
      <div><dt>ОКВЭД</dt><dd>${e(a.business?.okved || "Не указан")}</dd></div>
      <div><dt>Контакт</dt><dd>${e(a.business?.contact || "—")}</dd></div></dl>
      <h3>Финансы и потребность</h3><dl class="details compact">
      <div><dt>Цель</dt><dd>${e(a.purpose || "—")}</dd></div>
      <div><dt>Выручка / месяц</dt><dd>${money(a.revenue || 0)}</dd></div>
      <div><dt>Расходы / месяц</dt><dd>${money(a.expenses || 0)}</dd></div>
      <div><dt>Платежи по кредитам</dt><dd>${money(a.debtPayment || 0)}</dd></div>
      </dl>${reviewEvidence(a)}
      </section><section>${history ? `<h3>Решение банка</h3>${badge(a.status)}<p>${e(a.comment || "Без комментария")}</p>
      ${a.alternativeAmount ? `<p>Альтернативная сумма: ${money(a.alternativeAmount)}</p>` : ""}
      <p class="muted">${a.decidedAt ? date(a.decidedAt) : ""}</p>${a.status === "approved" && !a.workflow?.offers.length ? `<button type="button" class="button secondary" data-action="review-legacy-approval" data-id="${e(a.id)}" data-version="${a.workflow?.version??a.version}">Запросить документы для прежнего одобрения</button>` : ""}` :
      `<form class="decision-form form-stack" data-id="${e(a.id)}" data-version="${a.workflow?.version??a.version}">
      <h3>Принять решение</h3><fieldset class="decision-options">
      <legend class="sr-only">Кредитное решение</legend>
      <label><input type="radio" name="status" value="approved" required> Одобрить</label>
      <label><input type="radio" name="status" value="rejected" required> Отказать</label><label><input type="radio" name="status" value="needs_info" required> Запросить уточнения</label></fieldset>
      <label class="field"><span>Комментарий клиенту</span><textarea name="comment" rows="3" maxlength="1500" placeholder="Причина решения или условия"></textarea></label>
      <label class="field"><span>Альтернативная сумма, ₽ (необязательно)</span>
      <input type="number" name="alternativeAmount" min="1" step="1"></label>
      <button class="button primary" type="submit">Сохранить решение и уведомить клиента</button>
      </form>`}</section></div></div></details>`).join("")}</div>`;
}
export async function sendAnalystDecision(id, payload) {
  await apiRequest("/api/analyst/applications/" + encodeURIComponent(id) + "/decision", {
    method: "POST", body: payload,
  });
  await loadAnalyst();
}

function reviewEvidence(a) {
  const flow = a.workflow;
  const run = flow?.assessments.at(-1);
  const labels = {recommend_approval:"Рекомендуется одобрение", recommend_rejection:"Рекомендуется отказ", request_info:"Нужны уточнения", alternative_terms:"Предлагается снизить сумму", technical_error:"Техническая ошибка"};
  return `<h3>Проверки и демонстрационная оценка</h3>${run ? `<p><strong>${e(labels[run.policy.recommendation])}</strong></p><p>${run.policy.reasons.map(e).join(". ")}</p>${run.policy.alternative_amount ? `<p>Доступная демо-сумма: ${money(run.policy.alternative_amount)}</p>` : ""}<p class="footnote">${e(run.risk.disclaimer)}</p><ul>${run.checks.map(c => `<li>${e(c.source)}: ${e(c.status)} · ${date(c.received_at)}</li>`).join("")}</ul>` : '<p>Проверка будет выполнена перед решением по ранее отправленной заявке.</p>'}<h3>Документы</h3>${flow?.documents.map(d => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${e(d.filename)} · ${e(d.signature.status)}</button>`).join("") || '<p class="muted">Документы не приложены.</p>'}<details><summary>История заявки</summary><ol>${flow?.history.filter(h => h.old_status !== h.new_status || h.reason !== "Данные заявки обновлены").map(h => `<li>${e(h.reason)} · ${date(h.created_at)}</li>`).join("") || ""}</ol></details>`;
}

export function setAnalystView(view){
  analystView=view;
  changeAnalystFilter("status",view==="history"||view==="mine"?"all":view==="escalations"?"escalated":"pending");
}
