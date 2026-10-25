import { demoAuthEnabled } from "./auth.mjs";
import { artwork, authBackground } from "./artwork.mjs";
import {
  PRODUCTS,
  productById,
  money,
  escape as e,
  documentTypes,
  validateLoan,
} from "./domain.mjs";
import {
  ownDocuments,
  ownApplications,
  currentUser,
  saveApplication,
  syncDraft,
  submitDraft,
} from "./store.mjs";
import { brand, icon, button, field, modal, closeModal, toast } from "./ui.mjs";
let authMode = "register",
  authType = "llc";
export function setAuthMode(value) {
  authMode = value;
}
export function setAuthType(value) {
  authType = value;
}
export function auth() {
  return `<main class="auth-layout"><section class="auth-story">${authBackground(authMode)}${brand()}<div class="auth-story-copy"><h1>Больше возможностей<br> для вашего дела.</h1><p>Подберите финансирование, подайте заявку<br> и получите решение в одном кабинете.</p><div class="auth-products">${PRODUCTS.map((p) => `<div>${icon(p.icon)}<span>${p.name}</span></div>`).join("")}</div></div><div class="auth-story-footer">Создано для предпринимателей <span>Демо-версия</span></div></section><section class="auth-main"><div class="auth-top"><span>Кредитный кабинет бизнеса</span>${button((demoAuthEnabled() ? "Демо: администратор " : "Вход администратора ") + icon("arrow"), "admin-login", "text")}</div><div class="auth-form-wrap"><div class="tabs auth-tabs">${[
    ["register", "Регистрация"],
    ["login", "Вход"],
  ]
    .map(
      ([id, label]) =>
        `<button class="tab ${authMode === id ? "active" : ""}" data-action="auth-mode" data-value="${id}">${label}</button>`,
    )
    .join(
      "",
    )}</div><h2>${authMode === "register" ? "Начнём с вашего бизнеса" : "С возвращением"}</h2><p class="muted">${authMode === "register" ? "Минимум данных, чтобы открыть кабинет." : "Введите почту и пароль аккаунта."}</p>${authMode === "register" ? `<div class="segmented" role="group" aria-label="Тип бизнеса">${[
    ["llc", "Юридическое лицо"],
    ["ip", "Индивидуальный предприниматель"],
  ]
    .map(
      ([id, label]) =>
        `<button type="button" class="${authType === id ? "selected" : ""}" aria-pressed="${authType === id}" data-action="auth-type" data-value="${id}">${label}</button>`,
    )
    .join(
      "",
    )}</div>` : ""}<form id="auth-form" data-mode="${authMode}" data-type="${authType}" class="form-stack">${authMode === "register" ? field(authType === "ip" ? "ФИО предпринимателя" : "Наименование организации", "name", "", { required: true, attrs: `maxlength="160" placeholder="${authType === "ip" ? "Анна Соколова" : "ООО Вектор"}"` }) : ""}${authMode === "register" ? field(`ИНН ${authType === "ip" ? "ИП (12 цифр)" : "юрлица (10 цифр)"}`, "inn", "", { required: true, attrs: `inputmode="numeric" pattern="[0-9]{${authType === "ip" ? 12 : 10}}" maxlength="${authType === "ip" ? 12 : 10}" autocomplete="off"` }) : ""}${field("Электронная почта", "email", "", { type: "email", required: true, attrs: 'maxlength="150" autocomplete="email"' })}${field("Пароль", "password", "", { type: "password", required: true, attrs: `minlength="${authMode === "register" ? 8 : 1}" maxlength="128" autocomplete="${authMode === "register" ? "new-password" : "current-password"}"` })}<p class="form-error" id="auth-error" role="alert"></p><button class="button primary full" type="submit">${authMode === "register" ? "Создать кабинет" : "Войти в кабинет"} ${icon("arrow")}</button></form><p class="footnote auth-disclaimer">Аккаунт и сессия сохраняются на сервере. Учебный сервис: используйте вымышленные сведения.</p>${demoAuthEnabled() ? `<div class="demo-divider"><span>Посмотреть без регистрации</span></div><div class="demo-buttons">${button("Демо: юрлицо", "demo-login", "secondary", 'data-id="demo-llc"')}${button("Демо: ИП", "demo-login", "secondary", 'data-id="demo-ip"')}</div>` : ""}</div><footer class="auth-footer">Делора <span>Без реальной выдачи денежных средств</span></footer></section></main>`;
}
let wizard = null;
export function startWizard(options = {}) {
  const source = options.id
    ? ownApplications().find((a) => a.id === options.id)
    : null;
  const p = productById(options.productId || source?.productId);
  wizard = {
    step: options.revise ? 0 : Math.min(3, Math.max(0, source?.currentStep ?? 0)),
    values: {
      productId: p.id,
      amount: options.amount || 1000000,
      months: options.months || 24,
      purpose: p.purpose,
      revenue: "",
      expenses: "",
      debtPayment: 0,
      documentIds: documentTypes(currentUser().type, p.id).flatMap(t => { const d = ownDocuments().find(d => d.type === t.id); return d ? [d.id] : []; }),
      mockScenario: "success",
      ...source,
    },
  };
  // Resume at upload if the server has no required attachments.
  if (source && wizard.step === 3) {
    const available = ownDocuments().filter(d => wizard.values.documentIds?.includes(d.id));
    const missing = documentTypes(currentUser().type, wizard.values.productId)
      .some(t => !available.some(d => d.type === t.id));
    if (missing) wizard.step = 2;
  }
  if (options.revise && source) {
    delete wizard.values.id;
    wizard.values.amount = source.alternativeAmount || source.amount;
    wizard.values.comment = "";
    wizard.values.documentIds = [...(source.documentIds || [])];
  }
  renderWizard();
}
export function getWizard() {
  return wizard;
}
export function captureWizard() {
  if (!wizard) return;
  const form = document.getElementById("wizard-form");
  if (!form) return;
  const data = new FormData(form);
  for (const name of [
    "productId",
    "amount",
    "months",
    "purpose",
    "revenue",
    "expenses",
    "debtPayment",
    "mockScenario",
  ])
    if (data.has(name)) wizard.values[name] = data.get(name);
  if (wizard.step === 2) wizard.values.documentIds = data.getAll("documentIds");
}
export function wizardProduct(id) {
  captureWizard();
  const p = productById(id);
  Object.assign(wizard.values, {
    productId: id,
    amount: Math.min(p.max, Math.max(p.min, +wizard.values.amount)),
    months: Math.min(p.months[1], Math.max(p.months[0], +wizard.values.months)),
    purpose: p.purpose,
  });
  renderWizard();
}
function stepContent() {
  const v = wizard.values;
  const p = productById(v.productId);
  const user = currentUser();
  if (wizard.step === 0)
    return `<h3>На что нужны средства?</h3><div class="wizard-products">${PRODUCTS.map((item) => `<button type="button" class="wizard-product ${p.id === item.id ? "selected" : ""}" data-action="wizard-product" data-id="${item.id}" aria-pressed="${p.id === item.id}">${artwork(item.id, "wizard-art")}<strong>${item.name}</strong><small>до ${money(item.max)}</small></button>`).join("")}</div><div class="form-grid">${field(p.id === "overdraft" ? "Лимит, ₽" : "Сумма кредита, ₽", "amount", v.amount, { type: "number", required: true, attrs: `min="${p.min}" max="${p.max}" step="1"` })}${field("Срок, мес.", "months", v.months, { type: "number", required: true, attrs: `min="${p.months[0]}" max="${p.months[1]}" step="1"` })}</div><label class="field"><span>Цель финансирования <span class="required">*</span></span><textarea name="purpose" required maxlength="500" rows="3">${e(v.purpose)}</textarea></label><p class="footnote">${p.rate}% годовых - демонстрационная ставка. Условия учебные.</p>`;
  if (wizard.step === 1)
    return `<h3>Профиль и финансовые показатели</h3><div class="business-preview">${icon(user.type === "ip" ? "user" : "building")}<div><strong>${e(user.name)}</strong><small>${user.type === "ip" ? "ИП" : "Юридическое лицо"} / ИНН ${e(user.inn)}</small></div></div><p class="muted">Укажите среднемесячные показатели в рублях.</p><div class="form-grid">${field("Выручка в месяц, ₽", "revenue", v.revenue, { type: "number", required: true, attrs: 'min="1" max="10000000000" step="1"' })}${field("Расходы в месяц, ₽", "expenses", v.expenses, { type: "number", required: true, attrs: 'min="0" max="10000000000" step="1"' })}</div>${field("Платежи по другим кредитам в месяц, ₽", "debtPayment", v.debtPayment, { type: "number", required: true, attrs: 'min="0" max="10000000000" step="1"' })}<label class="field"><span>Демонстрационный сценарий проверок</span><select name="mockScenario">${[["success","Источники доступны"],["missing","Нет сведений"],["negative","Негативные сведения"],["unavailable","Источник недоступен"],["malformed","Некорректный ответ"]].map(([id,label]) => `<option value="${id}" ${v.mockScenario === id ? "selected" : ""}>${label}</option>`).join("")}</select></label><p class="notice">${icon("info")}Учитываются заявленные показатели. После отправки выполняются mock-проверки и демонстрационная оценка риска.</p>`;
  if (wizard.step === 2)
    return `<h3>Приложите документы</h3><p class="muted">Выберите сохранённый файл или загрузите новый. Учебный перечень для ${user.type === "ip" ? "ИП" : "юрлица"}.</p>${documentTypes(
      user.type,
      p.id,
    )
      .map((t) => {
        const docs = ownDocuments().filter((d) => d.type === t.id);
        return `<div class="document-slot"><strong>${t.name} <span class="required">*</span></strong><small>${t.hint}</small>${docs.map((d) => `<label class="check-field document-choice"><input type="checkbox" name="documentIds" value="${e(d.id)}" ${v.documentIds.includes(d.id) ? "checked" : ""}><span>${e(d.name)}${d.demo ? " (демо)" : ""}</span></label>`).join("")}<label class="upload-label">${icon("upload")} Загрузить файл<input class="file-input" type="file" data-upload="${t.id}" data-wizard="true" accept=".pdf"></label></div>`;
      })
      .join(
        "",
      )}<p class="footnote">PDF, до 10 МБ. Сохраняются на сервере.</p>`;
  return `<h3>Проверьте заявку</h3><div class="review-product">${icon(p.icon)}<div><small>Выбранный продукт</small><strong>${p.name}</strong></div><strong>${money(v.amount)}</strong></div><dl class="details"><div><dt>Заявитель</dt><dd>${e(user.name)}</dd></div><div><dt>Тип и ИНН</dt><dd>${user.type === "ip" ? "ИП" : "Юрлицо"} / ${e(user.inn)}</dd></div><div><dt>Срок</dt><dd>${v.months} мес.</dd></div><div><dt>Цель</dt><dd>${e(v.purpose)}</dd></div><div><dt>Выручка / расходы в месяц</dt><dd>${money(v.revenue)} / ${money(v.expenses)}</dd></div><div><dt>Другие кредитные платежи</dt><dd>${money(v.debtPayment)} / мес.</dd></div><div><dt>Документов</dt><dd>${v.documentIds.length}</dd></div></dl><label class="check-field"><input name="consentData" type="checkbox" required><span>Подтверждаю, что использую синтетические данные для учебной демонстрации.</span></label><label class="check-field"><input name="consentChecks" type="checkbox" required><span>Согласен на моделируемую обработку заявки и демонстрационные проверки.</span></label><p class="footnote">Заявка появится в кабинете аналитика. Реальный кредитный запрос не отправляется.</p>`;
}
export function renderWizard() {
  const titles = ["Потребность", "Бизнес и финансы", "Документы", "Проверка"];
  const content = `<ol class="wizard-steps">${titles.map((t, i) => `<li class="${i === wizard.step ? "active" : i < wizard.step ? "done" : ""}"><span>${i < wizard.step ? icon("check") : i + 1}</span><b>${t}</b></li>`).join("")}</ol><form id="wizard-form" class="form-stack">${stepContent()}<p id="wizard-error" class="form-error" role="alert"></p><div class="wizard-footer">${button("Сохранить и закрыть", "save-draft", "text")}<div>${wizard.step ? button("Назад", "wizard-back", "secondary") : ""}<button type="submit" class="button primary">${wizard.step === 3 ? "Отправить заявку" : "Продолжить"} ${icon("arrow")}</button></div></div></form>`;
  const existing = document.querySelector("#modal .modal-content");
  if (existing) {
    existing.innerHTML = content;
    existing.scrollTop = 0;
    document.querySelector("#wizard-form input, #wizard-form button")?.focus();
  } else modal("Новая заявка", content, "wizard-modal");
}
function validateStep() {
  const v = wizard.values;
  if (wizard.step === 0)
    return validateLoan(v) || (!v.purpose.trim() ? "Укажите цель кредита" : "");
  if (wizard.step === 1)
    return !(+v.revenue > 0) || +v.expenses < 0 || +v.debtPayment < 0
      ? "Проверьте финансовые показатели"
      : "";
  if (wizard.step === 2) {
    const docs = ownDocuments().filter((d) => v.documentIds.includes(d.id));
    const missing = documentTypes(currentUser().type, v.productId).filter(
      (t) => !docs.some((d) => d.type === t.id),
    );
    return missing.length
      ? "Приложите: " + missing.map((t) => t.name.toLowerCase()).join(", ")
      : "";
  }
  return "";
}
export async function wizardBack() {
  captureWizard();
  wizard.step = Math.max(0, wizard.step - 1);
  renderWizard();
  await autoSaveWizard();
}
function showSavedApplication(id) {
  const target = "#/applications/" + id;
  if (location.hash === target) {
    // Updating an existing draft does not cause a hashchange event.
    window.dispatchEvent(new Event("delora:refresh"));
  } else location.hash = target;
}
export async function wizardNext() {
  captureWizard();
  const error = validateStep();
  if (error) {
    document.getElementById("wizard-error").textContent = error;
    return;
  }
  if (wizard.step < 3) {
    wizard.step++;
    renderWizard();
    await autoSaveWizard();
    return;
  }
  // Recheck documents on final submission; users may have reopened a draft
  // in a different browser where locally saved documents are unavailable.
  const available = ownDocuments().filter(d => wizard.values.documentIds?.includes(d.id));
  const missing = documentTypes(currentUser().type, wizard.values.productId)
    .filter(t => !available.some(d => d.type === t.id));
  if (missing.length) {
    wizard.step = 2;
    renderWizard();
    document.getElementById("wizard-error").textContent = "Приложите обязательные документы заново";
    return;
  }
  const form = document.getElementById("wizard-form");
  if (!form.reportValidity()) return;
  const id = await submitDraft(
    await autoSaveWizard(),
    {
      ...wizard.values,
      amount: +wizard.values.amount,
      months: +wizard.values.months,
      revenue: +wizard.values.revenue,
      expenses: +wizard.values.expenses,
      debtPayment: +wizard.values.debtPayment,
      consents: {
        demoData: true,
        demoChecks: true,
        at: new Date().toISOString(),
      },
    },
  );
  closeModal();
  wizard = null;
  showSavedApplication(id);
  toast("Заявка отправлена. Следите за статусом в кабинете.");
}
export async function saveDraft() {
  captureWizard();
  const id = await autoSaveWizard();
  closeModal();
  wizard = null;
  showSavedApplication(id);
  toast("Черновик сохранён");
}


let autoSaveTimer;
export function scheduleWizardAutoSave() {
  if (!wizard || wizard.step === 3) return;
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => {
    autoSaveWizard().catch(error => toast(`Не удалось синхронизировать черновик: ${error.message}`, true));
  }, 900);
}
export async function autoSaveWizard() {
  clearTimeout(autoSaveTimer);
  if (!wizard) return null;
  captureWizard();
  // A partially filled first step may not be a valid loan yet; don't create
  // invalid server records. Values remain in the browser until they are valid.
  if (validateLoan(wizard.values)) {
    throw Error("Укажите корректные сумму и срок, чтобы сохранить черновик в базе");
  }
  const values = { ...wizard.values, currentStep: wizard.step };
  const localId = saveApplication(values, false);
  const id = await syncDraft(localId);
  if (wizard && (wizard.values.id === localId || !wizard.values.id)) wizard.values.id = id;
  return id;
}
