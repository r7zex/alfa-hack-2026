import { test } from "node:test";
import assert from "node:assert/strict";
import {
  PRODUCTS,
  documentTypes,
  payment,
  estimate,
  validateInn,
  validateLoan,
  escape,
} from "../app/static/js/domain.mjs";

test("INN validates both entity lengths and their independent check digits", () => {
  assert.equal(validateInn("9900000017", "llc"), "");
  assert.equal(validateInn("990000000115", "ip"), "");
  assert.ok(validateInn("9900000018", "llc"));
  assert.ok(validateInn("990000000116", "ip"));
  assert.ok(validateInn("9900000017", "ip"));
  assert.ok(validateInn("0000000000", "llc"));
});
test("annuity handles zero interest and agrees with a known monthly calculation", () => {
  assert.equal(payment(120000, 12, 0), 10000);
  assert.ok(Math.abs(payment(1000000, 12, 24) - 94559.5966) < 0.01);
  assert.equal(payment(-1, 12, 24), 0);
});
test("overdraft calculates daily interest, not an amortized monthly installment", () => {
  const result = estimate(PRODUCTS[2], 500000, 6, 30);
  assert.ok(Math.abs(result.interest - (500000 * 0.26 * 30) / 365) < 1e-8);
  assert.equal(result.total, 500000 + result.interest);
});
test("document requirements distinguish IP financial reporting and equipment invoices", () => {
  assert.deepEqual(
    documentTypes("ip", "working").map((d) => d.id),
    ["statement", "tax"],
  );
  assert.deepEqual(
    documentTypes("llc", "equipment").map((d) => d.id),
    ["statement", "accounts", "invoice"],
  );
});
test("loan limits reject excessive amounts and fractional terms", () => {
  assert.equal(
    validateLoan({ productId: "working", amount: 1000000, months: 12 }),
    "",
  );
  assert.ok(
    validateLoan({ productId: "overdraft", amount: 3000000, months: 12 }),
  );
  assert.ok(
    validateLoan({ productId: "equipment", amount: 300000, months: 6.5 }),
  );
});
test("user content is escaped before HTML interpolation", () => {
  assert.equal(
    escape('<img src=x onerror="alert(1)">'),
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
  );
});
test("demo repository preserves ownership and rejects repeated decisions or acceptances", async () => {
  const data = new Map(),
    sessionData = new Map();
  globalThis.localStorage = {
    getItem: (k) => data.get(k) || null,
    setItem: (k, v) => data.set(k, v),
  };
  globalThis.sessionStorage = {
    getItem: (k) => sessionData.get(k) || null,
    setItem: (k, v) => sessionData.set(k, v),
    removeItem: (k) => sessionData.delete(k),
  };
  const store = await import("../app/static/js/store.mjs");
  store.login("demo-llc");
  const id = store.saveApplication(
    { productId: "working", amount: 1000000, months: 12, documentIds: [] },
    false,
  );
  assert.ok(store.ownApplications().some((a) => a.id === id));
  store.login("demo-ip");
  assert.equal(
    store.ownApplications().some((a) => a.id === id),
    false,
  );
  assert.throws(() => store.saveApplication({ id }, false), /не найдена/);
  assert.throws(() => store.decide(id, { status: "approved" }), /аналитика/);
  store.login("demo-llc");
  store.saveApplication(
    { id, productId: "working", amount: 1000000, months: 12, documentIds: [] },
    true,
  );
  assert.throws(() => store.saveApplication({ id }, false), /редактирования/);
  store.login("admin");
  store.decide(id, { status: "approved", comment: "Демо" });
  assert.throws(
    () => store.decide(id, { status: "rejected", comment: "Повтор" }),
    /уже принято/,
  );
  store.login("demo-llc");
  store.acceptOffer(id);
  assert.equal(
    store.ownApplications().find((a) => a.id === id).status,
    "completed",
  );
  assert.throws(() => store.acceptOffer(id), /больше не доступно/);
});
