import { apiRequest } from "./auth.mjs";
// Production state is restored from the API. Browser storage is only a legacy test adapter.
import { localData, sessionData, cloneData, makeId } from "./runtime.mjs";
const KEY = "delora.demo.v1";
const SESSION_KEY = "delora.session.v1";
const demoInn = (prefix, type) => {
  const d = [...prefix].map(Number);
  const add = (weights) =>
    d.push((weights.reduce((sum, w, i) => sum + w * d[i], 0) % 11) % 10);
  if (type === "ip") {
    add([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]);
    add([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]);
  } else add([2, 4, 10, 3, 5, 9, 4, 6, 8]);
  return d.join("");
};
function seed() {
  const users = [
    {
      id: "demo-llc",
      type: "llc",
      name: "ООО Ритм",
      contact: "Алексей Миронов",
      inn: demoInn("990000001", "llc"),
      email: "ritm@example.test",
      okved: "47.91",
      address: "Демонстрационный город, ул. Примерная, 1",
      registration: "2022-03-15",
      ogrn: "",
      phone: "",
    },
    {
      id: "demo-ip",
      type: "ip",
      name: "ИП Анна Соколова",
      contact: "Анна Соколова",
      inn: demoInn("9900000001", "ip"),
      email: "anna@example.test",
      okved: "56.10",
      address: "Демонстрационный город, ул. Учебная, 2",
      registration: "2023-05-20",
      ogrn: "",
      phone: "",
    },
  ];
  const now = Date.now();
  const make = (
    id,
    ownerId,
    productId,
    amount,
    months,
    status,
    age,
    comment = "",
  ) => ({
    id,
    ownerId,
    productId,
    amount,
    months,
    status,
    purpose:
      productId === "equipment"
        ? "Покупка производственного оборудования"
        : "Закупка товаров",
    revenue: 1800000,
    expenses: 950000,
    debtPayment: 90000,
    createdAt: new Date(now - age * 86400000).toISOString(),
    updatedAt: new Date(now - age * 86400000).toISOString(),
    documentIds: [],
    comment,
    history: [
      {
        text:
          status === "pending"
            ? "Заявка отправлена на рассмотрение"
            : "Решение по демонстрационной заявке",
        at: new Date(now - age * 86400000).toISOString(),
      },
    ],
  });
  return {
    version: 1,
    users,
    applications: [
      make("DL-2026-0187", "demo-llc", "equipment", 7500000, 36, "pending", 1),
      make(
        "DL-2026-0162",
        "demo-llc",
        "working",
        3000000,
        24,
        "approved",
        4,
        "Предложение одобрено на запрошенных условиях.",
      ),
      make(
        "DL-2026-0140",
        "demo-llc",
        "overdraft",
        1500000,
        6,
        "rejected",
        8,
        "Текущая долговая нагрузка велика. Можно подать новую заявку на меньший лимит.",
      ),
      make("DL-2026-0191", "demo-ip", "working", 850000, 12, "pending", 0),
      make(
        "DL-2026-0171",
        "demo-ip",
        "overdraft",
        300000,
        6,
        "approved",
        3,
        "Условия одобрены.",
      ),
    ],
    documents: [
      {
        id: "demo-statement",
        ownerId: "demo-llc",
        type: "statement",
        name: "Выписка_демо.pdf",
        size: 1024,
        demo: true,
        createdAt: new Date(now).toISOString(),
      },
      {
        id: "demo-accounts",
        ownerId: "demo-llc",
        type: "accounts",
        name: "Отчётность_демо.pdf",
        size: 1024,
        demo: true,
        createdAt: new Date(now).toISOString(),
      },
    ],
  };
}
// Autosave is a persistence detail, not a review event. Compact historic
// records created by older versions without touching submit/decision events.
export function normalizeDraftHistory(history) {
  let seenCreation = false;
  return (Array.isArray(history) ? history : []).flatMap((entry) => {
    if (!["Черновик сохранён", "Черновик создан"].includes(entry?.text)) return [entry];
    if (seenCreation) return [];
    seenCreation = true;
    return [{ ...entry, text: "Черновик создан" }];
  });
}

