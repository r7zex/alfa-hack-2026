import { escape as e } from "./domain.mjs";
import { icon } from "./ui.mjs";

export const MAX_MESSAGE_LENGTH = 2000;

const questions = [
  {
    id: "products",
    question: "Какой кредит выбрать?",
    description: "Разобраться в видах финансирования",
    icon: "search",
    answer: "В кабинете есть кредит на оборотные расходы, кредит на оборудование и овердрафт. В разделе подбора можно сравнить их условия и рассчитать платёж. Это пример ответа: персональная рекомендация пока недоступна.",
    link: ["Подбор кредита", "#/products"],
  },
  {
    id: "documents",
    question: "Какие документы понадобятся?",
    description: "Узнать, где посмотреть список",
    icon: "file",
    answer: "Список документов можно посмотреть на странице выбранного кредита. Он зависит от типа бизнеса и продукта. Загруженные документы находятся в личном кабинете. Это демонстрационная подсказка, без проверки ваших файлов.",
    link: ["Мои документы", "#/profile?documents"],
  },
  {
    id: "application",
    question: "Как подать заявку?",
    description: "Пройти путь от выбора до отправки",
    icon: "plus",
    answer: "Выберите кредит в разделе подбора, укажите сумму и срок, затем нажмите кнопку подачи заявки. Заполните сведения о бизнесе и документы, проверьте данные перед отправкой. Незавершённую заявку можно продолжить из черновиков.",
    link: ["Выбрать кредит", "#/products"],
  },
  {
    id: "status",
    question: "Где проверить статус заявки?",
    description: "Найти решение и комментарий",
    icon: "clock",
    answer: "Откройте раздел с вашими заявками и выберите нужную. В карточке отображаются статус и история заявки. Это пример ответа: сам ассистент пока не получает сведения о ваших заявках.",
    link: ["Мои заявки", "#/applications"],
  },
];

// Frontend-only state. No messages are persisted or sent to an API.
const conversations = new Map();

function conversation(userId) {
  if (!conversations.has(userId))
    conversations.set(userId, { messages: [], draft: "" });
  return conversations.get(userId);
}

export function clearAssistant() {
  conversations.clear();
}

function messageHtml(message) {
  const assistant = message.role === "assistant";
  return `<article class="assistant-message ${assistant ? "from-assistant" : "from-user"}" aria-label="${assistant ? "Ответ ассистента" : "Ваше сообщение"}">
    <span class="assistant-avatar" aria-hidden="true">${icon(assistant ? "chat" : "user")}</span>
    <div class="assistant-message-content"><div class="assistant-message-author">${assistant ? 'ИИ-ассистент <span>Демо-ответ</span>' : "Вы"}</div>
    <div class="assistant-bubble"><p>${e(message.text)}</p>${message.link ? `<a class="text-link" href="${e(message.link[1])}">${e(message.link[0])} ${icon("arrow")}</a>` : ""}</div></div>
  </article>`;
}

