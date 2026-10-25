import { escape as e } from "./domain.mjs";
import { icon } from "./ui.mjs";
import { apiRequest } from "./auth.mjs";
import { makeId } from "./runtime.mjs";

export const MAX_MESSAGE_LENGTH = 2000;

const questions = [
  {
    id: "products",
    question: "Какой кредит выбрать?",
    description: "Разобраться в видах финансирования",
    icon: "search",
  },
  {
    id: "documents",
    question: "Какие документы понадобятся?",
    description: "Узнать, где посмотреть список",
    icon: "file",
  },
  {
    id: "application",
    question: "Как подать заявку?",
    description: "Пройти путь от выбора до отправки",
    icon: "plus",
  },
  {
    id: "status",
    question: "Где проверить статус заявки?",
    description: "Найти решение и комментарий",
    icon: "clock",
  },
];

// Cached UI state is account-scoped. The server is the source of chat history.
const conversations = new Map();
const safeLinks = new Set(["#/products", "#/applications", "#/profile?documents"]);

function conversation(userId) {
  if (!conversations.has(userId)) conversations.set(userId, {
    messages: [], draft: "", revision: 0, loaded: false, loading: false,
    sending: false, busy: false, available: false, error: "", pending: null, timer: null,
  });
  return conversations.get(userId);
}

export function clearAssistant() {
  for (const state of conversations.values()) clearTimeout(state.timer);
  conversations.clear();
}

function messageHtml(message) {
  const fromAssistant = message.role === "assistant";
  const links = (message.links || []).filter(link => safeLinks.has(link.href));
  return `<article class="assistant-message ${fromAssistant ? "from-assistant" : "from-user"}" aria-label="${fromAssistant ? "Ответ ассистента" : "Ваше сообщение"}">
    <span class="assistant-avatar" aria-hidden="true">${icon(fromAssistant ? "chat" : "user")}</span>
    <div class="assistant-message-content"><div class="assistant-message-author">${fromAssistant ? `ИИ-ассистент <span>${message.refused ? "Ограничение темы" : "Qwen"}</span>` : "Вы"}</div>
    <div class="assistant-bubble"><p>${e(message.text)}</p>${links.map(link => `<a class="text-link" href="${e(link.href)}">${e(link.label)} ${icon("arrow")}</a>`).join("")}</div></div>
  </article>`;
}

function adopt(state, data) {
  state.messages = data.messages;
  if (state.pending && data.messages.some(message => message.id === state.pending.request_id + ":user")) {
    state.pending = null;
    state.error = "";
  }
  state.revision = data.revision;
  state.available = data.available;
  state.busy = data.busy;
  state.loaded = true;
}

function refresh(userId, state) {
  if (conversations.get(userId) === state)
    window.dispatchEvent(new Event("delora:refresh"));
}

async function load(userId, state) {
  if (state.loading || state.sending) return;
  state.loading = true;
  state.error = "";
  try {
    const data = await apiRequest("/api/assistant/conversation");
    if (conversations.get(userId) !== state) return;
    adopt(state, data);
    if (state.busy) {
      clearTimeout(state.timer);
      state.timer = setTimeout(() => load(userId, state), 2500);
    }
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    refresh(userId, state);
  }
}

export function assistant(userId) {
  const state = conversation(userId);
  const waiting = state.sending || state.busy;
  const hasMessages = state.messages.length > 0 || state.pending;
  const ready = state.loaded && state.available && !waiting && !state.loading;
  return `<section class="assistant-page" aria-labelledby="assistant-title">
    <div class="page-heading"><div><h1 id="assistant-title">ИИ-ассистент</h1><p>Вопросы о кредитах, платежах, документах и заявках.</p></div></div>
    <div class="assistant-chat">
      <header class="assistant-chat-header"><div class="assistant-chat-identity"><span class="assistant-avatar" aria-hidden="true">${icon("chat")}</span><div><h2>Помощник по кредитованию</h2><span class="assistant-demo-label">Qwen - только кредитная тема</span></div></div>
      <button id="assistant-reset" class="button secondary" type="button" ${ready && (hasMessages || state.draft) ? "" : "disabled"}>${icon("plus")}<span>Новый диалог</span></button></header>
      <div class="assistant-body" id="assistant-body" aria-busy="${waiting || state.loading}">
        ${!state.loaded && !state.error ? '<p class="assistant-loading" role="status">Загружаем переписку...</p>' : ""}
        <div class="assistant-welcome" id="assistant-welcome" ${hasMessages || !state.loaded ? "hidden" : ""}><span class="assistant-welcome-icon" aria-hidden="true">${icon("chat")}</span><h2>С чего начнём?</h2><p>Помогу разобраться с кредитами.<br>Выберите вопрос или напишите свой.</p>
          <div class="assistant-suggestions">${questions.map(q => `<button class="assistant-suggestion" type="button" data-assistant-question="${q.id}" ${ready ? "" : "disabled"}>${icon(q.icon)}<span><strong>${q.question}</strong><small>${q.description}</small></span>${icon("arrow")}</button>`).join("")}</div>
        </div>
        <div class="assistant-log" id="assistant-log" role="log" aria-label="История переписки" aria-live="polite" aria-relevant="additions" ${hasMessages ? "" : "hidden"}>${state.messages.map(messageHtml).join("")}${state.pending ? messageHtml({role: "user", text: state.pending.message}) : ""}</div>
        ${waiting ? '<p class="assistant-loading" role="status">Qwen готовит и проверяет ответ...</p>' : ""}
      </div>
      <div class="assistant-compose">
        ${state.error ? `<div class="assistant-error" role="alert"><p>${e(state.error)}</p><button id="assistant-retry" class="button secondary" type="button">${state.pending ? "Повторить отправку" : "Обновить переписку"}</button>${state.pending ? '<button id="assistant-edit" class="button text" type="button">Изменить вопрос</button>' : ""}</div>` : ""}
        ${state.loaded && !state.available ? '<p class="assistant-error" role="status">Ассистент временно недоступен. Повторите позже.</p>' : ""}
        <form id="assistant-form"><label class="sr-only" for="assistant-message">Сообщение ассистенту</label><textarea id="assistant-message" name="message" rows="2" maxlength="${MAX_MESSAGE_LENGTH}" placeholder="Задайте вопрос о кредите..." aria-describedby="assistant-input-hint assistant-counter" ${ready && !state.pending ? "" : "disabled"} required>${e(state.draft)}</textarea><button class="button primary assistant-send" type="submit" aria-label="Отправить сообщение" ${ready && !state.pending && state.draft.trim() ? "" : "disabled"}>${icon("send")}</button></form>
        <div class="assistant-compose-meta"><span id="assistant-input-hint">Enter - отправить, Shift+Enter - новая строка</span><span id="assistant-counter">${state.draft.length}/${MAX_MESSAGE_LENGTH}</span></div>
        <p class="assistant-disclaimer">Переписка сохраняется в вашем аккаунте. Ответы справочные; решение по кредиту принимает банк. Условия продуктов демонстрационные.</p>
      </div>
    </div>
  </section>`;
}