let state;
export function getState() {
  if (state) return state;
  if (serverAuth) return state = {version: 1, users: [], applications: [], documents: []};
  const raw = localData.getItem(KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (
        parsed.version === 1 &&
        Array.isArray(parsed.users) &&
        Array.isArray(parsed.applications) &&
        Array.isArray(parsed.documents)
      ) {
        let needsCleanup = false;
        for (const application of parsed.applications) {
          const cleaned = normalizeDraftHistory(application.history);
          if (cleaned.length !== application.history?.length ||
              application.history?.some((event) => event.text === "Черновик сохранён")) {
            application.history = cleaned;
            needsCleanup = true;
          }
        }
        if (needsCleanup) persist(parsed);
        else state = parsed;
        return state;
      }
    } catch {
      /* Recover only invalid demo data. */
    }
  }
  state = seed();
  persist(state);
  return state;
}
function persist(next) {
  if (!serverAuth) localData.setItem(KEY, JSON.stringify(next));
  state = next;
}
export function update(mutator) {
  const next = cloneData(getState());
  mutator(next);
  persist(next);
}
export function invalidate() {
  state = undefined;
}
let serverAuth = false;
let serverUser = null;
export function useServerAuth(user) {
  if (!serverAuth || serverUser?.email !== user?.email) state = {version: 1, users: [], applications: [], documents: []};
  serverAuth = true;
  serverUser = user ? {
    ...user.business,
    id: user.role === "admin" ? "admin" : user.is_demo ? "demo-" + user.business.type : "user-" + user.id,
    email: user.email,
    role: user.role,
    registration: user.business?.registration || "",
  } : null;
  // Remove the old browser-only sign-in marker during migration.
  sessionData.removeItem(SESSION_KEY);
}
export function session() {
  if (serverAuth) return serverUser ? { id: serverUser.id, role: serverUser.role } : null;
  try {
    return JSON.parse(sessionData.getItem(SESSION_KEY)) || null;
  } catch {
    return null;
  }
}
export function login(id) {
  if (serverAuth) throw Error("Используйте серверную авторизацию");
  sessionData.setItem(SESSION_KEY, JSON.stringify({ id }));
}
export function logout() {
  serverUser = null;
  sessionData.removeItem(SESSION_KEY);
}
export const currentUser = () =>
  serverAuth ? serverUser : getState().users.find((u) => u.id === session()?.id);
export const ownApplications = () =>
  getState().applications.filter((a) => a.ownerId === session()?.id);
export const ownDocuments = () =>
  getState().documents.filter((d) => d.ownerId === session()?.id);
