import { productById, money, date, escape as e } from "./domain.mjs";
import { getState } from "./store.mjs";
import { heading, icon, badge, field, empty } from "./ui.mjs";
export function analyst(history = false) {
  const all = getState().applications;
  const count = all.filter((a) => a.status === "pending").length;
  return `${heading(history ? "История заявок" : "Текущие заявки", history ? "Принятые решения и обратная связь клиентам." : "Проверьте данные, примите решение и отправьте обратную связь.")}<div class="analyst-toolbar"><div class="tabs"><a class="tab ${!history ? "active" : ""}" href="#/current">На рассмотрении <span>${count}</span></a><a class="tab ${history ? "active" : ""}" href="#/history">История решений</a></div><label class="search-field">${icon("search")}<input id="analyst-search" type="search" placeholder="Поиск по ИНН" aria-label="Поиск по ИНН" inputmode="numeric" maxlength="12"></label></div><div id="analyst-list" data-history="${history}">${analystRows(history)}</div><p class="footnote">Демо-аналитик видит синтетические заявки этого браузера. Решения не являются реальными кредитными решениями.</p>`;
}
export function analystRows(history, query = "") {
  const s = getState();
  const apps = s.applications.filter(
    (a) =>
      (history
        ? ["approved", "rejected", "completed"].includes(a.status)
        : a.status === "pending") &&
      (s.users.find((u) => u.id === a.ownerId)?.inn || "").includes(
        query.trim(),
      ),
  );
  if (!apps.length)
    return empty(
      query
        ? "По этому ИНН ничего не найдено"
        : history
          ? "Решений пока нет"
          : "Все заявки рассмотрены",
      query
        ? "Проверьте цифры или очистите поиск."
        : "Новые заявки появятся здесь после отправки клиентом.",
    );
  return `<div class="review-list"><div class="review-table-head"><span>Заявка / дата</span><span>Клиент / ИНН</span><span>Продукт</span><span>Сумма</span><span>Статус</span><span></span></div>${apps
    .map((a) => {
      const user = a.profile || s.users.find((u) => u.id === a.ownerId);
      const p = productById(a.productId);
      const docs = s.documents.filter((d) => a.documentIds?.includes(d.id));
      return `<details class="review-row"><summary><span><strong>${e(a.id)}</strong><small>${date(a.createdAt)}</small></span><span><strong>${e(user.name)}</strong><small>${user.type === "ip" ? "ИП" : "Юрлицо"} / ${e(user.inn)}</small></span><span>${p.name}<small>${a.months} мес.</small></span><span class="nowrap">${money(a.amount)}</span><span>${badge(a.status)}</span>${icon("chevron")}</summary><div class="review-expanded"><div class="review-data"><section><h3>Данные заявки</h3><dl class="details compact"><div><dt>Цель</dt><dd>${e(a.purpose)}</dd></div><div><dt>Выручка в месяц</dt><dd>${money(a.revenue)}</dd></div><div><dt>Расходы в месяц</dt><dd>${money(a.expenses)}</dd></div><div><dt>Другие кредитные платежи</dt><dd>${money(a.debtPayment)}</dd></div><div><dt>Электронная почта</dt><dd>${e(user.email)}</dd></div><div><dt>ОКВЭД</dt><dd>${e(user.okved || "Не указан")}</dd></div></dl><h3>Документы</h3>${docs.length ? docs.map((d) => `<button class="document-link" data-action="download-document" data-id="${e(d.id)}">${icon("file")}${e(d.name)}${icon("arrow")}</button>`).join("") : '<p class="muted">Синтетический пример без приложенных файлов.</p>'}</section>${history ? `<section class="decision-readonly"><h3>Решение и обратная связь</h3>${badge(a.status)}<p>${e(a.comment || "Комментарий не добавлен.")}</p>${a.alternativeAmount ? `<p>Сумма для повторной заявки: <strong>${money(a.alternativeAmount)}</strong></p>` : ""}<small>Решение сохранено ${date(a.updatedAt)}</small></section>` : `<form class="decision-form form-stack" data-id="${e(a.id)}"><h3>Решение по заявке</h3><fieldset class="decision-options"><legend class="sr-only">Кредитное решение</legend><label><input type="radio" name="status" value="approved" required> ${icon("check")} Одобрить</label><label><input type="radio" name="status" value="rejected" required> ${icon("close")} Отказать</label></fieldset><label class="field"><span>Комментарий клиенту</span><textarea name="comment" rows="3" maxlength="1500" placeholder="Причина решения или что можно изменить"></textarea><small>При отказе укажите причину. Комментарий увидит клиент.</small></label>${field("Сумма для повторной заявки, ₽ (необязательно)", "alternativeAmount", "", { type: "number", attrs: `min="${p.min}" max="${p.max}" step="1"` })}<button class="button primary" type="submit">Сохранить и отправить фидбек ${icon("arrow")}</button></form>`}</div></div></details>`;
    })
    .join("")}</div>`;
}
