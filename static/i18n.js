/* ──────────────────────────────────────────────────────────────────
   Lightweight client-side i18n. Default language: Czech (cs).
   Strings are keyed; elements carry data-i18n / data-i18n-ph (placeholder).
   Language is persisted in localStorage and toggled from the navbar.
   ────────────────────────────────────────────────────────────────── */
const I18N = {
  cs: {
    // nav / common
    "nav.admin": "Administrace",
    "nav.logout": "Odhlásit se",
    "nav.settings": "Nastavení",
    "common.loading": "Načítání...",
    "common.save": "Uložit",
    "common.cancel": "Zrušit",
    "common.add": "Přidat",
    "common.remove": "Odebrat",
    "common.close": "Zavřít",
    // login
    "login.title": "Tajný Ježíšek",
    "login.subtitle": "Zadej uživatelské jméno a heslo a zjisti, komu dáváš dárek.",
    "login.username": "Uživatelské jméno",
    "login.password": "Heslo",
    "login.username_ph": "Tvé uživatelské jméno",
    "login.password_ph": "Tvé heslo",
    "login.button": "Přihlásit se",
    "login.hint": "O přihlašovací údaje požádej administrátora.",
    // dashboard
    "dash.welcome": "Vítej",
    "dash.assignment": "Tvé přidělení",
    "dash.giving_to": "Dáváš dárek:",
    "dash.no_assignment": "Zatím nemáš přidělení. Požádej administrátora o losování!",
    "dash.budget": "Rozpočet na dárek",
    "dash.exclusions": "Moje výjimky",
    "dash.exclusions_hint": "Lidé, které nechceš losovat. (Administrátor to může změnit.)",
    "dash.exclusions_select": "Vyber někoho k vyloučení...",
    "dash.no_exclusions": "Žádné výjimky nenastaveny.",
    "dash.wishes": "Vánoční přání",
    "dash.wishes_hint": "Napiš, co si přeješ! Ten, kdo tě vylosoval, to uvidí.",
    "dash.wishes_ph": "Co si přeješ k Vánocům? (max 500 znaků)",
    "dash.save_wish": "Uložit přání",
    "dash.recipient_wish": "Přání obdarovaného",
    "dash.recipient_wish_hint": "Co si přeje ten, koho jsi vylosoval/a:",
    "dash.wish_saved": "✅ Přání uloženo!",
    "dash.wish_empty": "Přání nemůže být prázdné.",
    // settings / password
    "settings.title": "Nastavení",
    "settings.current_pw": "Současné heslo",
    "settings.new_pw": "Nové heslo",
    "settings.current_pw_ph": "Současné heslo",
    "settings.new_pw_ph": "Nové heslo (min. 4 znaky)",
    "settings.update_pw": "Změnit heslo",
    "settings.pw_updated": "✅ Heslo změněno!",
    "settings.pw_both": "Obě pole jsou povinná.",
    "settings.pw_min": "Nové heslo musí mít alespoň 4 znaky.",
    // Q&A
    "qa.ask_title": "Zeptej se obdarovaného",
    "qa.ask_hint": "Zeptej se anonymně člověka, kterého jsi vylosoval/a. Neuvidí, kdo se ptá.",
    "qa.ask_ph": "Napiš otázku (např. „Jakou máš velikost trička?“)",
    "qa.ask_button": "Odeslat otázku",
    "qa.no_questions": "Zatím žádné otázky.",
    "qa.waiting_answer": "Čeká na odpověď...",
    "qa.answer_label": "Odpověď:",
    "qa.ask_sent": "✅ Otázka odeslána!",
    "qa.incoming_title": "Otázky k tvému dárku",
    "qa.incoming_hint": "Někdo se tě anonymně ptá. Odpověz, ať dostaneš lepší dárek!",
    "qa.no_incoming": "Zatím se nikdo neptal.",
    "qa.answer_ph": "Napiš odpověď...",
    "qa.answer_button": "Odpovědět",
    "qa.answered": "✅ Odpovězeno",
    "qa.answer_saved": "✅ Odpověď uložena!",
  },
  en: {
    "nav.admin": "Admin",
    "nav.logout": "Logout",
    "nav.settings": "Settings",
    "common.loading": "Loading...",
    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.add": "Add",
    "common.remove": "Remove",
    "common.close": "Close",
    "login.title": "Secret Santa",
    "login.subtitle": "Enter your username and password to see your assignment.",
    "login.username": "Username",
    "login.password": "Password",
    "login.username_ph": "Your username",
    "login.password_ph": "Your password",
    "login.button": "Login",
    "login.hint": "Ask the admin for your login credentials.",
    "dash.welcome": "Welcome",
    "dash.assignment": "Your Assignment",
    "dash.giving_to": "You are giving to:",
    "dash.no_assignment": "No assignment yet. Ask the admin to draw!",
    "dash.budget": "Gift budget",
    "dash.exclusions": "My Exclusions",
    "dash.exclusions_hint": "People you don't want to draw. (Admin can override these.)",
    "dash.exclusions_select": "Select someone to exclude...",
    "dash.no_exclusions": "No exclusions set.",
    "dash.wishes": "Christmas Wishes",
    "dash.wishes_hint": "Share your wish list! The person you draw will see what you want.",
    "dash.wishes_ph": "What are you wishing for this Christmas? (max 500 characters)",
    "dash.save_wish": "Save My Wish",
    "dash.recipient_wish": "Recipient's Wish",
    "dash.recipient_wish_hint": "What the person you drew is wishing for:",
    "dash.wish_saved": "✅ Wish saved!",
    "dash.wish_empty": "Wish cannot be empty.",
    "settings.title": "Settings",
    "settings.current_pw": "Current Password",
    "settings.new_pw": "New Password",
    "settings.current_pw_ph": "Current password",
    "settings.new_pw_ph": "New password (min 4 characters)",
    "settings.update_pw": "Update Password",
    "settings.pw_updated": "✅ Password updated!",
    "settings.pw_both": "Both fields required.",
    "settings.pw_min": "New password must be at least 4 characters.",
    "qa.ask_title": "Ask Your Recipient",
    "qa.ask_hint": "Ask the person you drew an anonymous question. They won't see who's asking.",
    "qa.ask_ph": "Type a question (e.g. \"What's your shirt size?\")",
    "qa.ask_button": "Send Question",
    "qa.no_questions": "No questions yet.",
    "qa.waiting_answer": "Waiting for an answer...",
    "qa.answer_label": "Answer:",
    "qa.ask_sent": "✅ Question sent!",
    "qa.incoming_title": "Questions About Your Gift",
    "qa.incoming_hint": "Someone is asking you anonymously. Answer to get a better gift!",
    "qa.no_incoming": "No questions yet.",
    "qa.answer_ph": "Type your answer...",
    "qa.answer_button": "Answer",
    "qa.answered": "✅ Answered",
    "qa.answer_saved": "✅ Answer saved!",
  }
};

function getLang() {
  return localStorage.getItem("lang") || "cs";
}

function t(key) {
  const lang = getLang();
  return (I18N[lang] && I18N[lang][key]) || (I18N.cs[key]) || key;
}

function applyI18n() {
  const lang = getLang();
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
  });
  // Update the toggle label to show the OTHER language's flag.
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.textContent = lang === "cs" ? "🇬🇧 EN" : "🇨🇿 CS";
}

function toggleLang() {
  const next = getLang() === "cs" ? "en" : "cs";
  localStorage.setItem("lang", next);
  applyI18n();
  // Let page scripts re-render any dynamically-built content.
  document.dispatchEvent(new CustomEvent("langchanged", { detail: { lang: next } }));
}

document.addEventListener("DOMContentLoaded", () => {
  applyI18n();
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.addEventListener("click", (e) => { e.preventDefault(); toggleLang(); });
});