export function assistant(userId) {
  const state = conversation(userId);
  const hasMessages = state.messages.length > 0;
  return `<section class="assistant-page" aria-labelledby="assistant-title">
    <div class="page-heading"><div><h1 id="assistant-title">ИИ-ассистент</h1><p>Вопросы о кредитах, документах и работе кабинета.</p></div></div>
    <div class="assistant-chat">
      <header class="assistant-chat-header"><div class="assistant-chat-identity"><span class="assistant-avatar" aria-hidden="true">${icon("chat")}</span><div><h2>Помощник по кабинету</h2><span class="assistant-demo-label">Демо-режим</span></div></div>
      <button id="assistant-reset" class="button secondary" type="button" ${hasMessages || state.draft ? "" : "disabled"}>${icon("plus")}<span>Новый диалог</span></button></header>
      <div class="assistant-body" id="assistant-body">
        <div class="assistant-welcome" id="assistant-welcome" ${hasMessages ? "hidden" : ""}><span class="assistant-welcome-icon" aria-hidden="true">${icon("chat")}</span><h2>С чего начнём?</h2><p>Выберите вопрос или напишите свой.<br>Сейчас доступны демонстрационные ответы.</p>
          <div class="assistant-suggestions">${questions.map((q) => `<button class="assistant-suggestion" type="button" data-assistant-question="${q.id}">${icon(q.icon)}<span><strong>${q.question}</strong><small>${q.description}</small></span>${icon("arrow")}</button>`).join("")}</div>
        </div>
        <div class="assistant-log" id="assistant-log" role="log" aria-label="История переписки" aria-live="polite" aria-relevant="additions" ${hasMessages ? "" : "hidden"}>${state.messages.map(messageHtml).join("")}</div>
      </div>
      <div class="assistant-compose"><form id="assistant-form"><label class="sr-only" for="assistant-message">Сообщение ассистенту</label><textarea id="assistant-message" name="message" rows="2" maxlength="${MAX_MESSAGE_LENGTH}" placeholder="Напишите свой вопрос..." aria-describedby="assistant-input-hint assistant-counter" required>${e(state.draft)}</textarea><button class="button primary assistant-send" type="submit" aria-label="Отправить сообщение" ${state.draft.trim() ? "" : "disabled"}>${icon("send")}</button></form>
        <div class="assistant-compose-meta"><span id="assistant-input-hint">Enter - отправить, Shift+Enter - новая строка</span><span id="assistant-counter">${state.draft.length}/${MAX_MESSAGE_LENGTH}</span></div>
        <p class="assistant-disclaimer">Демо-чат. Сообщения не отправляются на сервер. История доступна до перезагрузки страницы.</p>
      </div>
    </div>
  </section>`;
}

export function mountAssistant(userId) {
  const form = document.getElementById("assistant-form");
  if (!form) return;
  const state = conversation(userId);
  const input = form.elements.message;
  input.value = state.draft;
  const send = form.querySelector('[type="submit"]');
  const reset = document.getElementById("assistant-reset");
  const log = document.getElementById("assistant-log");
  const welcome = document.getElementById("assistant-welcome");
  const body = document.getElementById("assistant-body");

  function syncInput() {
    state.draft = input.value.slice(0, MAX_MESSAGE_LENGTH);
    send.disabled = !state.draft.trim();
    reset.disabled = !state.messages.length && !state.draft;
    document.getElementById("assistant-counter").textContent = `${state.draft.length}/${MAX_MESSAGE_LENGTH}`;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 152)}px`;
  }

  function submit(text) {
    const value = text.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!value) return;
    const sample = questions.find((q) => q.question === value);
    const reply = {
      role: "assistant",
      text: sample?.answer || "Сообщение получено. Сейчас это демо-чат: ответы на произвольные вопросы пока недоступны. Можно начать новый диалог и выбрать один из примеров вопросов или перейти к подбору кредита.",
      link: sample?.link || ["Подбор кредита", "#/products"],
    };
    const message = { role: "user", text: value };
    state.messages.push(message, reply);
    welcome.hidden = true;
    log.hidden = false;
    log.insertAdjacentHTML("beforeend", messageHtml(message) + messageHtml(reply));
    input.value = "";
    syncInput();
    body.scrollTop = body.scrollHeight;
    input.focus();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(input.value);
  });
  input.addEventListener("input", syncInput);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (input.value.trim()) form.requestSubmit();
    }
  });
  welcome.addEventListener("click", (event) => {
    const question = questions.find((q) => q.id === event.target.closest("[data-assistant-question]")?.dataset.assistantQuestion);
    if (question) submit(question.question);
  });
  reset.addEventListener("click", () => {
    state.messages.length = 0;
    log.replaceChildren();
    log.hidden = true;
    welcome.hidden = false;
    input.value = "";
    syncInput();
    body.scrollTop = 0;
    input.focus();
  });
  syncInput();
  if (state.messages.length) body.scrollTop = body.scrollHeight;
}
