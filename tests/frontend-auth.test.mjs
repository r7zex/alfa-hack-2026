import { test } from "node:test";
import assert from "node:assert/strict";

const data = new Map();
globalThis.sessionStorage = {
  getItem: (key) => data.get(key) || null,
  setItem: (key, value) => data.set(key, value),
  removeItem: (key) => data.delete(key),
};

test("server identity ignores forged browser sessions and client-side role selection", async () => {
  const store = await import("../app/static/js/store.mjs");
  sessionStorage.setItem("delora.session.v1", JSON.stringify({ id: "admin" }));
  store.useServerAuth(null);
  assert.equal(store.session(), null);
  assert.equal(store.currentUser(), null);
  assert.throws(() => store.login("admin"), /серверную/);
  store.useServerAuth({ id: 7, email: "user@example.com", role: "client", is_demo: false, business: { type: "ip", name: "Test", inn: "990000000115" } });
  assert.equal(store.session().id, "user-7");
  assert.equal(store.session().role, "client");
  assert.equal(store.currentUser().name, "Test");
  store.useServerAuth(null);
  assert.equal(store.session(), null);
});

test("auth adapter restores from server, attaches CSRF and clears expired identity", async () => {
  const auth = await import("../app/static/js/auth.mjs");
  const calls = [], users = [];
  const user = { id: 7, email: "user@example.com", role: "client" };
  const responses = [
    [200, { demo_auth_enabled: false }], [200, user], [200, { csrf_token: "csrf-1" }],
    [200, { user, csrf_token: "csrf-2" }], [204, null], [401, { detail: "Войдите в кабинет" }],
  ];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    const [status, data] = responses.shift();
    return { ok: status < 400, status, json: async () => data };
  };
  auth.onAuthChange((value) => users.push(value));
  await auth.restoreAuth();
  assert.equal(auth.demoAuthEnabled(), false);
  assert.deepEqual(users.at(-1), user);
  await auth.signIn("login", { email: user.email, password: "secret" });
  await auth.signOut();
  assert.equal(calls[4].options.headers["X-CSRF-Token"], "csrf-2");
  assert.equal(calls[4].options.credentials, "same-origin");
  assert.equal(users.at(-1), null);
  await assert.rejects(() => auth.authRequest("/me"), /Войдите/);
  assert.equal(users.at(-1), null);
  assert.equal(data.size, 0);
});

test("a delayed restore cannot expose a previous demo company's applications", async () => {
  const store=await import('../app/static/js/store.mjs');
  const identity=id=>({id,email:`demo${id}@example.com`,role:'client',is_demo:true,business:{type:'llc',name:`Company ${id}`}});
  let resolveList;
  const pending=new Promise(resolve=>{resolveList=resolve;});
  const response=value=>({ok:true,status:200,json:async()=>value});
  globalThis.fetch=async path=>path==='/api/applications'?pending:response(path==='/api/documents'?[]:{status:'approved',version:1,documents:[],history:[]});
  store.useServerAuth(identity(41));const before=store.session().id;
  const restore=store.restoreServerApplications();
  store.useServerAuth(identity(42));assert.notEqual(store.session().id,before);
  resolveList(response([{id:'old-company-app',status:'approved'}]));await restore;
  assert.deepEqual(store.ownApplications(),[]);
  store.useServerAuth(null);
});

test("an older response cannot replace a newer workflow after accepting terms", async () => {
  const store=await import('../app/static/js/store.mjs');
  store.useServerAuth({id:43,email:'race@example.com',role:'client',business:{type:'llc',name:'Race'}});
  const response=value=>({ok:true,status:200,json:async()=>value});
  let release,lists=0,newest=true;
  globalThis.fetch=async path=>{
    if(path==='/api/applications')return ++lists===1?new Promise(resolve=>{release=resolve;}):response([{id:'app',status:'approved',version:2}]);
    if(path==='/api/documents')return response([]);
    return response({status:newest?'offer_accepted':'approved',version:newest?3:1,documents:[],history:[]});
  };
  const old=store.restoreServerApplications();await store.restoreServerApplications();
  assert.equal(store.ownApplications()[0].status,'offer_accepted');
  newest=false;release(response([{id:'app',status:'approved',version:1}]));await old;
  assert.equal(store.ownApplications()[0].version,3);
  assert.equal(store.ownApplications()[0].status,'offer_accepted');
  store.useServerAuth(null);
});
