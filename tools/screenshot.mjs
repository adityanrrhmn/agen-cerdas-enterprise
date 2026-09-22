// Screenshot dashboard lewat Chrome DevTools Protocol (Edge/Chrome headless) dengan jeda waktu nyata.
// Dibutuhkan karena --virtual-time-budget tidak pernah selesai pada halaman yang memakai SSE.
//
// Mode singkat:  node tools/screenshot.mjs <baseUrl> <outDir> <nama>=<lebar>x<tinggi>@<path> ...
// Mode rencana:  node tools/screenshot.mjs --plan rencana.json
//   rencana.json: { "base": "http://localhost:5174", "out": "dir", "scale": 2, "shots": [
//     { "name": "review", "width": 1440, "height": 1000, "path": "/?tab=review",
//       "storage": { "campaign": "CMP-..." },           // diisi ke localStorage sebelum halaman dimuat
//       "actions": ["document.querySelector('.seg-review').click()"],  // dijalankan berurutan (jeda 1,2 dtk)
//       "selector": ".detail",                           // opsional: potong ke elemen ini
//       "full": true }                                   // opsional: rekam seluruh tinggi halaman
//   ]}
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

let plan;
if (process.argv[2] === "--plan") {
  plan = JSON.parse(readFileSync(process.argv[3], "utf8"));
} else {
  const [base, out, ...specs] = process.argv.slice(2);
  if (!base || !out || !specs.length) {
    console.error("Pakai: node tools/screenshot.mjs <baseUrl> <outDir> nama=LxT@path ...  |  --plan rencana.json");
    process.exit(2);
  }
  plan = { base, out, scale: Number(process.env.SCALE || 1), shots: specs.map((s) => {
    const [, name, width, height, path] = s.match(/^([\w-]+)=(\d+)x(\d+)@(.*)$/) ?? [];
    if (!name) throw new Error(`Format salah: ${s}`);
    return { name, width: Number(width), height: Number(height), path, full: true };
  }) };
}

const BROWSER = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "cdp-shot-"));
const browser = spawn(BROWSER, ["--headless=new", "--disable-gpu", "--no-first-run", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* browser belum siap */ }
    await sleep(200);
  }
  throw new Error("Browser headless tidak merespons");
}

const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let seq = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq;
  pending.set(id, (m) => (m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result)));
  ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;

mkdirSync(plan.out, { recursive: true });
const scale = plan.scale || 1;
try {
  await send("Page.enable");
  for (const s of plan.shots) {
    const mobile = s.width < 600;
    await send("Emulation.setDeviceMetricsOverride", { width: s.width, height: s.height, deviceScaleFactor: scale, mobile });
    await send("Page.navigate", { url: plan.base + "/" });
    await sleep(800);
    await evaluate(`(() => { try { localStorage.clear(); ${Object.entries(s.storage || {}).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`).join("")} } catch (e) {} })()`);
    await send("Page.navigate", { url: plan.base + s.path });
    await sleep(s.wait ?? 5000);
    for (const action of s.actions || []) {
      await evaluate(`(async () => { ${action} })()`);
      await sleep(1200);
    }
    const dims = await evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, sh: document.documentElement.scrollHeight})");
    let clip;
    if (s.full) {
      const height = Math.min(dims.sh, 4000);
      await send("Emulation.setDeviceMetricsOverride", { width: s.width, height, deviceScaleFactor: scale, mobile });
      await sleep(500);
    }
    if (s.selector) {
      const box = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(s.selector)}); if (!el) return null;
        const r = el.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height }; })()`);
      if (!box) throw new Error(`${s.name}: selector ${s.selector} tidak ditemukan`);
      const pad = s.pad ?? 0;
      clip = { x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad), width: box.width + 2 * pad, height: box.height + 2 * pad, scale: 1 };
    }
    const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, ...(clip ? { clip } : {}) });
    writeFileSync(join(plan.out, `${s.name}.png`), Buffer.from(data, "base64"));
    const overflow = dims.sw > dims.cw ? ` OVERFLOW horizontal ${dims.sw}px > ${dims.cw}px` : "";
    console.log(`${s.name}: ${resolve(plan.out, s.name + ".png")}${clip ? " (dipotong)" : ""}${overflow}`);
  }
} finally {
  ws.close();
  browser.kill();
}