export function saveApplication(input, submit) {
  const owner = currentUser();
  if (!owner) throw Error("Сначала войдите в кабинет");
  let id = input.id;
  update((s) => {
    const existing = s.applications.find(
      (a) => a.id === id && a.ownerId === owner.id,
    );
    if (id && !existing) throw Error("Заявка не найдена");
    if (existing && !["draft", "needs_info"].includes(existing.status))
      throw Error("Отправленная заявка недоступна для редактирования");
    id =
      existing?.id ||
      "DL-" +
        new Date().getFullYear() +
        "-" +
        makeId().slice(0, 8).toUpperCase();
    const at = new Date().toISOString();
    const value = {
      ...input,
      id,
      ownerId: owner.id,
      profile: cloneData(owner),
      status: submit ? "pending" : "draft",
      createdAt: existing?.createdAt || at,
      updatedAt: at,
      history: [
        ...normalizeDraftHistory(existing?.history),
        ...(!existing || submit ? [{
          at,
          text: submit ? "Заявка отправлена на рассмотрение" : "Черновик создан",
        }] : []),
      ],
    };
    if (existing) s.applications[s.applications.indexOf(existing)] = value;
    else s.applications.unshift(value);
  });
  return id;
}
export function decide(id, decision) {
  if (session()?.id !== "admin")
    throw Error("Доступ только для демо-аналитика");
  update((s) => {
    const app = s.applications.find((a) => a.id === id);
    if (!app || app.status !== "pending")
      throw Error("По этой заявке уже принято решение");
    if (!["approved", "rejected"].includes(decision.status))
      throw Error("Выберите решение");
    if (decision.status === "rejected" && !decision.comment?.trim())
      throw Error("Укажите причину отказа");
    Object.assign(app, decision, { updatedAt: new Date().toISOString() });
    app.history.push({
      at: app.updatedAt,
      text:
        decision.status === "approved"
          ? "Аналитик одобрил заявку"
          : "Аналитик отказал по заявке",
    });
  });
}
export function acceptOffer(id) {
  if (serverAuth) return dealAction(id, "accept", true);
  update((s) => {
    const a = s.applications.find(
      (a) => a.id === id && a.ownerId === session()?.id,
    );
    if (!a || a.status !== "approved")
      throw Error("Предложение больше не доступно");
    a.status = "completed";
    a.updatedAt = new Date().toISOString();
    a.history.push({
      at: a.updatedAt,
      text: "Клиент принял условия. Демо-сценарий завершён, деньги не выдаются.",
    });
  });
}
function database() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("delora.files.v1", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("files");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(Error("Не удалось открыть хранилище файлов"));
  });
}
async function fileOperation(mode, operation) {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("files", mode);
      const request = operation(tx.objectStore("files"));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () =>
        reject(Error("Не удалось сохранить файл. Проверьте свободное место."));
      tx.onabort = () => reject(Error("Операция с файлом прервана"));
    });
  } finally {
    db.close();
  }
}
export async function addDocument(file, type, applicationId = null) {
  if (serverAuth) {
    const data = new FormData(); data.append("file", file); data.append("document_type", type);
    const doc = await apiRequest("/api/documents" + (applicationId ? "/" + encodeURIComponent(applicationId) : ""), {method: "POST", body: data});
    const normalized = documentRow(doc, session()?.id);
    update(s => s.documents.push(normalized));
    return normalized;
  }
  if (!currentUser()) throw Error("Сначала войдите в кабинет");
  if (file.size === 0 || file.size > 10 * 1024 * 1024)
    throw Error("Выберите непустой файл размером до 10 МБ");
  const bytes = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const pdf =
    bytes[0] === 37 &&
    bytes[1] === 80 &&
    bytes[2] === 68 &&
    bytes[3] === 70 &&
    bytes[4] === 45;
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((b, i) => bytes[i] === b);
  const jpg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  if (!pdf && !png && !jpg)
    throw Error(
      "Разрешены только PDF, JPG и PNG. Содержимое файла не соответствует формату.",
    );
  const extension = file.name.split(".").pop().toLowerCase();
  if (
    !(
      (pdf && extension === "pdf") ||
      (png && extension === "png") ||
      (jpg && ["jpg", "jpeg"].includes(extension))
    )
  )
    throw Error("Расширение файла не соответствует содержимому");
  const doc = {
    id: makeId(),
    ownerId: currentUser().id,
    type,
    name: file.name,
    size: file.size,
    createdAt: new Date().toISOString(),
  };
  await fileOperation("readwrite", (s) => s.put(file, doc.id));
  try {
    update((s) => s.documents.push(doc));
  } catch (e) {
    await fileOperation("readwrite", (s) => s.delete(doc.id));
    throw e;
  }
  return doc;
}
export async function readDocument(id) {
  if (serverAuth) return apiRequest(`/api/documents/${encodeURIComponent(id)}/content`);
  const doc = getState().documents.find(
    (d) =>
      d.id === id && (d.ownerId === session()?.id || session()?.id === "admin"),
  );
  if (!doc) throw Error("Документ не найден");
  if (doc.demo)
    return new Blob(
      [
        "Синтетический документ для демонстрации интерфейса. Данные не являются банковской отчётностью.",
      ],
      { type: "text/plain;charset=utf-8" },
    );
  const file = await fileOperation("readonly", (s) => s.get(id));
  if (!file)
    throw Error("Файл отсутствует в этом браузере. Загрузите его повторно.");
  return file;
}


