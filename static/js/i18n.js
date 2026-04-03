/**
 * i18n.js — Language switcher. Sets lang via POST /api/set-lang then reloads.
 */
async function setLang(lang) {
    await fetch('/api/set-lang', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang }),
    });
    window.location.reload();
}
