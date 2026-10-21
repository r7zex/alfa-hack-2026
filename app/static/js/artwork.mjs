// Supplied artwork: shared paths keep decorative media out of business logic.
const base = new URL("../images/", import.meta.url);
export function artwork(name, className = "", eager = false) {
  return `<img class="artwork ${className}" src="${new URL(name + ".webp", base).href}" width="960" height="960" alt="" aria-hidden="true" loading="${eager ? "eager" : "lazy"}" decoding="async">`;
}
export function pageBanner(content, image) {
  return `<section class="page-banner"><div class="page-banner-copy">${content}</div>${artwork(image, "page-art", true)}</section>`;
}
export function authBackground(mode) {
  const image = mode === "login" ? "wave-login" : "wave-register";
  return `<img class="auth-background" src="${new URL(image + ".webp", base).href}" width="${mode === "login" ? 1440 : 1254}" height="${mode === "login" ? 810 : 1254}" alt="" aria-hidden="true" fetchpriority="high" decoding="async">`;
}
