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
import { getState, ownApplications, ownDocuments } from "./store.mjs";
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
  return `<div class="product-grid">${PRODUCTS.map((p) => `<a class="product-card" href="#/products/${p.id}"><div class="product-intro"><span class="product-icon">${icon(p.icon)}</span><div><h3>${p.name}</h3><p>${p.description}</p></div></div><div class="product-bottom"><strong>до ${shortMoney(p.max)}</strong><span class="text-link">Условия и расчёт ${icon("arrow")}</span></div></a>`).join("")}</div>`;
}
export function home(user) {
  const apps = ownApplications();
  const pending = apps.filter((a) => a.status === "pending").length;
  const approved = apps.filter((a) =>
    ["approved", "completed"].includes(a.status),
  ).length;
  const docs = ownDocuments();
  const required = documentTypes(user.type, "equipment");
  const count = required.filter((t) =>
    docs.some((d) => d.type === t.id),
  ).length;
  return `${heading("Бизнес растёт. Мы рядом.", "Финансирование, заявки и документы в одном кабинете.", button(icon("plus") + " Новая заявка", "new-application"))}
  <section class="welcome-band"><div><h2>Планы на бизнес - деньги на дело</h2><p>Подберите финансирование под свою задачу</p><a class="button white" href="#/products">Подобрать кредит</a></div><div class="orbit" aria-hidden="true">${[0, 1, 2, 3, 4].map((i) => `<i style="--i:${i}"></i>`).join("")}</div></section>
  <div class="summary-grid"><a href="#/applications?status=pending" class="summary-item">${icon("clock", "amber")}<span>На рассмотрении</span><strong>${pending}</strong></a><a href="#/applications?status=approved" class="summary-item">${icon("check", "green")}<span>Одобрено</span><strong>${approved}</strong></a><a href="#/profile?documents" class="summary-item">${icon("file")}<span>Документы</span><strong>${count}<small> из ${required.length}</small></strong></a></div>
  <section class="section"><div class="section-title"><h2>Финансирование для ваших задач</h2></div>${productCards()}</section>
  <section class="section"><div class="section-title"><h2>Последние заявки</h2><a href="#/applications" class="text-link">Все заявки ${icon("arrow")}</a></div>${applicationTable(apps.slice(0, 2))}</section>
  <p class="footnote">Все условия, клиенты и решения в этой версии демонстрационные.</p>`;
}
export function products() {
  return `${heading("Подбор кредита", "Выберите задачу бизнеса. Рассчитайте условия перед подачей заявки.")}<div class="notice">${icon("info")}<span>Демонстрационные продукты. Ставки и лимиты заданы для хакатона и не являются предложением банка.</span></div>${productCards()}<section class="panel guide"><h2>Какой продукт подойдёт?</h2><div class="guide-grid">${PRODUCTS.map((p, i) => `<div><span class="step-number">0${i + 1}</span><h3>${p.name}</h3><p>${p.detail}</p><a href="#/products/${p.id}" class="text-link">Рассчитать ${icon("arrow")}</a></div>`).join("")}</div></section>`;
}
export function productDetail(id, user) {
  const p = productById(id);
  const initial =
    p.id === "equipment" ? 3000000 : p.id === "overdraft" ? 500000 : 1000000;
  return `<a href="#/products" class="back-link">${icon("arrow")} Все продукты</a>${heading(p.name, p.detail)}<div class="two-column"><section class="panel product-terms"><span class="product-icon large">${icon(p.icon)}</span><h2>Средства для вашего бизнеса</h2><dl class="details"><div><dt>Сумма</dt><dd>от ${shortMoney(p.min)} до ${shortMoney(p.max)}</dd></div><div><dt>${p.id === "overdraft" ? "Срок лимита" : "Срок кредита"}</dt><dd>${p.months[0]}-${p.months[1]} мес.</dd></div><div><dt>Демо-ставка</dt><dd>${p.rate}% годовых</dd></div><div><dt>Для кого</dt><dd>ИП и юридические лица</dd></div><div><dt>Особенность</dt><dd>${p.feature}</dd></div></dl><h3>Что понадобится</h3><ul class="check-list">${documentTypes(
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
            ? ["approved", "completed"].includes(a.status)
            : a.status === status,
        );
  return `${heading("Мои заявки", "Следите за решением и продолжайте сохранённые черновики.", button(icon("plus") + " Новая заявка", "new-application"))}<div class="tabs" role="navigation" aria-label="Фильтр заявок">${[
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
  const docs = getState().documents.filter((d) =>
    a.documentIds?.includes(d.id),
  );
  return `<a href="#/applications" class="back-link">${icon("arrow")} Мои заявки</a>${heading("Заявка " + e(a.id), "Создана " + date(a.createdAt), badge(a.status))}<div class="two-column"><section class="panel"><h2>${p.name}</h2><dl class="details"><div><dt>Сумма</dt><dd>${money(a.amount)}</dd></div><div><dt>Срок</dt><dd>${a.months} мес.</dd></div><div><dt>Цель</dt><dd>${e(a.purpose)}</dd></div><div><dt>Ставка</dt><dd>${p.rate}% годовых, демо</dd></div></dl>${a.comment ? `<div class="feedback"><h3>Комментарий аналитика</h3><p>${e(a.comment)}</p></div>` : ""}${a.alternativeAmount ? `<p>Возможная сумма для новой заявки: <strong>${money(a.alternativeAmount)}</strong></p>` : ""}${a.status === "draft" ? button("Продолжить заполнение", "edit-application", "primary", `data-id="${e(a.id)}"`) : ""}${a.status === "rejected" ? button("Изменить условия и подать заново", "revise-application", "primary", `data-id="${e(a.id)}"`) : ""}${a.status === "approved" ? `<p class="footnote">Принятие условий завершит учебный сценарий. Реальный договор не заключается, деньги не выдаются.</p>${button("Принять условия в демо", "accept-offer", "primary", `data-id="${e(a.id)}"`)}` : ""}${a.status === "pending" ? '<p class="notice">Заявка передана на рассмотрение. Решение и комментарий появятся здесь.</p>' : ""}${a.status === "completed" ? '<p class="notice success">Учебный сценарий завершён. Условия приняты.</p>' : ""}<h3 class="spaced">Документы заявки</h3>${docs.length ? docs.map((d) => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${icon("file")}${e(d.name)}${icon("arrow")}</button>`).join("") : '<p class="muted">У синтетической заявки файлы не приложены.</p>'}</section><section class="panel"><h2>Ход рассмотрения</h2><ol class="timeline">${a.history.map((h) => `<li><span class="timeline-dot"></span><strong>${e(h.text)}</strong><small>${date(h.at)}</small></li>`).join("")}</ol></section></div>`;
}
export function profile(user) {
  const docs = ownDocuments();
  const requirements = documentTypes(user.type, "equipment");
  return `${heading("Личный кабинет", "Данные бизнеса и документы для ваших заявок.")}<div class="profile-header panel"><span class="profile-avatar">${icon(user.type === "ip" ? "user" : "building")}</span><div><h2>${e(user.name)}</h2><p>${user.type === "ip" ? "Индивидуальный предприниматель" : "Юридическое лицо"} <span class="separator">/</span> ИНН ${e(user.inn)}</p></div><span class="badge neutral">${user.type === "ip" ? "ИП" : "Юрлицо"}</span></div><div class="two-column profile-columns"><section class="panel"><h2>Сведения о бизнесе</h2><form id="profile-form" class="form-stack">${field(user.type === "ip" ? "ФИО предпринимателя" : "Наименование организации", "name", user.name, { required: true, attrs: 'maxlength="160"' })}${field("Контактное лицо", "contact", user.contact, { required: true, attrs: 'maxlength="100"' })}<div class="form-grid">${field("ИНН", "inn", user.inn, { attrs: "readonly", hint: "Указан при регистрации" })}${field(user.type === "ip" ? "ОГРНИП" : "ОГРН", "ogrn", user.ogrn, { attrs: `inputmode="numeric" pattern="[0-9]{${user.type === "ip" ? 15 : 13}}" maxlength="${user.type === "ip" ? 15 : 13}"` })}</div><div class="form-grid">${field("Основной ОКВЭД", "okved", user.okved, { attrs: 'pattern="[0-9]{2}(\\.[0-9]{1,2}){0,2}" maxlength="8" placeholder="47.91"' })}${field("Дата регистрации бизнеса", "registration", user.registration, { type: "date", attrs: `max="${new Date().toISOString().slice(0, 10)}"` })}</div>${field(user.type === "ip" ? "Адрес ведения деятельности" : "Юридический адрес", "address", user.address, { attrs: 'maxlength="250"' })}<h3>Контакты аккаунта</h3><div class="form-grid">${field("Электронная почта", "email", user.email, { type: "email", required: true, attrs: 'maxlength="150"' })}${field("Телефон", "phone", user.phone, { type: "tel", attrs: 'maxlength="25"' })}</div><button class="button primary" type="submit">Сохранить изменения</button></form></section><section class="panel" id="documents"><h2>Документы</h2><p class="muted">Добавьте один раз и используйте в новых заявках.</p><div class="document-list">${requirements
    .map((t) => {
      const found = docs.filter((d) => d.type === t.id);
      return `<div class="document-slot"><div class="document-slot-title">${icon("file")}<div><strong>${t.name}</strong><small>${t.hint}</small></div>${found.length ? icon("check", "green") : ""}</div>${found.map((d) => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}"><span>${e(d.name)}<small>${d.demo ? "Синтетический пример" : Math.ceil(d.size / 1024) + " КБ"} - ${date(d.createdAt)}</small></span>${icon("arrow")}</button>`).join("")}<label class="upload-label">${icon("upload")} ${found.length ? "Добавить ещё" : "Прикрепить документ"}<input class="file-input" type="file" data-upload="${t.id}" accept=".pdf,.jpg,.jpeg,.png"></label></div>`;
    })
    .join(
      "",
    )}</div><p class="footnote">PDF, JPG или PNG, до 10 МБ. Файлы сохраняются только в этом браузере. Используйте синтетические документы.</p></section></div>`;
}
