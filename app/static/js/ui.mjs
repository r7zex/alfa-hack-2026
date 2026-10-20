import { escape as e, STATUS, money, date, productById } from "./domain.mjs";
const paths = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  file: '<path d="M14 3H5v18h14V8Z"/><path d="M14 3v5h5M8 12h8M8 16h5"/>',
  user: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  exit: '<path d="M9 3H4v18h5M9 12h12m-5-5 5 5-5 5"/>',
  chart: '<path d="M5 21v-8M12 21V8M19 21V3"/>',
  gear: '<path d="m9 3-1 3-3 1v3l-2 2 2 2v3l3 1 1 3h6l1-3 3-1v-3l2-2-2-2V7l-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
  cycle:
    '<path d="M21 4v6h-6M3 20v-6h6M20 10a8 8 0 0 0-14-5M4 14a8 8 0 0 0 14 5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  shield:
    '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  history: '<path d="M3 4v6h6M3 10a9 9 0 1 1 0 5M12 7v5l3 2"/>',
  building:
    '<path d="M4 21V3h12v18M16 9h4v12M8 7h4M8 11h4M8 15h4M9 21v-3h2v3"/>',
};
export const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
export const brand = () =>
  `<a class="brand" href="#/home" aria-label="Делора - главная"><svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="12" fill="currentColor"/><path d="M12 29V12h10a8.5 8.5 0 0 1 0 17h-3v-10" fill="none" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>делора</span></a>`;
export const button = (label, action, kind = "primary", attrs = "") =>
  `<button class="button ${kind}" type="button" data-action="${action}" ${attrs}>${label}</button>`;
export const badge = (status) =>
  `<span class="badge ${e(status)}"><span class="status-dot"></span>${e(STATUS[status] || status)}</span>`;
export const heading = (title, subtitle = "", action = "") =>
  `<div class="page-heading"><div><h1>${title}</h1>${subtitle ? `<p>${subtitle}</p>` : ""}</div>${action}</div>`;
export const empty = (title, text, action = "") =>
  `<div class="empty"><span class="empty-icon">${icon("file")}</span><h3>${title}</h3><p>${text}</p>${action}</div>`;
export const field = (label, name, value = "", options = {}) =>
  `<label class="field ${options.class || ""}"><span>${label}${options.required ? ' <span class="required">*</span>' : ""}</span><input name="${name}" value="${e(value)}" type="${options.type || "text"}" ${options.required ? "required" : ""} ${options.attrs || ""}>${options.hint ? `<small>${options.hint}</small>` : ""}</label>`;
export function applicationTable(apps, users = null) {
  if (!apps.length)
    return empty(
      "Заявок пока нет",
      "Начните с выбора продукта и сохраните первую заявку.",
      button("Подобрать кредит", "navigate", "primary", 'data-to="products"'),
    );
  return `<div class="table-wrap"><table><thead><tr><th>№ заявки</th><th>${users ? "Клиент / ИНН" : "Продукт"}</th><th>Сумма</th><th>Статус</th><th>Дата подачи</th><th><span class="sr-only">Действия</span></th></tr></thead><tbody>${apps.map((a) => `<tr><td><strong class="row-id">${e(a.id)}</strong></td><td>${users ? e(users.find((u) => u.id === a.ownerId)?.name) : e(productById(a.productId).name)}${users ? `<small>${e(users.find((u) => u.id === a.ownerId)?.inn)}</small>` : ""}</td><td class="nowrap">${money(a.amount)}</td><td>${badge(a.status)}</td><td class="nowrap">${date(a.createdAt)}</td><td><a class="text-link" href="#/applications/${e(a.id)}">Открыть ${icon("arrow")}</a></td></tr>`).join("")}</tbody></table></div>`;
}
let toastTimer;
export function toast(message, error = false) {
  const el = document.getElementById("toast");
  clearTimeout(toastTimer);
  el.textContent = message;
  el.className = `toast visible ${error ? "error" : ""}`;
  toastTimer = setTimeout(() => el.classList.remove("visible"), 4500);
}
let previousFocus;
export function modal(title, content, className = "") {
  closeModal();
  previousFocus = document.activeElement;
  const dialog = document.createElement("dialog");
  dialog.id = "modal";
  dialog.className = `modal ${className}`;
  dialog.innerHTML = `<div class="modal-head"><h2>${title}</h2><button class="icon-button" type="button" data-action="close-modal" aria-label="Закрыть">${icon("close")}</button></div><div class="modal-content">${content}</div>`;
  document.body.append(dialog);
  dialog.addEventListener("close", () => {
    dialog.remove();
    previousFocus?.focus();
  });
  dialog.showModal();
  return dialog;
}
export function closeModal() {
  const el = document.getElementById("modal");
  if (el) el.close();
}
