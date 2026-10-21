// Browser storage can be unavailable even when JavaScript itself is enabled.
let temporaryStorage = false;
export function storageIsTemporary() {
  return temporaryStorage;
}
export function safeStorage(resolveBackend) {
  const memory = new Map();
  let blocked = false;
  function call(method, key, value) {
    if (!blocked) {
      try {
        const result = resolveBackend()[method](key, value);
        if (method === "getItem") {
          if (result !== null) memory.set(key, result);
          else memory.delete(key);
        } else if (method === "setItem") memory.set(key, String(value));
        else memory.delete(key);
        return result;
      } catch {
        blocked = true;
        temporaryStorage = true;
      }
    }
    if (method === "setItem") memory.set(key, String(value));
    if (method === "removeItem") memory.delete(key);
    return method === "getItem" ? (memory.get(key) ?? null) : undefined;
  }
  return {
    getItem: (key) => call("getItem", key),
    setItem: (key, value) => call("setItem", key, value),
    removeItem: (key) => call("removeItem", key),
  };
}
export const localData = safeStorage(() => globalThis.localStorage);
export const sessionData = safeStorage(() => globalThis.sessionStorage);
export function cloneData(value) {
  return typeof globalThis.structuredClone === "function"
    ? globalThis.structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}
export function makeId() {
  if (typeof globalThis.crypto?.randomUUID === "function")
    return globalThis.crypto.randomUUID();
  if (typeof globalThis.crypto?.getRandomValues !== "function")
    throw Error(
      "Браузер не поддерживает создание идентификаторов. Откройте сайт в актуальном браузере через localhost.",
    );
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((n) => n.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
