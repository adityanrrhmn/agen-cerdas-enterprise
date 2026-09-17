// Screenshot halaman dashboard lewat Chrome DevTools Protocol (Edge/Chrome headless), dengan jeda waktu nyata.
// Dibutuhkan karena --virtual-time-budget tidak pernah selesai pada halaman yang memakai SSE.
// Pakai: node tools/screenshot.mjs <baseUrl> <outDir> <nama>=<lebar>x<tinggi>@<path> ...
// Contoh: node tools/screenshot.mjs http://localhost:5174 .impeccable/review desktop-review=1440x1000@/?tab=review
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [base, outDir, ...shots] = process.argv.slice(2);
if (!base || !outDir || !shots.length) {
  console.error("Pakai: node tools/screenshot.mjs <baseUrl> <outDir> nama=LxT@path ...");
  process.exit(2);
}
const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
];
const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "cdp-shot-"));
const browser = spawn(BROWSERS[0], ["--headless=new", "--disable-gpu", "--no-first-run", `--remote-debugging-port=${port}`,
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

mkdirSync(outDir, { recursive: true });
try {
  await send("Page.enable");
  for (const spec of shots) {
    const [, name, w, h, path] = spec.match(/^([\w-]+)=(\d+)x(\d+)@(.*)$/) ?? [];
    if (!name) throw new Error(`Format salah: ${spec}`);
    const mobile = Number(w) < 600;
    await send("Emulation.setDeviceMetricsOverride", { width: Number(w), height: Number(h), deviceScaleFactor: 1, mobile });
    await send("Page.navigate", { url: base + path });
    await sleep(5000); // data dimuat lewat polling/SSE
    const { result } = await send("Runtime.evaluate", { expression: "JSON.stringify({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, sh: document.documentElement.scrollHeight})", returnByValue: true });
    const dims = JSON.parse(result.value);
    const height = Math.min(dims.sh, 4000);
    await send("Emulation.setDeviceMetricsOverride", { width: Number(w), height, deviceScaleFactor: 1, mobile });
    await sleep(400);
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(outDir, `${name}.png`), Buffer.from(data, "base64"));
    const overflow = dims.sw > dims.cw ? ` OVERFLOW horizontal ${dims.sw}px > ${dims.cw}px` : "";
    console.log(`${name}: ${resolve(outDir, name + ".png")} (${w}x${height})${overflow}`);
  }
} finally {
  ws.close();
  browser.kill();
}
