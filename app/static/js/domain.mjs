export const PRODUCTS = [
  {
    id: "working",
    name: "Оборотный кредит",
    icon: "chart",
    description: "На пополнение запасов и текущие расходы",
    detail:
      "Закупайте товары, оплачивайте поставки и пополняйте оборотные средства.",
    min: 100000,
    max: 5000000,
    months: [3, 24],
    rate: 24,
    purpose: "Закупка товаров и пополнение оборотных средств",
    feature: "Равные ежемесячные платежи",
  },
  {
    id: "equipment",
    name: "На оборудование",
    icon: "gear",
    description: "На развитие и модернизацию бизнеса",
    detail:
      "Обновите оборудование, запустите производство или расширьте мощности.",
    min: 300000,
    max: 15000000,
    months: [6, 60],
    rate: 21,
    purpose: "Приобретение оборудования",
    feature: "Счёт или предложение поставщика",
  },
  {
    id: "overdraft",
    name: "Овердрафт",
    icon: "cycle",
    description: "На краткосрочные кассовые разрывы",
    detail: "Оплачивайте срочные расходы, пока ожидаете поступления на счёт.",
    min: 50000,
    max: 2000000,
    months: [1, 12],
    rate: 26,
    purpose: "Покрытие кассовых разрывов",
    feature: "Проценты на использованную сумму",
  },
];
export const STATUS = {
  draft: "Черновик",
  pending: "На рассмотрении",
  approved: "Одобрено",
  rejected: "Отказано",
  completed: "Ранее завершено",
  submitted: "Отправлена", processing: "Проверка", needs_info: "Нужны уточнения",
  processing_error: "Ошибка проверки", offer_accepted: "Условия приняты",
  offer_declined: "Предложение отклонено", signed: "Демо-договор подписан", disbursed: "Демо-выдача завершена",
};
export const productById = (id) =>
  PRODUCTS.find((p) => p.id === id) || PRODUCTS[0];
export const money = (value) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 })
    .format(Number(value))
    .replace(/\s/g, " ") + " ₽";
export const number = (value) =>
  new Intl.NumberFormat("ru-RU").format(Number(value)).replace(/\s/g, " ");
export const date = (value) => new Date(value).toLocaleDateString("ru-RU");
export const shortMoney = (value) =>
  value >= 1000000 ? `${value / 1000000} млн ₽` : money(value);
export function payment(amount, months, annualRate) {
  if (!(amount > 0) || !(months > 0) || annualRate < 0) return 0;
  const r = annualRate / 1200;
  return r === 0 ? amount / months : (amount * r) / (1 - (1 + r) ** -months);
}
export function estimate(product, amount, months, days = 30) {
  if (product.id === "overdraft") {
    const interest = (((amount * product.rate) / 100) * days) / 365;
    return { installment: interest, interest, total: amount + interest };
  }
  const installment = payment(amount, months, product.rate);
  return {
    installment,
    interest: installment * months - amount,
    total: installment * months,
  };
}
export function validateInn(value, type) {
  const size = type === "ip" ? 12 : 10;
  if (!new RegExp(`^\\d{${size}}$`).test(value))
    return `ИНН ${type === "ip" ? "ИП" : "юрлица"} должен содержать ${size} цифр`;
  if (/^0+$/.test(value)) return "Проверьте ИНН";
  const d = [...value].map(Number);
  const check = (weights) =>
    (weights.reduce((s, w, i) => s + w * d[i], 0) % 11) % 10;
  const valid =
    size === 10
      ? check([2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[9]
      : check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[10] &&
        check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[11];
  return valid ? "" : "Контрольные цифры ИНН не совпадают";
}
export function documentTypes(type, productId) {
  const docs = [
    {
      id: "statement",
      name: "Выписка по расчётному счёту",
      hint: "За последние 6 месяцев",
    },
    type === "ip"
      ? {
          id: "tax",
          name: "Налоговая декларация ИП",
          hint: "За последний отчётный период",
        }
      : {
          id: "accounts",
          name: "Бухгалтерская отчётность",
          hint: "Баланс и отчёт о финансовых результатах",
        },
  ];
  if (productId === "equipment")
    docs.push({
      id: "invoice",
      name: "Предложение поставщика",
      hint: "Счёт или коммерческое предложение на оборудование",
    });
  return docs;
}
export function validateLoan(values) {
  const p = productById(values.productId);
  if (
    !Number.isFinite(+values.amount) ||
    +values.amount < p.min ||
    +values.amount > p.max
  )
    return `Сумма: от ${money(p.min)} до ${money(p.max)}`;
  if (
    !Number.isInteger(+values.months) ||
    +values.months < p.months[0] ||
    +values.months > p.months[1]
  )
    return `Срок: от ${p.months[0]} до ${p.months[1]} мес.`;
  return "";
}
export function escape(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}

export async function loadProducts() {
  const response = await fetch("/api/products", {credentials: "same-origin"});
  if (!response.ok) throw Error("Каталог продуктов недоступен");
  const rows = await response.json();
  for (const row of rows) {
    const product = PRODUCTS.find(p => p.id === row.id);
    if (product) Object.assign(product, {min: row.min, max: row.max, months: row.months, rate: row.rate});
  }
}
