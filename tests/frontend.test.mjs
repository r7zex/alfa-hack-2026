import { test } from "node:test";
import assert from "node:assert/strict";
import { safeStorage, cloneData, makeId } from "../app/static/js/runtime.mjs";
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
test("blocked browser storage uses memory without throwing", () => {
  const storage = safeStorage(() => {
    throw new Error("Storage blocked");
  });
  assert.equal(storage.getItem("demo"), null);
  storage.setItem("demo", "saved");
  assert.equal(storage.getItem("demo"), "saved");
  storage.removeItem("demo");
  assert.equal(storage.getItem("demo"), null);
});
test("storage quota failure retains previously read data for this page", () => {
  const storage = safeStorage(() => ({
    getItem: () => "existing",
    setItem: () => {
      throw new Error("Quota exceeded");
    },
  }));
  assert.equal(storage.getItem("old"), "existing");
  storage.setItem("new", "temporary");
  assert.equal(storage.getItem("old"), "existing");
  assert.equal(storage.getItem("new"), "temporary");
});
test("JSON demo state can be cloned when structuredClone is unavailable", () => {
  const original = globalThis.structuredClone;
  try {
    globalThis.structuredClone = undefined;
    const data = { profile: { type: "ip" }, values: [1, 2] };
    const copy = cloneData(data);
    assert.deepEqual(copy, data);
    copy.profile.type = "llc";
    assert.equal(data.profile.type, "ip");
  } finally {
    globalThis.structuredClone = original;
  }
});
test("UUID creation works without the secure-context randomUUID method", () => {
  const original = globalThis.crypto;
  try {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: { getRandomValues: original.getRandomValues.bind(original) },
    });
    assert.match(
      makeId(),
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    assert.notEqual(makeId(), makeId());
  } finally {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: original,
    });
  }
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
