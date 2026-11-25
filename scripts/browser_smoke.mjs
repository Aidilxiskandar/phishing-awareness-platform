// Real-browser smoke test: drives a full drill in headless Chrome against a
// running PhishGuard server and fails on any HTTP error, CSP violation or JS error.
//
// Why: some bugs only exist in a real browser. Example: under
// Referrer-Policy: no-referrer, browsers send "Origin: null" on form POSTs, so
// every admin form failed CSRF while the Python test client (which sends no
// Origin) passed. This catches that class of problem.
//
// usage:   node scripts/browser_smoke.mjs [baseUrl] [adminUser] [adminPassword]
// default: http://127.0.0.1:8765  admin  phishguard-dev
// Needs Node >= 22 (built-in WebSocket) and Chrome/Chromium (set CHROME_PATH to override).
// Only point it at a throwaway local server: it creates users and a campaign.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base = "http://127.0.0.1:8765", user = "admin", password = "phishguard-dev"] =
  process.argv.slice(2);
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) {
  console.error("Refusing: only run the smoke test against a local server.");
  process.exit(2);
}

const chromePath = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium", "/usr/bin/chromium-browser",
].find((p) => p && existsSync(p));
if (!chromePath) { console.error("Chrome not found; set CHROME_PATH."); process.exit(2); }

const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "phishguard-smoke-"));
const chrome = spawn(chromePath, [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check",
  ...(process.platform === "linux" ? ["--no-sandbox"] : []), "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const problems = [];
let step = "start";
function fail(msg) { problems.push(`[${step}] ${msg}`); }
const log = (m) => { if (process.env.SMOKE_VERBOSE) console.log(`  ${m}`); };

async function cdp() {
  let url;
  for (let i = 0; i < 100 && !url; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      url = list.find((t) => t.type === "page")?.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    if (!url) await sleep(100);
  }
  if (!url) throw new Error("could not connect to Chrome");
  const ws = new WebSocket(url);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0;
  const pending = new Map();
  const listeners = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    for (const fn of listeners.get(msg.method) || []) fn(msg.params);
  };
  return {
    ws,
    send: (method, params = {}) => new Promise((resolve) => {
      const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({ id: i, method, params }));
    }),
    on: (method, fn) => listeners.set(method, [...(listeners.get(method) || []), fn]),
    once: (method, ms = 10000) => new Promise((resolve, reject) => {
      const t = setTimeout(() => { off(); reject(new Error(`timed out waiting for ${method}`)); }, ms);
      const fn = (p) => { clearTimeout(t); off(); resolve(p); };
      const off = () => listeners.set(method, (listeners.get(method) || []).filter((f) => f !== fn));
      listeners.set(method, [...(listeners.get(method) || []), fn]);
    }),
  };
}

const c = await cdp();
await c.send("Page.enable");
await c.send("Network.enable");
// Present as an ordinary desktop browser: PhishGuard (correctly) classifies a
// "HeadlessChrome" User-Agent as automation, and here we play a real person.
const ua = (await c.send("Runtime.evaluate", { expression: "navigator.userAgent", returnByValue: true })).result.result.value;
await c.send("Network.setUserAgentOverride", { userAgent: ua.replace("HeadlessChrome", "Chrome") });
await c.send("Log.enable");
await c.send("Runtime.enable");

const EXPECTED_STATUS = new Set();  // "METHOD path" pairs allowed to be >= 400
c.on("Network.responseReceived", (p) => {
  const { status, url } = p.response;
  if (status >= 400 && url.startsWith(base)) {
    const path = new URL(url).pathname;
    if (!EXPECTED_STATUS.has(path)) fail(`HTTP ${status} ${path}`);
  }
});
c.on("Log.entryAdded", ({ entry }) => {
  if (entry.level === "error" && !/favicon/.test(entry.url || "")) fail(`console: ${entry.text}`);
});
c.on("Runtime.exceptionThrown", (p) => fail(`JS exception: ${p.exceptionDetails.text}`));

async function go(path) {
  const loaded = c.once("Page.loadEventFired");
  await c.send("Page.navigate", { url: base + path });
  await loaded; await sleep(300);
}
async function js(expression) {
  const r = await c.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result.exceptionDetails) throw new Error(`[${step}] ${r.result.exceptionDetails.text}: ${expression}`);
  return r.result.result.value;
}
async function submit(expression) {
  const loaded = c.once("Page.loadEventFired");
  await js(expression);
  await loaded; await sleep(300);
}
const path = () => js("location.pathname");
const begin = (name) => { step = name; log(name); };
const text = () => js("document.body.innerText");
function expect(cond, msg) { if (!cond) fail(msg); }

