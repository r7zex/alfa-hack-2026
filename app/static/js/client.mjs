import {clientExtra,challengeFor} from "./operations.mjs";
import { artwork, pageBanner } from "./artwork.mjs";
import {
  PRODUCTS,
  productById,
  money,
  shortMoney,
  date,
  escape as e,
  documentTypes,
  estimate,
} from "./domain.mjs";
import { getState, ownApplications, ownDocuments, currentUser } from "./store.mjs";
import {
  heading,
  icon,
  button,
  badge,
  field,
  applicationTable,
  empty,
} from "./ui.mjs";
export function productCards() {
  return `<div class="product-grid">${PRODUCTS.map((p) => `<a class="product-card" href="#/products/${p.id}">${artwork(p.id, "product-art")}<div class="product-intro"><div><h3>${p.name}</h3><p>${p.description}</p></div></div><div class="product-bottom"><strong>до ${shortMoney(p.max)}</strong><span class="text-link">Условия и расчёт ${icon("arrow")}</span></div></a>`).join("")}</div>`;
}
export function home(user) {
  const apps = ownApplications();
  const pending = apps.filter((a) => ["pending", "submitted", "processing", "data_check", "enrichment", "scoring", "decision", "escalated", "needs_info", "processing_error"].includes(a.status)).length;
  const approved = apps.filter((a) =>
    ["approved", "counter_offer", "offer_accepted", "signed", "disbursed", "completed"].includes(a.status),
  ).length;
  const docs = ownDocuments();
  const required = documentTypes(user.type, "equipment");
  const count = required.filter((t) =>
    docs.some((d) => d.type === t.id),
  ).length;
  return `${heading("Бизнес растёт. Мы рядом.", "Финансирование, заявки и документы в одном кабинете.", button(icon("plus") + " Новая заявка", "new-application"))}
  <section class="welcome-band"><div><h2>Планы на бизнес - деньги на дело</h2><p>Подберите финансирование под свою задачу</p><a class="button primary" href="#/products">Подобрать кредит</a></div>${artwork("growth", "welcome-art", true)}</section>
  <div class="summary-grid"><a href="#/applications?status=pending" class="summary-item">${icon("clock", "amber")}<span>На рассмотрении</span><strong>${pending}</strong></a><a href="#/applications?status=approved" class="summary-item">${icon("check", "green")}<span>Одобрено</span><strong>${approved}</strong></a><a href="#/profile?documents" class="summary-item">${icon("file")}<span>Документы</span><strong>${count}<small> из ${required.length}</small></strong></a></div>
  <section class="section"><div class="section-title"><h2>Финансирование для ваших задач</h2></div>${productCards()}</section>
  <section class="section"><div class="section-title"><h2>Последние заявки</h2><a href="#/applications" class="text-link">Все заявки ${icon("arrow")}</a></div>${applicationTable(apps.slice(0, 2))}</section>
  <p class="footnote">Все условия, клиенты и решения в этой версии демонстрационные.</p>`;
}
export function products() {
  return `${pageBanner(heading("Подбор кредита", "Выберите задачу бизнеса. Рассчитайте условия перед подачей заявки."), "selection")}<div class="notice">${icon("info")}<span>Демонстрационные продукты. Ставки и лимиты заданы для хакатона и не являются предложением банка.</span></div><section class="panel"><h2>Подобрать по потребности</h2><form id="recommendation-form" class="form-stack"><div class="form-grid">${field("Сумма, ₽", "amount", 1000000, {type:"number",required:true,attrs:'min="1"'})}${field("Срок, мес.","months",12,{type:"number",required:true,attrs:'min="1" max="120"'})}</div>${field("Цель", "purpose", "Закупка товаров",{required:true,attrs:'maxlength="500"'})}<div class="form-grid">${field("Выручка в месяц, ₽","revenue",1500000,{type:"number",required:true,attrs:'min="1"'})}${field("Расходы в месяц, ₽","expenses",700000,{type:"number",required:true,attrs:'min="0"'})}</div>${field("Другие кредитные платежи, ₽","debt_payment",10000,{type:"number",required:true,attrs:'min="0"'})}<button class="button primary" type="submit">Подобрать</button></form><div id="recommendation-result" aria-live="polite"></div></section>${productCards()}<section class="panel guide"><h2>Какой продукт подойдёт?</h2><div class="guide-grid">${PRODUCTS.map((p, i) => `<div><span class="step-number">0${i + 1}</span><h3>${p.name}</h3><p>${p.detail}</p><a href="#/products/${p.id}" class="text-link">Рассчитать ${icon("arrow")}</a></div>`).join("")}</div></section>`;
}
export function productDetail(id, user) {
  const p = productById(id);
  const initial =
    p.id === "equipment" ? 3000000 : p.id === "overdraft" ? 500000 : 1000000;
  return `<a href="#/products" class="back-link">${icon("arrow")} Все продукты</a>${pageBanner(heading(p.name, p.detail), p.id === "equipment" ? "transport" : p.id)}<div class="two-column"><section class="panel product-terms">${artwork(p.id, "terms-art")}<h2>Средства для вашего бизнеса</h2><dl class="details"><div><dt>Сумма</dt><dd>от ${shortMoney(p.min)} до ${shortMoney(p.max)}</dd></div><div><dt>${p.id === "overdraft" ? "Срок лимита" : "Срок кредита"}</dt><dd>${p.months[0]}-${p.months[1]} мес.</dd></div><div><dt>Демо-ставка</dt><dd>${p.rate}% годовых</dd></div><div><dt>Для кого</dt><dd>ИП и юридические лица</dd></div><div><dt>Особенность</dt><dd>${p.feature}</dd></div></dl><h3>Что понадобится</h3><ul class="check-list">${documentTypes(
    user.type,
    p.id,
  )
    .map(
      (d) =>
        `<li>${icon("check")}<span>${d.name}<small>${d.hint}</small></span></li>`,
    )
    .join(
      "",
    )}</ul><p class="footnote">Учебный перечень документов. В кейсе нет отдельных обязательных списков для каждого продукта.</p></section><section class="panel calculator"><h2>Рассчитайте ${p.id === "overdraft" ? "использование лимита" : "платёж"}</h2><form id="calculator" data-product="${p.id}">${field(p.id === "overdraft" ? "Использованная сумма, ₽" : "Сумма кредита, ₽", "amount", initial, { type: "number", required: true, attrs: `min="${p.min}" max="${p.max}" step="10000"` })}<input class="range" type="range" name="amountRange" aria-label="Изменить сумму" min="${p.min}" max="${p.max}" step="10000" value="${initial}"><div class="range-labels"><span>${shortMoney(p.min)}</span><span>${shortMoney(p.max)}</span></div>${field(p.id === "overdraft" ? "Срок действия лимита, мес." : "Срок кредита, мес.", "months", p.id === "overdraft" ? 6 : 24, { type: "number", required: true, attrs: `min="${p.months[0]}" max="${p.months[1]}" step="1"` })}${p.id === "overdraft" ? field("Дней использования суммы", "days", 30, { type: "number", required: true, attrs: 'min="1" max="365" step="1"' }) : ""}<div id="calculation" class="calculation"></div><button class="button primary full" type="submit">Подать заявку ${icon("arrow")}</button><p class="footnote">${p.id === "overdraft" ? "Расчёт процентов за указанные дни. Основной долг возвращается отдельно." : "Аннуитетный расчёт без комиссий и страховки."} Расчёт предварительный.</p></form></section></div>`;
}
export function calculationHtml(p, amount, months, days) {
  const result = estimate(p, amount, months, days);
  return `<span>${p.id === "overdraft" ? "Проценты за период" : "Ежемесячный платёж"}</span><strong>${money(result.installment)}</strong><div><span>Ставка</span><b>${p.rate}% годовых</b></div><div><span>${p.id === "overdraft" ? "Долг и проценты" : "Всего к возврату"}</span><b>${money(result.total)}</b></div>`;
}
export function applications(status = "all") {
  const all = ownApplications();
  const apps =
    status === "all"
      ? all
      : all.filter((a) =>
          status === "approved"
            ? ["approved", "counter_offer", "offer_accepted", "signed", "disbursed", "completed"].includes(a.status)
            : a.status === status,
        );
  return `${pageBanner(heading("Мои заявки", "Следите за решением и продолжайте сохранённые черновики.", button(icon("plus") + " Новая заявка", "new-application")), "applications")}<div class="tabs" role="navigation" aria-label="Фильтр заявок">${[
    ["all", "Все"],
    ["pending", "На рассмотрении"],
    ["approved", "Одобрено"],
    ["rejected", "Отказано"],
    ["draft", "Черновики"],
  ]
    .map(
      ([id, title]) =>
        `<a class="tab ${id === status ? "active" : ""}" href="#/applications?status=${id}" ${id === status ? 'aria-current="page"' : ""}>${title}${id === "all" ? ` <span>${all.length}</span>` : ""}</a>`,
    )
    .join(
      "",
    )}</div>${apps.length ? applicationTable(apps) : empty("Здесь пока пусто", "Заявки с таким статусом появятся в этом разделе.", button("Новая заявка", "new-application"))}`;
}
export function applicationDetail(id) {
  const a = ownApplications().find((a) => a.id === id);
  if (!a)
    return empty(
      "Заявка не найдена",
      "Вернитесь к своим заявкам.",
      '<a class="button primary" href="#/applications">Мои заявки</a>',
    );
  const p = productById(a.productId);
  const docs = a.workflow?.documents?.map(d => ({...d, name: d.filename})) || getState().documents.filter(d => a.documentIds?.includes(d.id));
  return `<a href="#/applications" class="back-link">${icon("arrow")} Мои заявки</a>${heading("Заявка " + e(a.id.slice(0, 8).toUpperCase()), "Создана " + date(a.createdAt), badge(a.status))}<div class="two-column"><section class="panel"><h2>${p.name}</h2><dl class="details"><div><dt>Сумма</dt><dd>${money(a.amount)}</dd></div><div><dt>Срок</dt><dd>${a.months} мес.</dd></div><div><dt>Цель</dt><dd>${e(a.purpose)}</dd></div><div><dt>Ставка</dt><dd>${p.rate}% годовых, демо</dd></div></dl>${a.comment ? `<div class="feedback"><h3>Комментарий аналитика</h3><p>${e(a.comment)}</p></div>` : ""}${a.alternativeAmount ? `<p>Альтернативная сумма: <strong>${money(a.alternativeAmount)}</strong></p>` : ""}${["draft", "needs_info"].includes(a.status) ? button("Продолжить заполнение", "edit-application", "primary", `data-id="${e(a.id)}"`) : ""}${a.status === "rejected" ? button("Изменить условия и подать заново", "revise-application", "primary", `data-id="${e(a.id)}"`) : ""}${workflowPanel(a)}<h3 class="spaced">Документы заявки</h3>${docs.length ? docs.map((d) => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${icon("file")}${e(d.name)}${icon("arrow")}</button>`).join("") : '<p class="muted">Документы ещё не приложены.</p>'}</section><section class="panel"><h2>Ход рассмотрения</h2><ol class="timeline">${a.history.map((h) => `<li><span class="timeline-dot"></span><strong>${e(h.text)}</strong><small>${date(h.at)}</small></li>`).join("")}</ol></section></div>${clientExtra(a)}`;
}
export function profile(user) {
  const docs = ownDocuments();
  const requirements = documentTypes(user.type, "equipment");
  return `${pageBanner(heading("Личный кабинет", "Данные бизнеса и документы для ваших заявок."), "profile")}<div class="profile-header panel">${artwork(user.type === "ip" ? "profile" : "business", "profile-business-art")}<div><h2>${e(user.name)}</h2><p>${user.type === "ip" ? "Индивидуальный предприниматель" : "Юридическое лицо"} <span class="separator">/</span> ИНН ${e(user.inn)}</p></div><span class="badge neutral">${user.type === "ip" ? "ИП" : "Юрлицо"}</span></div><div class="two-column profile-columns"><section class="panel"><h2>Сведения о бизнесе</h2><form id="profile-form" class="form-stack">${field(user.type === "ip" ? "ФИО предпринимателя" : "Наименование организации", "name", user.name, { required: true, attrs: 'maxlength="160"' })}${field("Контактное лицо", "contact", user.contact, { required: true, attrs: 'maxlength="100"' })}<div class="form-grid">${field("ИНН", "inn", user.inn, { attrs: "readonly", hint: "Указан при регистрации" })}${field(user.type === "ip" ? "ОГРНИП" : "ОГРН", "ogrn", user.ogrn, { attrs: `inputmode="numeric" pattern="[0-9]{${user.type === "ip" ? 15 : 13}}" maxlength="${user.type === "ip" ? 15 : 13}"` })}</div>${user.type === "llc" ? field("КПП", "kpp", user.kpp, { attrs: 'inputmode="numeric" pattern="[0-9]{9}" maxlength="9"' }) : ""}<div class="form-grid">${field("Основной ОКВЭД", "okved", user.okved, { attrs: 'pattern="[0-9]{2}(\\.[0-9]{1,2}){0,2}" maxlength="8" placeholder="47.91"' })}${field("Дата регистрации бизнеса", "registration", user.registration, { type: "date", attrs: `max="${new Date().toISOString().slice(0, 10)}"` })}</div>${field(user.type === "ip" ? "Адрес ведения деятельности" : "Юридический адрес", "address", user.address, { attrs: 'maxlength="250"' })}<h3>Контакты аккаунта</h3><div class="form-grid">${field("Электронная почта", "email", user.email, { type: "email", required: true, attrs: 'maxlength="150" readonly' })}${field("Телефон", "phone", user.phone, { type: "tel", attrs: 'maxlength="25"' })}</div><button class="button primary" type="submit">Сохранить изменения</button></form><h3>Безопасность аккаунта</h3><form id="password-form" class="form-stack">${field("Текущий пароль", "current_password", "", { type: "password", required: true, attrs: 'maxlength="128" autocomplete="current-password"' })}${field("Новый пароль", "new_password", "", { type: "password", required: true, attrs: 'minlength="8" maxlength="128" autocomplete="new-password"' })}${field("Повторите новый пароль", "confirm_password", "", { type: "password", required: true, attrs: 'minlength="8" maxlength="128" autocomplete="new-password"' })}<button class="button secondary" type="submit">Изменить пароль</button></form>${button("Выйти на всех устройствах", "logout-all", "text")}</section><section class="panel" id="documents"><h2>Документы</h2><p class="muted">Добавьте один раз и используйте в новых заявках.</p><div class="document-list">${requirements
    .map((t) => {
      const found = docs.filter((d) => d.type === t.id);
      return `<div class="document-slot"><div class="document-slot-title">${icon("file")}<div><strong>${t.name}</strong><small>${t.hint}</small></div>${found.length ? icon("check", "green") : ""}</div>${found.map((d) => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}"><span>${e(d.name)}<small>${d.demo ? "Синтетический пример" : Math.ceil(d.size / 1024) + " КБ"} - ${date(d.createdAt)}</small></span>${icon("arrow")}</button>`).join("")}<label class="upload-label">${icon("upload")} ${found.length ? "Добавить ещё" : "Прикрепить документ"}<input class="file-input" type="file" data-upload="${t.id}" accept=".pdf"></label></div>`;
    })
    .join(
      "",
    )}</div><p class="footnote">PDF, до 10 МБ. Файлы сохраняются на сервере. Используйте синтетические документы.</p></section></div>`;
}

