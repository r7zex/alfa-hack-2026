import {
  productById,
  validateInn,
  validateLoan,
  escape as e,
} from "./js/domain.mjs";
import {
  getState,
  currentUser,
  session,
  useServerAuth,
  invalidate,
  ownApplications,
  addDocument,
  readDocument,
  acceptOffer,
  restoreServerApplications,
} from "./js/store.mjs";
import { brand, icon, button, toast, closeModal } from "./js/ui.mjs";
import {
  home,
  products,
  productDetail,
  calculationHtml,
  applications,
  applicationDetail,
  profile,
} from "./js/client.mjs";
import {
  auth,
  setAuthMode,
  setAuthType,
  startWizard,
  getWizard,
  captureWizard,
  renderWizard,
  wizardProduct,
  wizardBack,
  wizardNext,
  saveDraft,
  scheduleWizardAutoSave,
  autoSaveWizard,
} from "./js/forms.mjs";
import { analyst, loadAnalyst, resetAnalyst, changeAnalystFilter, sendAnalystDecision, analystPendingCount } from "./js/analyst.mjs";
import { storageIsTemporary } from "./js/runtime.mjs";

import { restoreAuth, onAuthChange, signIn, demoSignIn, signOut, saveProfile, changePassword, demoAuthEnabled } from "./js/auth.mjs";
onAuthChange(useServerAuth);
useServerAuth(null);