// Application synchronization uses the same session and CSRF token as auth.
const serverIds = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const serverOwners = ["demo-llc", "demo-ip"];
const draftsInFlight = new Map();
const queue = new Map();
const resolvedIds = new Map();
function demoOwner() {
  const owner = session()?.id;
  if (serverAuth) return serverUser?.role === "client" ? owner : null;
  return serverOwners.includes(owner) ? owner : null;
}
function perform(owner, task) {
  const prior = queue.get(owner) || Promise.resolve();
  const current = prior.catch(() => {}).then(task);
  queue.set(owner, current);
  return current;
}
async function serverRequest(owner, path, options = {}) {
  if (!owner || session()?.id !== owner) throw Error("Сессия изменилась. Войдите заново.");
  return apiRequest(path, { method: options.method, body: options.body ? JSON.parse(options.body) : undefined });
}
function payload(row) {
  const nullable = value => value === "" || value == null ? null : Number(value);
  return {
    productId: row.productId, amount: Number(row.amount), months: Number(row.months),
    purpose: row.purpose || null, revenue: nullable(row.revenue),
    expenses: nullable(row.expenses), debtPayment: nullable(row.debtPayment),
    currentStep: row.currentStep ?? 0,
    mockScenario: row.mockScenario || "success",
    documentIds: (row.documentIds || []).filter(id => serverIds.test(id)),
  };
}
export async function syncDraft(localId) {
  const owner = demoOwner();
  if (!owner) return localId;
  return perform(owner, async () => {
    const id = resolvedIds.get(localId) || localId;
    const row = getState().applications.find(a => a.id === id && a.ownerId === owner);
    if (!row || row.status !== "draft") return id;
    const known = serverIds.test(id);
    const result = await serverRequest(owner, known ? `/api/applications/${id}` : "/api/applications", {
      method: known ? "PATCH" : "POST", body: JSON.stringify(payload(row)),
    });
    if (!known) {
      resolvedIds.set(id, result.id);
      update(s => {
        const source = s.applications.find(a => a.id === id && a.ownerId === owner);
        if (source) source.id = result.id;
      });
    }
    return result.id;
  });
}
export async function submitDraft(localId, values) {
  const owner = demoOwner();
  if (!owner) return saveApplication(values, true);
  const id = await syncDraft(localId);
  await perform(owner, () => serverRequest(owner, `/api/applications/${id}/submit`, { method: "POST", body: JSON.stringify({demo_data: !!values.consents?.demoData, demo_checks: !!values.consents?.demoChecks}) }));
  await restoreServerApplications();
  return id;
}
function documentRow(doc, owner) {
  return {...doc, ownerId: owner, name: doc.filename, type: doc.document_type, createdAt: doc.created_at};
}
export async function restoreServerApplications() {
  const owner = demoOwner();
  if (!owner) return;
  const rows = await apiRequest("/api/applications");
  const [documents, flows] = await Promise.all([
    apiRequest("/api/documents"),
    Promise.all(rows.map(row => apiRequest(`/api/applications/${row.id}/workflow`))),
  ]);
  if (session()?.id !== owner) return;
  update(s => {
    s.documents = documents.map(d => documentRow(d, owner));
    s.applications = rows.map((row, i) => ({
      ...row, ownerId: owner, profile: cloneData(currentUser()), workflow: flows[i],
      documentIds: flows[i].documents.map(d => d.id),
      history: flows[i].history.filter(h => h.old_status !== h.new_status || h.reason !== "Данные заявки обновлены").map(h => ({text: h.reason, at: h.created_at})),
    }));
  });
}
export async function dealAction(id, action, acknowledged = false) {
  const app = ownApplications().find(a => a.id === id);
  const offer = app?.workflow?.offers?.at(-1);
  if (!offer) throw Error("Предложение отсутствует. Обновите заявку.");
  await apiRequest(`/api/applications/${id}/offer/${action}`, {method: "POST", body: {
    offer_id: offer.id, acknowledged, contract_sha256: offer.contract_sha256,
  }});
  await restoreServerApplications();
}
export async function retryProcessing(id) {
  await apiRequest(`/api/applications/${id}/retry`, {method: "POST", body: {mockScenario: "success"}});
  await restoreServerApplications();
}
