// Server authentication. Session credentials stay in the HttpOnly cookie.
let csrfToken = "";
let demoEnabled = false;
let onUser = () => {};

export const demoAuthEnabled = () => demoEnabled;
export function onAuthChange(callback) { onUser = callback; }

export async function apiRequest(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
    ...(body ? { body: body instanceof FormData ? body : JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") {
      csrfToken = "";
      onUser(null);
      globalThis.dispatchEvent?.(new Event("delora:refresh"));
    }
    const data = await response.json().catch(() => ({}));
    const message = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(". ")
      : data.detail;
    const error = Error((typeof message === "object" ? message.message || JSON.stringify(message) : message) || "Не удалось выполнить запрос");
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.headers?.get("content-type")?.includes("application/pdf") ? response.blob() : response.json();
}

export function authRequest(path, options) { return apiRequest("/api/auth" + path, options); }

export async function restoreAuth() {
  const config = await authRequest("/config");
  demoEnabled = config.demo_auth_enabled;
  try {
    const user = await authRequest("/me");
    csrfToken = (await authRequest("/csrf")).csrf_token;
    onUser(user);
  } catch (error) {
    if (error.status !== 401) throw error;
    onUser(null);
  }
}

export async function signIn(mode, data) {
  const result = await authRequest(mode === "register" ? "/register" : "/login", {
    method: "POST", body: data,
  });
  csrfToken = result.csrf_token;
  onUser(result.user);
  return result.user;
}

export async function demoSignIn(account) {
  const result = await authRequest("/demo", { method: "POST", body: { account } });
  csrfToken = result.csrf_token;
  onUser(result.user);
  return result.user;
}

export async function signOut(all = false) {
  try {
    await authRequest(all ? "/logout-all" : "/logout", { method: "POST" });
  } catch (error) {
    if (error.status !== 401) throw error;
  }
  csrfToken = "";
  onUser(null);
}

export async function saveProfile(data) {
  const user = await authRequest("/profile", { method: "PATCH", body: data });
  onUser(user);
}

export async function changePassword(data) {
  await authRequest("/password", { method: "POST", body: data });
  csrfToken = "";
  onUser(null);
}

export async function scenarioSignIn(key){
  const result=await apiRequest("/api/demo/login",{method:"POST",body:{key}});
  csrfToken=result.csrf_token;onUser(result.user);return result.user;
}