const root = document.getElementById("app");
function showStorageNotice() {
  if (!storageIsTemporary()) return;
  const target = root.querySelector(".auth-form-wrap, .main-content");
  if (!target) return;
  const notice = document.createElement("p");
  notice.className = "notice storage-notice";
  notice.textContent =
    "Временный режим: браузер не разрешил сохранить данные. Изменения будут доступны до обновления страницы.";
  target.prepend(notice);
}
function route() {
  const [path, query = ""] = (
    location.hash.replace(/^#\/?/, "") || "home"
  ).split("?");
  return { parts: path.split("/"), params: new URLSearchParams(query) };
}
function navItem(id, label, image, active, count = "") {
  return `<a href="#/${id}" class="nav-item ${active ? "active" : ""}" ${active ? 'aria-current="page"' : ""}>${icon(image)}<span>${label}</span>${count ? `<b>${count}</b>` : ""}</a>`;
}
function shell(content, user, section, admin) {
  const count = admin
    ? analystPendingCount()
    : ownApplications().length;
  return `<a class="skip-link" href="#main-content" data-action="skip-content">Перейти к содержимому</a><div class="app-shell"><aside class="sidebar">${brand()}<nav aria-label="Основная навигация">${admin ? navItem("current", "Текущие заявки", "file", section === "current", count) + navItem("history", "История заявок", "history", section === "history") : navItem("home", "Главная", "home", section === "home") + navItem("products", "Подбор кредита", "search", section === "products") + navItem("applications", "Мои заявки", "file", section === "applications", count) + navItem("profile", "Личный кабинет", "user", section === "profile")}</nav><div class="sidebar-footer"><div class="demo-note"><span class="demo-dot"></span>Демо-версия сервиса<small>Синтетические данные</small></div>${button(icon("exit") + " Выйти", "logout", "text")}</div></aside><div class="workspace"><header class="topbar"><span>${admin ? "Рабочее место аналитика" : "Кабинет предпринимателя"}</span><div class="topbar-account">${admin ? `<span class="analyst-label">${icon("shield")} Кредитный аналитик</span>` : `<a href="#/profile">${icon(user.type === "ip" ? "user" : "building")}<strong>${e(user.name)}</strong>${icon("chevron")}</a>`}${button(icon("exit"), "logout", "icon-button mobile-logout", 'aria-label="Выйти"')}</div></header><main id="main-content" class="main-content" tabindex="-1">${content}</main></div></div>`;
}
function render() {
  try {
    getState();
    const signed = session();
    const admin = signed?.id === "admin";
    const user = currentUser();
    if (!admin && !user) {
      root.innerHTML = auth();
      document.title = "Делора - вход в кабинет";
      showStorageNotice();
      return;
    }
    const { parts, params } = route();
    let section = parts[0];
    let content;
    if (admin) {
      section = section === "history" ? "history" : "current";
      changeAnalystFilter("status", section === "history" ? "all" : "pending");
      content = analyst(section === "history");
    } else if (section === "products")
      content = parts[1] ? productDetail(parts[1], user) : products();
    else if (section === "applications")
      content = parts[1]
        ? applicationDetail(parts[1])
        : applications(params.get("status") || "all");
    else if (section === "profile") content = profile(user);
    else {
      section = "home";
      content = home(user);
    }
    root.innerHTML = shell(content, user, section, admin);
    showStorageNotice();
    document.title =
      "Делора - " +
      {
        home: "Главная",
        products: "Подбор кредита",
        applications: "Мои заявки",
        profile: "Личный кабинет",
        current: "Текущие заявки",
        history: "История заявок",
      }[section];
    if (document.getElementById("calculator")) calculate();
    if (section === "profile" && params.has("documents"))
      document.getElementById("documents")?.scrollIntoView({ block: "start" });
  } catch (error) {
    root.innerHTML = `<main class="startup-screen"><h1>Не удалось открыть кабинет</h1><p>При запуске возникла ошибка. Обновите страницу сочетанием Ctrl+F5.</p><details><summary>Подробности ошибки</summary><pre>${e(error.message)}</pre></details><button class="button primary" data-action="reload">Обновить</button></main>`;
    toast(error.message, true);
  }
}
function navigate(to) {
  if (location.hash === "#/" + to) render();
  else location.hash = "/" + to;
}
function enter(user) {
  navigate(user.role === "admin" ? "current" : "home");
  if (user.role === "admin") {
    changeAnalystFilter("status", route().parts[0] === "history" ? "all" : "pending");
    loadAnalyst().then(render).catch(error => toast(`Заявки аналитика недоступны: ${error.message}`, true));
  }
  else restoreServerApplications().then(render).catch(error => toast(`Серверные заявки недоступны: ${error.message}`, true));
}
async function download(id) {
  const doc = getState().documents.find((d) => d.id === id);
  const file = await readDocument(id);
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = doc.demo ? doc.name.replace(/\.pdf$/, ".txt") : doc.name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const { action, id, value, to } = target.dataset;
  try {
    if (action === "skip-content") {
      event.preventDefault();
      document.getElementById("main-content")?.focus();
    } else if (action === "navigate") navigate(to);
    else if (action === "reload") location.reload();
    else if (action === "auth-mode") {
      setAuthMode(value);
      render();
    } else if (action === "auth-type") {
      setAuthType(value);
      render();
    } else if (action === "demo-login") enter(await demoSignIn(id === "demo-ip" ? "ip" : "llc"));
    else if (action === "admin-login") {
      if (demoAuthEnabled()) enter(await demoSignIn("admin"));
      else { setAuthMode("login"); render(); }
    }
    else if (action === "logout" || action === "logout-all") {
      closeModal();
      await signOut(action === "logout-all");
      resetAnalyst();
      navigate("home");
    } else if (action === "analyst-refresh") { await loadAnalyst(); render(); }
    else if (action === "new-application") startWizard();
    else if (action === "close-modal") { if (getWizard()) await autoSaveWizard(); closeModal(); }
    else if (action === "wizard-product") { wizardProduct(id); scheduleWizardAutoSave(); }
    else if (action === "wizard-back") await wizardBack();
    else if (action === "save-draft") await saveDraft();
    else if (action === "edit-application") startWizard({ id });
    else if (action === "revise-application") startWizard({ id, revise: true });
    else if (action === "download-document") await download(id);
    else if (action === "accept-offer") {
      acceptOffer(id);
      render();
      toast("Условия приняты. Учебный сценарий завершён.");
    }
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  try {
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form));
    if (form.id === "auth-form") {
      const mode = form.dataset.mode;
      const payload = { email: data.email.trim().toLowerCase(), password: data.password };
      if (mode === "register") {
        const error = validateInn(data.inn.trim(), form.dataset.type);
        if (error) throw Error(error);
        Object.assign(payload, { type: form.dataset.type, inn: data.inn.trim(), name: data.name.trim() });
      }
      form.querySelector('[type="submit"]').disabled = true;
      const user = await signIn(mode, payload);
      enter(user);
      if (mode === "register") toast("Кабинет создан");
    } else if (form.id === "calculator") {
      const productId = form.dataset.product;
      const error = validateLoan({ ...data, productId });
      if (error) throw Error(error);
      startWizard({ productId, amount: +data.amount, months: +data.months });
    } else if (form.id === "wizard-form") await wizardNext();
    else if (form.id === "profile-form") {
      if (!data.name.trim() || !data.contact.trim())
        throw Error("Заполните название и контактное лицо");
      await saveProfile({
        name: data.name.trim(), contact: data.contact.trim(),
        ogrn: data.ogrn, kpp: data.kpp || "", okved: data.okved,
        registration: data.registration || null, address: data.address, phone: data.phone,
      });
      render();
      toast("Изменения сохранены");
    } else if (form.id === "password-form") {
      if (data.new_password !== data.confirm_password) throw Error("Пароли не совпадают");
      await changePassword({ current_password: data.current_password, new_password: data.new_password });
      render();
      toast("Пароль изменен. Войдите заново.");
    } else if (form.matches(".decision-form")) {
      if (data.status === "rejected" && !data.comment.trim())
        throw Error("При отказе укажите причину в комментарии");
      await sendAnalystDecision(form.dataset.id, {
        status: data.status,
        comment: data.comment.trim(),
        alternativeAmount: data.alternativeAmount ? +data.alternativeAmount : null,
      });
      render();
      toast("Решение сохранено. Клиент видит обратную связь.");
    }
  } catch (error) {
    if (form.id === "auth-form")
      document.getElementById("auth-error").textContent = error.message;
    else if (form.id === "wizard-form")
      document.getElementById("wizard-error").textContent = error.message;
    else toast(error.message, true);
  } finally {
    if (form.id === "auth-form" && form.isConnected) form.querySelector('[type="submit"]').disabled = false;
  }
});
function calculate() {
  const form = document.getElementById("calculator");
  const p = productById(form.dataset.product);
  const data = Object.fromEntries(new FormData(form));
  const error =
    validateLoan({ ...data, productId: p.id }) ||
    (data.days &&
    (!Number.isInteger(+data.days) || +data.days < 1 || +data.days > 365)
      ? "Укажите от 1 до 365 дней"
      : "");
  document.getElementById("calculation").innerHTML = error
    ? `<p class="form-error">${e(error)}</p>`
    : calculationHtml(p, +data.amount, +data.months, +(data.days || 30));
}
let analystSearchTimer;
document.addEventListener("input", (event) => {
  const input = event.target;
  if (input.closest("#calculator")) {
    const form = input.form;
    if (input.name === "amountRange") form.elements.amount.value = input.value;
    if (input.name === "amount") form.elements.amountRange.value = input.value;
    calculate();
  }
  if (input.matches("[data-analyst-search]")) {
    clearTimeout(analystSearchTimer);
    analystSearchTimer = setTimeout(async () => {
      changeAnalystFilter("query", input.value);
      try { await loadAnalyst(); render(); }
      catch (error) { toast(error.message, true); }
    }, 350);
  }
  if (input.closest("#wizard-form")) scheduleWizardAutoSave();
  if (input.closest(".decision-form") && input.name === "status")
    input.form.elements.comment.required = input.value === "rejected";
});
document.addEventListener("change", async (event) => {
  const input = event.target;
  if (input.closest("#wizard-form") && !input.matches("[data-upload]")) scheduleWizardAutoSave();
  if (input.matches("[data-analyst-filter]")) {
    changeAnalystFilter(input.dataset.analystFilter, input.value);
    try { await loadAnalyst(); render(); }
    catch (error) { toast(error.message, true); }
    return;
  }
  if (!input.matches("[data-upload]") || !input.files?.[0]) return;
  input.disabled = true;
  try {
    if (input.dataset.wizard) captureWizard();
    const doc = await addDocument(input.files[0], input.dataset.upload);
    if (
      input.dataset.wizard &&
      getWizard() &&
      document.getElementById("wizard-form")
    ) {
      getWizard().values.documentIds.push(doc.id);
      renderWizard();
      scheduleWizardAutoSave();
    } else render();
    toast("Документ сохранён в браузере");
  } catch (error) {
    toast(error.message, true);
    input.disabled = false;
    input.value = "";
  }
});
window.addEventListener("delora:refresh", render);
window.addEventListener("hashchange", () => {
  if (session()?.id === "admin") {
    changeAnalystFilter("status", route().parts[0] === "history" ? "all" : "pending");
    loadAnalyst().then(render).catch(error => toast(error.message, true));
  } else render();
  if (!route().params.has("documents")) window.scrollTo({ top: 0 });
});
window.addEventListener("storage", (event) => {
  if (event.key === "delora.demo.v1") {
    invalidate();
    render();
  }
});
restoreAuth().then(async () => {
  render();
  if (session()?.id === "admin") {
    changeAnalystFilter("status", route().parts[0] === "history" ? "all" : "pending");
    try { await loadAnalyst(); render(); }
    catch (error) { toast(`Заявки аналитика недоступны: ${error.message}`, true); }
  } else if (session()?.id) {
    try { await restoreServerApplications(); render(); }
    catch (error) { toast(`Серверные заявки недоступны: ${error.message}`, true); }
  }
}).catch((error) => {
  root.innerHTML = `<main class="startup-screen"><h1>Не удалось проверить вход</h1><p>${e(error.message)}</p><button class="button primary" data-action="reload">Повторить</button></main>`;
});