export function mountAssistant(userId) {
  const form = document.getElementById("assistant-form");
  if (!form) return;
  const state = conversation(userId);
  const input = form.elements.message;
  const send = form.querySelector('[type="submit"]');
  const reset = document.getElementById("assistant-reset");
  const body = document.getElementById("assistant-body");
  input.value = state.draft;

  function syncInput() {
    state.draft = input.value.slice(0, MAX_MESSAGE_LENGTH);
    send.disabled = !state.loaded || !state.available || state.loading || state.sending || state.busy || Boolean(state.pending) || !state.draft.trim();
    reset.disabled = !state.loaded || state.loading || state.sending || state.busy || !(state.messages.length || state.draft || state.pending);
    document.getElementById("assistant-counter").textContent = `${state.draft.length}/${MAX_MESSAGE_LENGTH}`;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 152)}px`;
  }

  async function submit(text, retry = false) {
    const value = text.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!value || state.sending || state.busy || !state.loaded || !state.available || (!retry && state.pending)) return;
    if (!retry) state.pending = {message: value, request_id: makeId(), revision: state.revision};
    state.draft = "";
    state.error = "";
    state.sending = true;
    refresh(userId, state);
    try {
      const data = await apiRequest("/api/assistant/messages", {method: "POST", body: state.pending});
      if (conversations.get(userId) !== state) return;
      adopt(state, data);
      state.pending = null;
    } catch (error) {
      state.error = error.message;
      if (error.status === 409) {
        try {
          const data = await apiRequest("/api/assistant/conversation");
          if (conversations.get(userId) !== state) return;
          if (data.revision !== state.revision) state.pending = null;
          adopt(state, data);
          if (state.busy) state.timer = setTimeout(() => load(userId, state), 2500);
        } catch { /* Keep the original actionable error. */ }
      }
    } finally {
      state.sending = false;
      refresh(userId, state);
      if (conversations.get(userId) === state) document.getElementById("assistant-message")?.focus();
    }
  }

  form.addEventListener("submit", event => { event.preventDefault(); submit(input.value); });
  input.addEventListener("input", syncInput);
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!send.disabled) form.requestSubmit();
    }
  });
  document.getElementById("assistant-welcome").addEventListener("click", event => {
    const question = questions.find(q => q.id === event.target.closest("[data-assistant-question]")?.dataset.assistantQuestion);
    if (question) submit(question.question);
  });
  document.getElementById("assistant-retry")?.addEventListener("click", () => {
    if (state.pending) submit(state.pending.message, true);
    else load(userId, state);
  });
  document.getElementById("assistant-edit")?.addEventListener("click", () => {
    state.draft = state.pending?.message || "";
    state.pending = null;
    state.error = "";
    refresh(userId, state);
    document.getElementById("assistant-message")?.focus();
  });
  reset.addEventListener("click", async () => {
    if (state.sending || state.busy || state.loading) return;
    state.sending = true;
    state.error = "";
    refresh(userId, state);
    try {
      const data = await apiRequest("/api/assistant/reset", {method: "POST", body: {revision: state.revision}});
      if (conversations.get(userId) !== state) return;
      adopt(state, data);
      state.draft = "";
      state.pending = null;
    } catch (error) { state.error = error.message; }
    finally {
      state.sending = false;
      refresh(userId, state);
    }
  });
  syncInput();
  if (state.messages.length || state.pending) body.scrollTop = body.scrollHeight;
  if (!state.loaded && !state.loading && !state.error) load(userId, state);
}