const stamp = Date.now();
const email = `smoke-${stamp}@example.com`;
try {
  begin("login");
  await go("/login");
  await submit(`document.querySelector('[name=username]').value=${JSON.stringify(user)};
    document.querySelector('[name=password]').value=${JSON.stringify(password)};
    document.querySelector('form[action="/login"]').submit()`);
  expect(await path() === "/", `expected dashboard after login, got ${await path()}`);

  begin("add user");
  await go("/users");
  await submit(`const f=document.querySelector('form[action="/users"]');
    f.querySelector('[name=email]').value=${JSON.stringify(email)};
    f.querySelector('[name=name]').value='Smoke Test';
    f.querySelector('[name=consented]').checked=true; f.submit()`);
  expect((await text()).includes(email), "new user not listed");

  begin("create campaign");
  await go("/phishing");
  await submit(`const f=document.querySelector('form[action="/campaigns"]');
    f.querySelector('[name=name]').value='Smoke drill ${stamp}'; f.submit()`);
  const campaignPath = await path();
  expect(/^\/campaigns\/\d+$/.test(campaignPath), `expected campaign page, got ${campaignPath}`);

  begin("target + send");
  await submit(`const f=document.querySelector('form[action$="/targets"]');
    const row=[...f.querySelectorAll('tr')].find(r=>r.innerText.includes(${JSON.stringify(email)}));
    row.querySelector('input[type=checkbox]').checked=true; f.submit()`);
  await submit(`document.querySelector('form[action$="/send"]').submit()`);
  let token = "";
  for (let i = 0; i < 40 && !token; i++) {
    await go(campaignPath);
    token = await js(`(()=>{const row=[...document.querySelectorAll('tr')].find(r=>r.innerText.includes(${JSON.stringify(email)}));
      const m=row && row.innerText.match(/\\/t\\/click\\/([A-Za-z0-9_-]+)/); return m?m[1]:""})()`);
    if (!token) await sleep(250);
  }
  expect(token, "no tracked link for the recipient");

  begin("recipient clicks (JS beacon)");
  await go(`/t/click/${token}`);
  await sleep(800);  // let the beacon land
  await go(campaignPath);
  const human = await js(`(()=>{const m=[...document.querySelectorAll('.metric')].find(e=>/Human clicks/.test(e.innerText));
    return m?parseInt(m.innerText,10):-1})()`);
  expect(human === 1, `expected 1 human click after a browser click, got ${human}`);

  begin("recipient reports");
  await go(`/t/report/${token}`);       // confirmation page auto-submits its form
  await sleep(800);
  expect(/thank you for reporting/i.test(await text()), "report was not confirmed");

  begin("staff training");
  await go(`/t/click/${token}`);
  const cta = await js(`document.querySelector('a.cta').getAttribute('href')`);
  expect(cta.startsWith(`/t/training/${token}/`), `unexpected training link ${cta}`);
  await go(cta);
  expect(!(await text()).includes("Log out"), "admin navigation shown to staff");
  await submit(`const f=document.querySelector('form[action$="/quiz"]');
    const names=[...new Set([...f.querySelectorAll('input[type=radio]')].map(r=>r.name))];
    names.forEach(n=>f.querySelector('input[name="'+n+'"]').checked=true); f.submit()`);
  expect(/Your result/.test(await text()), "quiz result not shown");

  begin("admin pages render");
  for (const p of ["/", "/phishing", "/training", "/users", "/reports", `/reports${campaignPath}`]) {
    await go(p);
    expect(await path() === p, `${p} redirected to ${await path()}`);
  }

  begin("logout");
  await go("/");
  await submit(`document.querySelector('form[action="/logout"]').submit()`);
  expect(await path() === "/login", "logout did not return to login");
} catch (e) {
  fail(e.message);
} finally {
  c.ws.close(); chrome.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ }
}

if (problems.length) {
  console.error(`Browser smoke test FAILED (${problems.length}):\n  ` + problems.join("\n  "));
  process.exit(1);
}
console.log("Browser smoke test passed: login, users, campaign, send, human click, report, staff training, all tabs, logout.");