function workflowPanel(a) {
  const flow = a.workflow;
  if (!flow) return "";
  const run = flow.assessments.at(-1);
  const offer = flow.offers.at(-1);
  const activeOffer=offer?.status==="offered" && (!offer.expires_at || new Date(offer.expires_at)>new Date());
  const actionForm = (operation, label, consent) => `<form id="offer-action-form" data-id="${e(a.id)}" data-operation="${operation}" class="form-stack"><label class="check-field"><input type="checkbox" name="acknowledged" required><span>${consent}</span></label><button class="button primary" type="submit">${label}</button></form>`;
  return `<section class="spaced"><h3>Проверка заявки</h3>${run ? `<p>${run.policy.reasons.map(e).join(". ")}</p><p class="footnote">Демонстрационная оценка риска: ${run.risk.points}/100. Это не вероятность дефолта и не политика банка.</p>` : '<p class="muted">Проверки начнутся после отправки заявки.</p>'}
  ${button("Обновить статус", "refresh-applications", "text")}
  ${a.status === "needs_info" ? '<p class="notice">Аналитик запросил уточнения. Дополните заявку и отправьте повторно.</p>' : ""}
  ${a.status === "processing_error" ? button("Повторить с доступными демо-источниками", "retry-processing", "secondary", `data-id="${e(a.id)}"`) : ""}
  ${offer && !currentSigner() ? '<p class="notice">Принятие и подписание доступны уполномоченному представителю организации.</p>' : ""}${offer ? `<h3>Предложение · версия ${offer.version}</h3><div class="offer-comparison"><div><h4>Запрошено</h4><p>${money(a.amount)}</p><p>${a.months} мес. · ${productById(a.productId).rate}%</p><p>${e(productById(a.productId).name)}</p></div><div><h4>Предложено</h4><p>${money(offer.amount)}</p><p>${offer.months} мес. · ${e(offer.annual_rate)}%</p><p>${e(productById(offer.product_id||a.productId).name)}</p></div></div>${offer.expires_at?`<p class="footnote">Действует до ${date(offer.expires_at)}</p>`:""}${!activeOffer && ["approved","counter_offer"].includes(a.status)?'<p class="notice">Предложение истекло или отозвано. Свяжитесь с банком.</p>':""}<dl class="details"><div><dt>Сумма / срок</dt><dd>${money(offer.amount)} / ${offer.months} мес.</dd></div><div><dt>Ставка / платёж</dt><dd>${offer.annual_rate}% / ${money(offer.monthly_payment)}</dd></div></dl>${offer.principal_due ? `<p>Проценты ежемесячно; основной долг ${money(offer.principal_due)} возвращается в конце срока.</p>` : ""}<details><summary>Демонстрационный договор</summary><p>${e(offer.contract_text)}</p></details>
  ${["approved","counter_offer"].includes(a.status) && currentSigner() && activeOffer ? actionForm("accept", "Принять предложение", "Согласен с предложенными демонстрационными условиями") + button("Отклонить предложение", "decline-offer", "text", `data-id="${e(a.id)}"`) : ""}
  ${a.status === "offer_accepted" && currentSigner() ? signingForm(a,offer) : ""}
  ${a.status === "signed" && currentSigner() ? button("Завершить демонстрационную выдачу", "disburse-offer", "primary", `data-id="${e(a.id)}"`) : ""}
  ${a.status === "disbursed" ? '<p class="notice success">Демонстрационная выдача завершена. Реальные деньги не переводились.</p>' : ""}
  ${a.status === "offer_declined" ? '<p class="notice">Вы отклонили предложение.</p>' : ""}` : ""}</section>`;
}

function currentSigner(){ return currentUser()?.can_sign !== false; }
function signingForm(a,offer){
  const challenge=challengeFor(a.id);
  return `<p class="footnote">Условное подписание внутри продукта, не УКЭП и не SMS.</p>${button("Получить демо-код", "request-signing-code", "secondary", `data-id="${e(a.id)}"`)}${challenge ? `<form id="offer-action-form" data-id="${e(a.id)}" data-operation="sign" class="form-stack"><p>Код действителен до ${new Date(challenge.expires_at).toLocaleTimeString("ru-RU")}</p>${challenge.demo_code?`<p class="notice">Демонстрационный код: <strong data-demo-code>${e(challenge.demo_code)}</strong></p>`:'<p class="notice">Код выдан. Демонстрационный показ кода отключён.</p>'}<label class="check-field"><input type="checkbox" name="acknowledged" required><span>Ознакомился с демонстрационным договором и подтверждаю условное подписание</span></label>${field("Одноразовый код","code","",{required:true,attrs:'inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"'})}<button class="button primary" type="submit">Подписать демо-договор</button></form>`:''}`;
}
