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
  dealAction,
  retryProcessing,
  restoreServerApplications,
} from "./js/store.mjs";
import { brand, icon, button, toast, closeModal, modal } from "./js/ui.mjs";
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
import { analyst, loadAnalyst, resetAnalyst, changeAnalystFilter, sendAnalystDecision, analystPendingCount, setAnalystView } from "./js/analyst.mjs";
import { assistant, mountAssistant, clearAssistant } from "./js/assistant.mjs";
import { apiRequest } from "./js/auth.mjs";
import { loadProducts, money, productById as lookupProduct } from "./js/domain.mjs";
import {operationsPage,loadOperations,needsOperationsLoad,invalidateOperations,clearOperations,installOperations,joinPage,setChallenge,challengeFor} from "./js/operations.mjs";
import { storageIsTemporary } from "./js/runtime.mjs";

import { restoreAuth, onAuthChange, signIn, demoSignIn, signOut, saveProfile, changePassword, demoAuthEnabled, scenarioSignIn } from "./js/auth.mjs";
onAuthChange(user => { connectLive(null); clearAssistant(); resetAnalyst(); clearOperations(); useServerAuth(user); });
useServerAuth(null);

const root = document.getElementById("app");
let renderedHash=null;
function focusedFormSelector(form){
  const base=form.id?'#'+CSS.escape(form.id):'.'+CSS.escape(form.classList[0]);
  return base+['application','task','source','id','product','operation'].filter(key=>form.dataset[key]!==undefined)
    .map(key=>`[data-${key}="${CSS.escape(form.dataset[key])}"]`).join('');
}
function showStorageNotice() {
  if (!storageIsTemporary()) return;
  const target = root.querySelector(".auth-form-wrap, .main-content");
  if (!target) return;
  const notice = document.createElement("p");
  notice.className = "notice storage-notice";
  notice.textContent =
    "Настройки интерфейса доступны до обновления страницы. Заявки и документы сохраняются на сервере.";
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
  return `<a class="skip-link" href="#main-content" data-action="skip-content">Перейти к содержимому</a><div class="app-shell"><aside class="sidebar">${brand()}<button type="button" class="button text mobile-menu" data-action="toggle-menu" aria-expanded="false">Меню</button><nav aria-label="Основная навигация">${(admin ? [["current","Очередь заявок","file"],["mine","Мои заявки","user"],["escalations","Эскалации","shield"],["history","История решений","history"],["messages","Сообщения","chat"],["notifications","Уведомления","clock"],["analytics","Аналитика","chart"],["integrations","Интеграции","cycle"],...(user.role==="admin"?[["settings","Правила","shield"],["audit","Аудит","history"]]:[])] : [["home","Главная","home"],["products","Подбор кредита","search"],["applications","Мои заявки","file"],["loans","Мои кредиты","chart"],["documents","Документы","file"],["messages","Сообщения","chat"],["notifications","Уведомления","clock"],["team","Команда","building"],["assistant","ИИ-ассистент","chat"],["profile","Личный кабинет","user"]]).map(([id,label,image])=>navItem(id,label,image,section===id)).join("")}</nav><div class="sidebar-footer"><div class="demo-note"><span class="demo-dot"></span>Демо-версия сервиса<small>Синтетические данные</small></div>${button(icon("exit") + " Выйти", "logout", "text")}</div></aside><div class="workspace"><header class="topbar"><span>${admin ? ({admin:"Администратор",underwriter:"Кредитный аналитик",approver:"Согласующий"}[user.role]) : "Кабинет предпринимателя"}</span><div class="topbar-account"><a class="notification-bell" href="#/notifications" aria-label="Уведомления">${icon("clock")}<b id="notification-count"></b></a>${admin ? `<span class="analyst-label">${icon("shield")} Кредитный аналитик</span>` : `<a href="#/profile">${icon(user.type === "ip" ? "user" : "building")}<strong>${e(user.name)}</strong>${icon("chevron")}</a>`}${button(icon("exit"), "logout", "icon-button mobile-logout", 'aria-label="Выйти"')}</div></header><main id="main-content" class="main-content" tabindex="-1">${content}</main></div></div>`;
}
function render() {
  try {
    const focused=document.activeElement,activeForm=focused?.closest('form');
    const preserve=renderedHash===location.hash&&activeForm&&root.contains(activeForm)&&!activeForm.dataset.busy&&['INPUT','TEXTAREA','SELECT'].includes(focused.tagName)
      ? {selector:focusedFormSelector(activeForm),application:activeForm.dataset.application,
         operation:activeForm.dataset.operation,version:activeForm.dataset.version,field:focused.name,values:[...new FormData(activeForm)].filter(([,v])=>typeof v==='string'),start:focused.selectionStart,end:focused.selectionEnd}:null;
    getState();
    const signed = session();
    const admin = signed?.id === "admin";
    const user = currentUser();
    if (!admin && !user) {
      root.innerHTML = route().parts[0] === "join" ? joinPage() : auth();
      document.title = "Делора - вход в кабинет";
      showStorageNotice();
      return;
    }
    const { parts, params } = route();
    let section = parts[0];
    let content;
    const extraSections=["loans","documents","messages","notifications","team","analytics","integrations","settings","audit","review"];
    if (extraSections.includes(section)) {
      content=operationsPage(section,parts[1]||"");
    } else if (admin) {
      section=["history","mine","escalations"].includes(section)?section:"current";
      setAnalystView(section);
      content=analyst(section==="history" || section==="mine" || section==="escalations");
    } else if (section === "products")
      content = parts[1] ? productDetail(parts[1], user) : products();
    else if (section === "applications")
      content = parts[1]
        ? applicationDetail(parts[1])
        : applications(params.get("status") || "all");
    else if (section === "profile") content = profile(user);
    else if (section === "assistant") content = assistant(user.id);
    else {
      section = "home";
      content = home(user);
    }
    root.innerHTML = shell(content, user, section, admin);
    renderedHash=location.hash;
    if(preserve){
      const form=root.querySelector(preserve.selector);
      if(form&&form.dataset.application===preserve.application&&form.dataset.operation===preserve.operation){
        if(preserve.version!==undefined)form.dataset.version=preserve.version;
        for(const [name,value] of preserve.values){const field=form.elements.namedItem(name);if(field&&field.type!=='file'){if(field.type==='checkbox')field.checked=true;else field.value=value;}}
        const field=form.elements.namedItem(preserve.field);field?.focus?.({preventScroll:true});
        if(field?.setSelectionRange&&preserve.start!=null){try{field.setSelectionRange(preserve.start,preserve.end);}catch{/* Numeric inputs do not expose a selection. */}}
      }
    }
    if (section === "assistant") mountAssistant(user.id);
    if(extraSections.includes(section) && section!=="documents" && needsOperationsLoad(section,parts[1]||"")) {
      const key=location.hash;
      loadOperations(section,parts[1]||"").then(()=>{if(location.hash===key)render();});
    }
    connectLive(section==="applications"?parts[1]:null);
    showStorageNotice();
    document.title =
      "Делора - " +
      {
        home: "Главная",
        loans:"Мои кредиты",documents:"Документы",messages:"Сообщения",notifications:"Уведомления",team:"Команда",analytics:"Аналитика",integrations:"Интеграции",settings:"Правила",review:"Рассмотрение",mine:"Мои заявки",escalations:"Эскалации",
        products: "Подбор кредита",
        applications: "Мои заявки",
        profile: "Личный кабинет",
        assistant: "ИИ-ассистент",
        current: "Текущие заявки",
        history: "История заявок",
      }[section] || "Делора - Кабинет";
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
    setAnalystView(route().parts[0]);
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
  link.download = doc?.name || "document.pdf";
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
    else if (action === "toggle-menu") {
      const sidebar=document.querySelector(".sidebar");sidebar.classList.toggle("menu-open");target.setAttribute("aria-expanded",sidebar.classList.contains("menu-open"));
    }
    else if(action==="operations-refresh"){await refreshOperations(true);}
    else if(action==="request-signing-code"){
      target.disabled=true;
      try{setChallenge(id,await apiRequest(`/api/applications/${id}/signing-code`,{method:"POST"}));render();}
      finally{if(target.isConnected)target.disabled=false;}
    }
    else if (action === "auth-mode") {
      setAuthMode(value);
      render();
    } else if (action === "auth-type") {
      setAuthType(value);
      render();
    } else if (action === "demo-login") enter(await demoSignIn(id === "demo-ip" ? "ip" : "llc"));
    else if(action==="demo-scenarios"){
      const rows=await apiRequest("/api/demo/scenarios");
      modal("Демонстрационные сценарии",rows.length?`<form id="demo-scenario-form" class="form-stack"><label class="field"><span>Сценарий</span><select name="key">${rows.map(r=>`<option value="${e(r.key)}">${e(r.title)}</option>`).join("")}</select></label><button class="button primary" type="submit">Открыть сценарий</button></form>`:'<p>Демонстрационные профили ещё не подготовлены. Инструкция запуска приведена в README.</p>');
    }
    else if (action === "bank-demo-login") enter(await demoSignIn(id));
    else if (action === "admin-login") {
      if (demoAuthEnabled()) enter(await demoSignIn("admin"));
      else { setAuthMode("login"); render(); }
    }
    else if (action === "logout" || action === "logout-all") {
      closeModal();
      await signOut(action === "logout-all");
      resetAnalyst();
      navigate("home");
    } else if (action === "review-legacy-approval") {
      await sendAnalystDecision(id, {status: "needs_info", expectedVersion:Number(target.dataset.version),comment: "Прежнее одобрение не содержит версии предложения. Уточните данные и документы для проверки условий."}); render();
    } else if (action === "analyst-refresh") { await loadAnalyst(); render(); }
    else if (action === "new-application") startWizard();
    else if (action === "close-modal") { if (getWizard()) await autoSaveWizard(); closeModal(); }
    else if (action === "wizard-product") { wizardProduct(id); scheduleWizardAutoSave(); }
    else if (action === "wizard-back") await wizardBack();
    else if (action === "save-draft") await saveDraft();
    else if (action === "edit-application") startWizard({ id });
    else if (action === "revise-application") startWizard({ id, revise: true });
    else if (action === "download-document") await download(id);
    else if (action === "refresh-applications") { await restoreServerApplications(); render(); }
    else if (action === "retry-processing") { await retryProcessing(id); render(); }
    else if (action === "decline-offer") { await dealAction(id, "decline"); render(); }
    else if (action === "disburse-offer") { if(!confirm("Зафиксировать демонстрационную выдачу?"))return;target.disabled=true;try{await dealAction(id,"disburse");render();}finally{if(target.isConnected)target.disabled=false;} }
    else if (action === "accept-offer") {
      await acceptOffer(id);
      render();
      toast("Условия приняты. Ознакомьтесь с демо-договором.");
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
    if(form.id==="demo-scenario-form"){const user=await scenarioSignIn(data.key);closeModal();enter(user);}
    else if (form.id === "offer-action-form") {
      if(form.dataset.busy)return;
      form.dataset.busy="true";
      form.querySelector('[type="submit"]').disabled=true;
      const challenge=challengeFor(form.dataset.id);
      try{await dealAction(form.dataset.id, form.dataset.operation, data.acknowledged === "on",form.dataset.operation==="sign"?{challenge_id:challenge?.challenge_id,code:data.code}:{});}
      finally{delete form.dataset.busy;form.querySelector('[type="submit"]').disabled=false;}
      render();
      toast(form.dataset.operation === "sign" ? "Демо-договор подписан" : "Условия приняты");
    } else if (form.id === "recommendation-form") {
      const rows = await apiRequest("/api/products/recommendations",{method:"POST",body:{purpose:data.purpose,amount:Number(data.amount),months:Number(data.months),revenue:Number(data.revenue),expenses:Number(data.expenses),debt_payment:Number(data.debt_payment)}});
      document.getElementById("recommendation-result").innerHTML = rows.length
        ? rows.map((r,i) => `<section class="feedback"><h3><a class="text-link" href="#/products/${e(r.productId)}">${i === 0 && r.eligible ? "Рекомендуем: " : ""}${e(lookupProduct(r.productId).name)}</a></h3><p>${e(r.compatibility)} · ${r.months} мес. · ${r.annual_rate}%</p><p>${r.reasons.map(e).join(". ")}</p><p>Доступная сумма ${money(r.available_amount)} · предварительный платёж ${money(r.monthly_payment)}</p></section>`).join("")
        : '<p class="form-error">Нет продукта с такой суммой и сроком. Измените параметры.</p>';
    } else if (form.id === "auth-form") {
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
        expectedVersion:Number(form.dataset.version),
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
    const applicationId = input.dataset.wizard ? await autoSaveWizard() : input.dataset.application || null;
    const doc = await addDocument(input.files[0], input.dataset.upload, applicationId);
    if (
      input.dataset.wizard &&
      getWizard() &&
      document.getElementById("wizard-form")
    ) {
      getWizard().values.documentIds.push(doc.id);
      if(getWizard().step===2)renderWizard();
      scheduleWizardAutoSave();
    } else {await restoreServerApplications();invalidateOperations();render();}
    toast("Документ сохранён на сервере");
  } catch (error) {
    toast(error.message, true);
    input.disabled = false;
    input.value = "";
  }
});
window.addEventListener("delora:refresh", render);
window.addEventListener("hashchange", () => {
  connectLive(null);
  if (session()?.id === "admin") {
    setAnalystView(route().parts[0]);
    loadAnalyst().then(render).catch(error => toast(error.message, true));
  } else if (session()?.id) {
    restoreServerApplications().then(render).catch(error => toast(error.message, true));
  } else render();
  if (!route().params.has("documents")) window.scrollTo({ top: 0 });
});
window.addEventListener("storage", (event) => {
  if (event.key === "delora.demo.v1") {
    invalidate();
    render();
  }
});
Promise.all([restoreAuth(), loadProducts()]).then(async () => {
  render();
  if (session()?.id === "admin") {
    setAnalystView(route().parts[0]);
    try { await loadAnalyst(); render(); }
    catch (error) { toast(`Заявки аналитика недоступны: ${error.message}`, true); }
  } else if (session()?.id) {
    try { await restoreServerApplications(); render(); }
    catch (error) { toast(`Серверные заявки недоступны: ${error.message}`, true); }
  }
}).catch((error) => {
  root.innerHTML = `<main class="startup-screen"><h1>Не удалось проверить вход</h1><p>${e(error.message)}</p><button class="button primary" data-action="reload">Повторить</button></main>`;
});

let live=null,liveId=null,liveVersion=-1,liveUpdating=false;
function connectLive(id){
  if(id===liveId)return;
  live?.close();live=null;liveId=id;liveVersion=-1;
  if(!id||session()?.id==="admin"||!session())return;
  live=new EventSource(`/api/applications/${encodeURIComponent(id)}/stream`);
  live.addEventListener("update",async event=>{
    const data=JSON.parse(event.data);if(data.version<=liveVersion||liveUpdating)return;
    liveVersion=data.version;liveUpdating=true;
    try{await restoreServerApplications();const focused=document.activeElement,form=focused?.closest("form");if(!form||form.dataset.busy||focused.tagName==="BUTTON")render();}
    catch(error){toast(error.message,true);}finally{liveUpdating=false;}
  });
}
async function refreshOperations(force=true){
  if(force)invalidateOperations();
  if(session()?.id&&session()?.id!=="admin")await restoreServerApplications();
  render();
}
installOperations(refreshOperations);
window.addEventListener("delora:error",event=>toast(event.detail,true));
setInterval(async()=>{
  if(!session()||document.hidden||liveUpdating)return;
  try{
    const notes=await apiRequest("/api/notifications");const counter=document.getElementById("notification-count");if(counter)counter.textContent=notes.unread||"";
    if(document.activeElement?.closest("form")||document.getElementById("modal"))return;
    const section=route().parts[0];
    if(["notifications","messages","review","integrations","analytics"].includes(section)){invalidateOperations();render();}
    else if(session()?.id==="admin"&&["current","mine","escalations","history"].includes(section)){await loadAnalyst();render();}
    else if(ownApplications().some(a=>["submitted","data_check","enrichment","scoring","decision","processing"].includes(a.status))){await restoreServerApplications();render();}
  }catch{/* Manual refresh and EventSource reconnection remain available. */}
},5000);
