// Generator deck presentasi Outreach Control (Kelompok 1). Jalankan: npm run build  → Presentasi_Outreach_Control_Kelompok_1.pptx
// Semua angka hasil berasal dari tes otomatis (43 tes) dan simulasi 100 lead fiktif (docs/runbook-aplikasi.md).
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const L = require("lucide-react");

const OUT = path.join(__dirname, "Presentasi_Outreach_Control_Kelompok_1.pptx");
const IMG = (f) => path.join(__dirname, "..", "docs", "gambar", f);
const ASET = (f) => path.join(__dirname, "aset", f);

const C = {
  deep: "0C3136", teal: "154E54", tealM: "2F7D84", teal200: "BCD7D9", teal100: "DCEBEC", teal50: "EDF5F5",
  amber: "F2B544", amber50: "FDF3DC", ink: "17292C", ink2: "3F5558", ink3: "5F7477", line: "D6E2E3",
  pass: "1E6F48", review: "9A6300", block: "A8321F", white: "FFFFFF",
};
const HEAD = "Cambria";
const BODY = "Calibri";
const W = 13.333;

const iconCache = new Map();
async function icon(Comp, color = "FFFFFF") {
  const key = `${Comp.displayName || Comp.name}-${color}`;
  if (!iconCache.has(key)) {
    const svg = renderToStaticMarkup(React.createElement(Comp, { color: `#${color}`, size: 256, strokeWidth: 1.9 }));
    const png = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
    iconCache.set(key, "image/png;base64," + png.toString("base64"));
  }
  return iconCache.get(key);
}
async function ratio(file) {
  const m = await sharp(file).metadata();
  return m.height / m.width;
}

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.author = "Kelompok 1 — Agen Cerdas Enterprise";
  pres.title = "Outreach Control: Sistem Multi-Agent Email Writer & Enrichment";
  let page = 0;

  // ------------------------------------------------------------ helper
  const text = (slide, t, o) => slide.addText(t, { fontFace: BODY, color: C.ink, margin: 0, isTextBox: true, valign: "top", ...o });

  function light(title, notes) {
    const s = pres.addSlide();
    page += 1;
    s.background = { color: C.white };
    text(s, title, { x: 0.6, y: 0.42, w: 12.1, h: 0.85, fontFace: HEAD, fontSize: 28, bold: true, color: C.ink, valign: "middle" });
    text(s, "Outreach Control · Kelompok 1 · Agen Cerdas Enterprise", { x: 0.6, y: 7.02, w: 7, h: 0.3, fontSize: 10, color: C.ink3 });
    text(s, String(page), { x: 12.23, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: C.ink3, align: "right" });
    s.addNotes(notes);
    return s;
  }

  function dark(notes) {
    const s = pres.addSlide();
    page += 1;
    s.background = { color: C.deep };
    s.addNotes(notes);
    return s;
  }

  async function frame(slide, file, x, y, { w, h }) {
    const r = await ratio(file);
    if (w && !h) h = w * r;
    if (h && !w) w = h / r;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, fill: { color: C.white }, line: { color: C.line, width: 0.75 },
      shadow: { type: "outer", blur: 8, offset: 3, angle: 90, color: "0C3136", opacity: 0.18 },
    });
    slide.addImage({ path: file, x, y, w, h });
    return { w, h };
  }

  async function iconCircle(slide, Comp, x, y, d = 0.62, bg = C.teal, fg = "FFFFFF") {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
    const pad = d * 0.24;
    slide.addImage({ data: await icon(Comp, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
  }

  function card(slide, x, y, w, h, fill = C.teal50) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill } });
  }

  async function note(slide, items, x, y, w, gap = 1.12) {
    // Anotasi bernomor di samping tangkapan layar
    for (const [i, [head, body]] of items.entries()) {
      const yy = y + i * gap;
      slide.addShape(pres.shapes.OVAL, { x, y: yy, w: 0.42, h: 0.42, fill: { color: C.amber }, line: { color: C.amber } });
      text(slide, String(i + 1), { x, y: yy, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.deep, align: "center", valign: "middle" });
      text(slide, [
        { text: head, options: { bold: true, fontSize: 15, color: C.ink, breakLine: true } },
        { text: body, options: { fontSize: 12.5, color: C.ink2 } },
      ], { x: x + 0.6, y: yy - 0.04, w: w - 0.6, h: gap - 0.08, paraSpaceAfter: 2 });
    }
  }

  // ============================================================ 1. Judul
  {
    const s = dark(
      "Pembukaan (±40 detik). Perkenalkan Kelompok 1 dan judul: Outreach Control, sistem multi-agent yang menyusun email outreach B2B " +
      "berdasarkan bukti, dengan manusia memegang keputusan kirim. Sampaikan bahwa presentasi mencakup rancangan dan prototipe yang sudah berjalan.");
    text(s, "AGEN CERDAS ENTERPRISE  ·  KELOMPOK 1", { x: 0.7, y: 0.75, w: 6.2, h: 0.35, fontSize: 13, bold: true, color: C.amber, charSpacing: 2 });
    text(s, "Outreach Control", { x: 0.7, y: 1.25, w: 6.4, h: 1.0, fontFace: HEAD, fontSize: 46, bold: true, color: C.white });
    text(s, "Sistem multi-agent untuk email outreach B2B yang setiap klaimnya dapat ditelusuri ke bukti",
      { x: 0.7, y: 2.3, w: 6.0, h: 1.1, fontSize: 20, color: C.teal200 });
    text(s, "Magister Kecerdasan Artifisial · Universitas Gadjah Mada · 2026", { x: 0.7, y: 3.55, w: 6.2, h: 0.35, fontSize: 13, color: C.teal200 });
    const team = [
      ["Aditya Nurrohman", "Leader & Evaluator"], ["Amar Ma'ruf", "Presenter"], ["St. Syakirah", "Programmer"],
      ["Amelia Gizzela Sheehan Auni", "Designer"], ["Gregorius Bugen Jovi Sitindaon", "Researcher"],
    ];
    team.forEach(([n, r], i) => {
      text(s, [{ text: n, options: { bold: true, fontSize: 12.5, color: C.white, breakLine: true } }, { text: r, options: { fontSize: 11, color: C.amber } }],
        { x: 0.7 + (i % 2) * 3.1, y: 4.55 + Math.floor(i / 2) * 0.72, w: 3.0, h: 0.66 });
    });
    await frame(s, IMG("preview-approval.png"), 7.2, 1.0, { h: 5.35 });
  }

  // ============================================================ 2. Masalah
  {
    const s = light("Outreach B2B masih manual, terpisah, dan sulit diaudit",
      "Masalah (±1 menit). Tim sales sering hanya punya nama, email, atau perusahaan di spreadsheet. Empat masalah: salah orang karena nama sama, " +
      "riset dan penulisan berulang, koordinasi dan jadwal terpisah sehingga kontak bisa dikirimi dua kali, serta risiko privasi dan klaim yang tidak teruji. " +
      "Tekankan kolom kanan: tiap masalah punya respons rancangan yang konkret.");
    const rows = [
      [L.UserSearch, "Data kurang lengkap, nama sama", "Risiko salah orang atau salah perusahaan", "Entity linking, sumber bukti, antrean review"],
      [L.Repeat, "Riset dan penulisan berulang", "Persiapan lambat, banyak pindah aplikasi", "Agen khusus, template, pemrosesan batch"],
      [L.CalendarClock, "Koordinasi dan jadwal terpisah", "Draft terlewat atau kontak dikirimi dua kali", "Orchestrator, state per task, kunci kirim"],
      [L.ShieldAlert, "Privasi dan fakta tidak teruji", "Kontak tanpa izin, personalisasi keliru", "Security gate, approval manusia, suppression"],
    ];
    for (const [i, [ic, p, d, r]] of rows.entries()) {
      const x = 0.6 + (i % 2) * 6.15;
      const y = 1.6 + Math.floor(i / 2) * 2.55;
      card(s, x, y, 5.95, 2.25);
      await iconCircle(s, ic, x + 0.3, y + 0.3);
      text(s, p, { x: x + 1.1, y: y + 0.3, w: 4.6, h: 0.62, fontFace: HEAD, fontSize: 18, bold: true, valign: "middle" });
      text(s, [
        { text: "Dampak  ", options: { bold: true, color: C.block, fontSize: 15 } }, { text: d, options: { fontSize: 15, color: C.ink2, breakLine: true } },
        { text: "Respons  ", options: { bold: true, color: C.pass, fontSize: 15 } }, { text: r, options: { fontSize: 15, color: C.ink2 } },
      ], { x: x + 1.1, y: y + 1.05, w: 4.65, h: 1.05, paraSpaceAfter: 10 });
    }
  }

  // ============================================================ 3. Tujuan
  {
    const s = light("Tujuan: email relevan yang setiap klaimnya bisa ditelusuri",
      "Tujuan (±1 menit). Kami tidak ingin satu agen memegang seluruh data dan semua keputusan. Empat prinsip: bukti sebelum klaim; " +
      "konteks tiap agen sempit; mobilitas agen diuji, bukan diasumsikan; manusia memegang keputusan kirim. Spreadsheet menjadi sumber state utama.");
    const pillars = [
      [L.FileSearch, "Bukti sebelum klaim", "Setiap fakta di email membawa sumber, waktu pengambilan, dan kutipan."],
      [L.Layers, "Konteks agen sempit", "Satu task terfokus per lead; agen bertukar JSON dan referensi, bukan riwayat percakapan."],
      [L.ArrowRightLeft, "Mobilitas diuji", "Agen riset/enrichment dapat berpindah runtime lewat checkpoint; manfaatnya diukur."],
      [L.UserCheck, "Manusia memutuskan", "Approval terikat versi draft; LLM tidak dapat membatalkan blokir aturan."],
    ];
    for (const [i, [ic, h, b]] of pillars.entries()) {
      const x = 0.6 + i * 3.08;
      card(s, x, 1.6, 2.88, 4.1);
      await iconCircle(s, ic, x + 0.3, 1.9, 0.8);
      text(s, h, { x: x + 0.3, y: 2.95, w: 2.4, h: 0.9, fontFace: HEAD, fontSize: 19, bold: true });
      text(s, b, { x: x + 0.3, y: 3.85, w: 2.35, h: 1.7, fontSize: 14, color: C.ink2 });
    }
    text(s, [{ text: "Sasaran rubrik: ", options: { bold: true } }, { text: "fungsi bisnis, integrasi AI (DL/LLM, ML, RL), UI/UX tiga langkah, dan mobile intelligent agents." }],
      { x: 0.6, y: 6.05, w: 12.1, h: 0.5, fontSize: 14, color: C.ink2 });
  }

  // ============================================================ 4. SOTA
  {
    const s = light("Posisi terhadap solusi yang ada",
      "SOTA (±1 menit). Clay, Apollo, HubSpot/Clearbit, dan ZoomInfo kuat sebagai ekosistem terpadu. Kami sengaja memakai tool terpisah " +
      "agar kontrak pesan, approval, dan eksperimen agen bisa diinspeksi. Landasan penelitian: AutoGen untuk pola multi-agent, ReAct untuk agen yang memakai tool, " +
      "Ditto untuk entity matching, FIPA Contract Net untuk negosiasi, dan Papaioannou & Edwards untuk mobile code.");
    const prod = [
      ["Clay", "Enrichment CRM terpadu dengan AI"], ["Apollo", "Waterfall enrichment, asisten tulis, sequence"],
      ["HubSpot / Clearbit", "Enrichment langsung di CRM"], ["ZoomInfo", "Data kontak dan perusahaan via API"],
    ];
    text(s, "Solusi komersial", { x: 0.6, y: 1.5, w: 6.5, h: 0.4, fontSize: 14, bold: true, color: C.tealM });
    prod.forEach(([n, d], i) => {
      const y = 1.95 + i * 0.86;
      card(s, 0.6, y, 6.5, 0.74);
      text(s, n, { x: 0.85, y, w: 2.2, h: 0.74, fontSize: 16, bold: true, valign: "middle" });
      text(s, d, { x: 3.05, y, w: 3.9, h: 0.74, fontSize: 14, color: C.ink2, valign: "middle" });
    });
    text(s, "Landasan penelitian", { x: 0.6, y: 5.5, w: 6.5, h: 0.4, fontSize: 14, bold: true, color: C.tealM });
    ["AutoGen", "ReAct", "Ditto", "FIPA Contract Net", "Mobile code"].forEach((c, i) => {
      const w = [1.1, 0.95, 0.85, 1.75, 1.35][i];
      const x = 0.6 + [0, 1.22, 2.29, 3.26, 5.13][i];
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.95, w, h: 0.46, rectRadius: 0.2, fill: { color: C.white }, line: { color: C.teal200, width: 1 } });
      text(s, c, { x, y: 5.95, w, h: 0.46, fontSize: 12.5, color: C.teal, bold: true, align: "center", valign: "middle" });
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.55, y: 1.5, w: 5.18, h: 4.95, rectRadius: 0.1, fill: { color: C.teal }, line: { color: C.teal },
      shadow: { type: "outer", blur: 10, offset: 3, angle: 90, color: "0C3136", opacity: 0.2 } });
    await iconCircle(s, L.Target, 7.9, 1.85, 0.7, C.amber, C.deep);
    text(s, "Posisi kami", { x: 8.8, y: 1.85, w: 3.7, h: 0.7, fontFace: HEAD, fontSize: 24, bold: true, color: C.white, valign: "middle" });
    text(s, [
      { text: "Kontrak pesan dan approval dapat diinspeksi", options: { bullet: true, breakLine: true } },
      { text: "State di spreadsheet milik tim, satu penulis", options: { bullet: true, breakLine: true } },
      { text: "Eksperimen mobilitas agen dengan checkpoint", options: { bullet: true, breakLine: true } },
      { text: "Tool terpisah: Apify, Firecrawl, OpenRouter, Gmail", options: { bullet: true } },
    ], { x: 7.95, y: 2.85, w: 4.55, h: 3.4, fontSize: 18, color: C.white, paraSpaceAfter: 14 });
  }

  // ============================================================ 5. Arsitektur
  {
    const s = light("Arsitektur: kontrol terpusat, agen spesialis, kirim dibatasi approval",
      "Arsitektur (±1,5 menit). Ikuti panah: pengguna mengisi campaign, orchestrator mendelegasikan ke agen enrichment, riset, dan writer. " +
      "Semua hasil diperiksa Security sebelum manusia menyetujui. Scheduler milik aplikasi yang memanggil Gmail API. Semua state lewat satu Data Gateway ke Google Sheets. " +
      "Tekankan: Apify dan Firecrawl adalah tool, bukan agen; respons Gmail bukan bukti email dibaca.");
    await frame(s, ASET("diagram-arsitektur.png"), 0.7, 1.5, { h: 5.25 });
    const pts = [
      ["Pisahkan keputusan bahasa dari kontrol", "LLM menulis dan merangkum; antrean, jadwal, dan kirim ditangani layanan deterministik."],
      ["Satu lead, satu alur", "Validasi → enrichment → riset → tulis → periksa → approval → kirim; banyak lead berjalan paralel."],
      ["Satu penulis state", "Data Gateway menulis batch ke 8 tab Google Sheets; agen tidak menulis langsung."],
    ];
    await note(s, pts, 7.0, 1.7, 5.7, 1.55);
  }

  // ============================================================ 6. Lima agen
  {
    const s = light("Lima agen dengan konteks sempit",
      "Agen (±1,5 menit). Orchestrator adalah broker. Enrichment dan Research bisa berpindah runtime. Writer tidak punya izin kirim. " +
      "Security adalah rule engine wajib; evaluator LLM tidak bisa membatalkan blokir. Yang bukan agen AI: Data Gateway, scheduler, sender, dan dispatcher.");
    const agents = [
      [L.Network, "Orchestrator", "Broker · statis", "Brief + state → rencana task dan alokasi runtime", "State machine, batas biaya, pemulihan"],
      [L.UserSearch, "Enrichment", "Worker · mobile", "Nama + petunjuk → kandidat, skor S, fakta profil", "Nama ambigu masuk review"],
      [L.Globe, "Research", "Scout · mobile", "Identitas → maks. 3 fakta web bersumber", "Kutipan harus ada di sumber"],
      [L.PenLine, "Email Writer", "Worker · statis", "Brief + fakta → subjek, isi, fact_id", "Maks. 2 revisi; tanpa izin kirim"],
      [L.ShieldCheck, "Security", "Rule engine · statis", "Kontak + draft → PASS / REVIEW / BLOCK", "Blokir tidak bisa dibatalkan LLM"],
    ];
    for (const [i, [ic, n, k, io, b]] of agents.entries()) {
      const x = 0.6 + i * 2.46;
      card(s, x, 1.55, 2.3, 4.55);
      await iconCircle(s, ic, x + 0.25, 1.8, 0.72);
      text(s, n, { x: x + 0.25, y: 2.65, w: 1.95, h: 0.45, fontFace: HEAD, fontSize: 18, bold: true });
      text(s, k, { x: x + 0.25, y: 3.08, w: 1.95, h: 0.35, fontSize: 12, color: C.tealM, bold: true });
      text(s, io, { x: x + 0.25, y: 3.5, w: 1.9, h: 1.35, fontSize: 13, color: C.ink2 });
      s.addShape(pres.shapes.LINE, { x: x + 0.25, y: 4.95, w: 1.8, h: 0, line: { color: C.teal200, width: 1 } });
      text(s, b, { x: x + 0.25, y: 5.05, w: 1.9, h: 0.9, fontSize: 12, color: C.ink3, italic: true });
    }
    text(s, [{ text: "Bukan agen AI: ", options: { bold: true, color: C.ink } }, { text: "Data Gateway, dispatcher, scheduler, Gmail sender, dan adapter layanan adalah kode terprogram." }],
      { x: 0.6, y: 6.3, w: 12.1, h: 0.45, fontSize: 14, color: C.ink2 });
  }

  // ============================================================ 7. Koordinasi & mobilitas
  {
    const s = light("Negosiasi Contract Net dan migrasi dengan checkpoint",
      "Koordinasi (±1,5 menit). Orchestrator mengirim CFP ke runtime yang memenuhi syarat, menerima proposal estimasi waktu, lalu memilih satu. " +
      "Migrasi memindahkan identitas, tujuan, state, dan referensi data. Setelah migrasi generation naik; hasil dari worker lama ditolak. " +
      "Di simulasi 100 lead ada 200 CFP, 200 PROPOSE, 100 ACCEPT, 100 REJECT, dan 2 migrasi A ke B yang selesai dari checkpoint.");
    await frame(s, ASET("diagram-contract-net.png"), 0.7, 1.5, { w: 6.7 });
    await frame(s, ASET("diagram-migrasi.png"), 0.7, 5.03, { w: 6.7 });
    const stats = [["1.012", "pesan antaragen dalam simulasi 100 lead"], ["200 / 100", "CFP terkirim / proposal diterima"], ["2", "migrasi A → B; hasil generation lama ditolak"]];
    stats.forEach(([n, l], i) => {
      const y = 1.6 + i * 1.62;
      card(s, 8.35, y, 4.38, 1.42);
      text(s, n, { x: 8.6, y: y + 0.12, w: 3.9, h: 0.72, fontFace: HEAD, fontSize: 34, bold: true, color: C.teal });
      text(s, l, { x: 8.6, y: y + 0.85, w: 3.95, h: 0.5, fontSize: 13, color: C.ink2 });
    });
    text(s, "Sumber angka: simulasi dengan layanan tiruan dan data fiktif.", { x: 8.35, y: 6.5, w: 4.4, h: 0.35, fontSize: 11, color: C.ink3, italic: true });
  }

  // ============================================================ 8. Entity linking
  {
    const s = light("Entity linking: agen tidak menebak identitas",
      "AI (±1,5 menit). Skor S menggabungkan kecocokan domain atau URL LinkedIn, kemiripan nama, perusahaan, dan jabatan. " +
      "Diterima otomatis hanya bila S minimal 0,85 dan unggul minimal 0,10 dari kandidat kedua. Di tangkapan layar, empat kandidat bernama Sinta punya skor di bawah 0,3, " +
      "sehingga pengguna yang memilih. Jelaskan juga pembagian metode: rule-based wajib, LLM untuk bahasa, classifier dan contextual bandit sebagai eksperimen.");
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.55, w: 5.6, h: 1.55, rectRadius: 0.1, fill: { color: C.teal }, line: { color: C.teal } });
    text(s, "S = 0,40d + 0,30n + 0,20c + 0,10r", { x: 0.8, y: 1.7, w: 5.3, h: 0.7, fontFace: HEAD, fontSize: 21, bold: true, color: C.white, valign: "middle", fit: "shrink" });
    text(s, "d domain/URL · n nama · c perusahaan · r jabatan (0–1)", { x: 0.85, y: 2.45, w: 5.0, h: 0.45, fontSize: 13, color: C.teal200 });
    text(s, [
      { text: "Terima bila ", options: {} }, { text: "S ≥ 0,85", options: { bold: true } }, { text: " dan unggul ", options: {} },
      { text: "≥ 0,10", options: { bold: true } }, { text: "; selain itu review manusia.", options: {} },
    ], { x: 0.6, y: 3.3, w: 5.4, h: 0.7, fontSize: 15, color: C.ink2 });
    const methods = [
      [L.ListChecks, "Rule-based", "Wajib: izin, suppression, duplikat, jadwal"],
      [L.MessageSquareText, "DL / LLM", "OpenRouter, keluaran JSON sesuai skema"],
      [L.GitCompare, "ML", "Classifier pasangan entitas (eksperimen)"],
      [L.Dices, "RL", "Contextual bandit alokasi worker (offline)"],
    ];
    for (const [i, [ic, h, b]] of methods.entries()) {
      const y = 4.1 + i * 0.66;
      await iconCircle(s, ic, 0.6, y, 0.5, C.teal50, C.teal);
      text(s, [{ text: h + "  ", options: { bold: true, color: C.ink } }, { text: b, options: { color: C.ink2 } }], { x: 1.25, y, w: 4.8, h: 0.5, fontSize: 13.5, valign: "middle" });
    }
    await frame(s, IMG("review-identitas.png"), 6.6, 1.55, { w: 6.1 });
  }

  // ============================================================ 9. Divider prototipe
  {
    const s = dark("Transisi ke demo prototipe (±20 detik). Sebutkan stack dan bahwa semua tangkapan layar berikut diambil dari mode simulasi dengan data fiktif. " +
      "Kalau waktu memungkinkan, lakukan demo langsung dari laptop.");
    text(s, "Dari rancangan ke prototipe", { x: 0.7, y: 2.05, w: 11.9, h: 1.0, fontFace: HEAD, fontSize: 44, bold: true, color: C.white });
    text(s, "Prototipe fungsional berjalan dari ujung ke ujung: Setup → Preview & Approval → Monitor.", { x: 0.7, y: 3.15, w: 11.5, h: 0.6, fontSize: 20, color: C.teal200 });
    const chips = ["FastAPI", "React + TypeScript", "OpenRouter · Claude Sonnet 5", "Apify", "Firecrawl", "Google Sheets", "Gmail API"];
    let x = 0.7;
    chips.forEach((c) => {
      const w = 0.32 + c.length * 0.092;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 4.2, w, h: 0.5, rectRadius: 0.22, fill: { color: C.teal }, line: { color: C.tealM, width: 1 } });
      text(s, c, { x, y: 4.2, w, h: 0.5, fontSize: 12.5, bold: true, color: C.white, align: "center", valign: "middle" });
      x += w + 0.14;
    });
    text(s, "Tangkapan layar: mode simulasi, data fiktif (.example).", { x: 0.7, y: 5.2, w: 8, h: 0.4, fontSize: 13, color: C.amber, italic: true });
  }

  // ============================================================ 10. Setup
  {
    const s = light("Setup: satu orang atau banyak lead",
      "Setup (±1 menit). Pengguna memilih mode: satu orang (dikunci sistem untuk tepat satu penerima) atau banyak lead lewat CSV. " +
      "Lead manual cukup nama lengkap dan deskripsi, misalnya Azhari, dosen dan guru besar di UGM; agen membaca instansi dan peran sebagai petunjuk pencarian. " +
      "Panel kanan menunjukkan kesiapan setiap layanan.");
    await frame(s, IMG("setup.png"), 0.7, 1.5, { h: 5.3 });
    await note(s, [
      ["Pilih mode penerima", "Satu orang dikunci di tiga lapis: tambah lead, approval, dan scheduler."],
      ["Brief campaign", "Tujuan, penawaran, CTA, personalisasi, dan anggaran LLM."],
      ["Lead manual atau CSV", "Nama + deskripsi sudah cukup; email boleh menyusul."],
      ["Kesiapan layanan", "Status OpenRouter, Apify, Firecrawl, Sheets, dan Gmail."],
    ], 8.0, 1.65, 4.75, 1.3);
  }

  // ============================================================ 11. Preview & Approval
  {
    const s = light("Preview & Approval: setiap klaim punya jejak bukti",
      "Preview (±1,5 menit). Daftar kiri menunjukkan keputusan Security per lead. Draft untuk Sinta Pramesti memakai dua fakta; kata yang berasal dari fakta diberi nomor " +
      "yang merujuk ke jejak bukti di bawah: sumber, waktu, skor identitas. Approval terikat versi; kalau draft diedit, approval lama batal. " +
      "Email hanya terkirim ke alamat di allowlist.");
    await frame(s, IMG("preview-approval.png"), 0.7, 1.45, { h: 5.4 });
    await note(s, [
      ["Keputusan per lead", "Siap disetujui, perlu review, atau diblokir, lengkap dengan alasannya."],
      ["Jejak bukti bernomor", "Fakta di email merujuk ke sumber CRM, Apify, atau web beserta waktunya."],
      ["Approval terikat versi", "Edit draft membatalkan approval dan memicu pemeriksaan ulang."],
      ["Kirim terkendali", "Kunci kirim, allowlist, dan status SENT_UNKNOWN bila hasil tidak pasti."],
    ], 7.15, 1.6, 5.6, 1.3);
  }

  // ============================================================ 12. Monitor
  {
    const s = light("Monitor: agen, migrasi, dan pesan terlihat langsung",
      "Monitor (±1 menit). Bagian atas menunjukkan alur task per tahap. Runtime A dan B beserta riwayat migrasi. Panel kanan memuat pemakaian layanan " +
      "dan pesan antaragen yang mengalir langsung: CFP, PROPOSE, INFORM_RESULT, keputusan Security, approval, dan kiriman.");
    await frame(s, IMG("monitor.png"), 0.7, 1.45, { h: 5.4 });
    const stats = [["87", "lead diputuskan"], ["13", "menunggu review identitas"], ["1.012", "pesan antaragen"], ["2", "migrasi A → B"]];
    stats.forEach(([n, l], i) => {
      const y = 1.55 + i * 1.3;
      text(s, n, { x: 7.25, y, w: 2.3, h: 0.9, fontFace: HEAD, fontSize: 40, bold: true, color: C.teal, valign: "middle" });
      text(s, l, { x: 9.55, y, w: 3.2, h: 0.9, fontSize: 15, color: C.ink2, valign: "middle" });
    });
    text(s, "Simulasi 100 lead fiktif; 76 lolos, 14 review, 10 blokir.", { x: 7.25, y: 6.45, w: 5.5, h: 0.35, fontSize: 11, color: C.ink3, italic: true });
  }

  // ============================================================ 13. Mode draf & mobile
  {
    const s = light("Tetap berguna tanpa Gmail: mode draf",
      "Mode draf (±1 menit). Kalau Google Client ID dan Secret belum diisi, aplikasi tetap berjalan. Semua agen bekerja, tetapi keluarannya berupa isi email: " +
      "difinalkan lalu disalin atau diunduh sebagai .eml, atau diekspor CSV untuk seluruh campaign. Pengaman izin, grounding, dan review identitas tetap berlaku. " +
      "Tampilan juga responsif sampai layar ponsel.");
    await frame(s, IMG("mode-draf-final.png"), 0.7, 1.5, { w: 6.5 });
    await frame(s, IMG("mode-draf-koneksi.png"), 0.7, 5.4, { w: 6.5 });
    await frame(s, ASET("mobile-atas.png"), 10.5, 1.5, { h: 5.3 });
    text(s, [
      { text: "Finalkan, salin, unduh", options: { bold: true, fontSize: 17, color: C.ink, breakLine: true } },
      { text: "Tanpa antrean kirim; email penerima opsional.", options: { fontSize: 13.5, color: C.ink2, breakLine: true } },
      { text: " ", options: { fontSize: 8, breakLine: true } },
      { text: "Responsif", options: { bold: true, fontSize: 17, color: C.ink, breakLine: true } },
      { text: "Diuji pada 1440 px dan 390 px.", options: { fontSize: 13.5, color: C.ink2 } },
    ], { x: 7.55, y: 1.6, w: 2.7, h: 4.5 });
  }

  // ============================================================ 14. Keamanan
  {
    const s = light("Keamanan berlapis, diuji otomatis",
      "Keamanan (±1 menit). Enam lapisan. Lima sudah diuji otomatis: izin dan suppression, halaman web berisi prompt injection dibuang dan dicatat, " +
      "approval dan jadwal, task ulang dan migrasi, kegagalan Gmail dengan transport tiruan. Audit dan retensi data belum diuji. Rujukan: OWASP LLM01 dan UU PDP, tanpa klaim sudah diaudit.");
    const layers = [
      [L.KeyRound, "Identitas & izin", "Hanya kontak berizin dan bukan suppression; kredensial tidak masuk spreadsheet.", true],
      [L.Bug, "Konten web", "Instruksi mencurigakan dibuang dan dicatat sebagai insiden.", true],
      [L.CalendarCheck, "Approval & jadwal", "Edit membatalkan approval; suppression dicek ulang sebelum kirim.", true],
      [L.RefreshCw, "Task ulang & migrasi", "Kunci kirim mencegah duplikasi; generation lama ditolak.", true],
      [L.MailWarning, "Kegagalan Gmail", "Timeout menjadi SENT_UNKNOWN, tidak dikirim ulang otomatis.", true],
      [L.Archive, "Audit & retensi", "Log tanpa rahasia ada; kebijakan retensi belum diuji.", false],
    ];
    for (const [i, [ic, h, b, ok]] of layers.entries()) {
      const x = 0.6 + (i % 3) * 4.1;
      const y = 1.55 + Math.floor(i / 3) * 2.55;
      card(s, x, y, 3.9, 2.3, ok ? C.teal50 : C.amber50);
      await iconCircle(s, ic, x + 0.28, y + 0.28, 0.62);
      text(s, h, { x: x + 1.05, y: y + 0.28, w: 2.7, h: 0.62, fontFace: HEAD, fontSize: 17, bold: true, valign: "middle" });
      text(s, b, { x: x + 0.28, y: y + 1.05, w: 3.4, h: 0.85, fontSize: 13, color: C.ink2 });
      text(s, ok ? "Diuji otomatis" : "Belum diuji", { x: x + 0.28, y: y + 1.85, w: 3.4, h: 0.32, fontSize: 12, bold: true, color: ok ? C.pass : C.review });
    }
  }

  // ============================================================ 15. Hasil
  {
    const s = light("Hasil: 43 tes lulus dan simulasi 100 lead",
      "Hasil (±1,5 menit). 43 tes otomatis lulus; tes ditulis dari kebutuhan laporan, bukan menyalin implementasi. Simulasi 100 lead fiktif: " +
      "76 PASS, 14 REVIEW (13 identitas ambigu, 1 prompt injection), 10 BLOCK (7 tanpa izin, 2 email invalid, 1 duplikat). " +
      "Tegaskan batas: layanan tiruan dan data fiktif, sehingga waktu proses bukan ukuran kinerja nyata.");
    text(s, "43 / 43", { x: 0.6, y: 1.45, w: 3.2, h: 0.95, fontFace: HEAD, fontSize: 48, bold: true, color: C.teal });
    text(s, "tes otomatis lulus", { x: 3.45, y: 1.62, w: 2.6, h: 0.7, fontSize: 16, color: C.ink2, valign: "middle" });
    s.addChart(pres.charts.BAR, [{
      name: "Tes", labels: ["Integrasi", "Agen", "Orchestrator", "Lead manual", "LinkedIn", "Mode draf", "Satu penerima", "API"],
      values: [10, 9, 7, 6, 4, 4, 2, 1],
    }], {
      x: 0.5, y: 2.45, w: 6.0, h: 4.35, barDir: "bar", chartColors: [C.teal], showValue: true, dataLabelPosition: "outEnd",
      dataLabelColor: C.ink, dataLabelFontSize: 12, dataLabelFontFace: BODY, catAxisLabelColor: C.ink2, catAxisLabelFontSize: 13,
      catAxisLabelFontFace: BODY, valAxisHidden: true,
      valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, catAxisOrientation: "maxMin", barGapWidthPct: 45,
    });
    s.addChart(pres.charts.DOUGHNUT, [{ name: "Keputusan", labels: ["PASS", "REVIEW", "BLOCK"], values: [76, 14, 10] }], {
      x: 6.85, y: 1.45, w: 3.4, h: 3.4, holeSize: 58, chartColors: [C.pass, C.amber, C.block], showValue: true, showPercent: false,
      dataLabelColor: C.white, dataLabelFontSize: 14, dataLabelFontFace: BODY, dataLabelFontBold: true, showLegend: false,
    });
    text(s, [
      { text: "76 PASS", options: { bold: true, color: C.pass, breakLine: true } }, { text: "siap disetujui", options: { color: C.ink2, fontSize: 12.5, breakLine: true } },
      { text: "14 REVIEW", options: { bold: true, color: C.review, breakLine: true } }, { text: "13 identitas ambigu, 1 prompt injection", options: { color: C.ink2, fontSize: 12.5, breakLine: true } },
      { text: "10 BLOCK", options: { bold: true, color: C.block, breakLine: true } }, { text: "7 tanpa izin, 2 email invalid, 1 duplikat", options: { color: C.ink2, fontSize: 12.5 } },
    ], { x: 10.4, y: 1.6, w: 2.4, h: 3.3, fontSize: 16, paraSpaceAfter: 3 });
    card(s, 6.85, 5.35, 5.9, 1.3);
    text(s, [
      { text: "Batas bukti  ", options: { bold: true, color: C.ink } },
      { text: "Simulasi memakai layanan tiruan dan data fiktif. Rata-rata persiapan 2,7 detik per lead (p95 3,2 detik) mencerminkan latensi buatan, bukan kinerja nyata.", options: { color: C.ink2 } },
    ], { x: 7.1, y: 5.5, w: 5.45, h: 1.05, fontSize: 13 });
  }

  // ============================================================ 16. Keterbatasan & lanjut
  {
    const s = light("Keterbatasan dan langkah berikutnya",
      "Penutup teknis (±1 menit). Jujur tentang yang belum diuji: kualitas email dari LLM sungguhan, run nyata actor Apify, pengiriman Gmail ke penerima nyata, " +
      "dan pembandingan A/B/C. Langkah berikutnya memakai mode satu penerima dan mode draf supaya uji live tetap aman dan murah.");
    const cols = [
      [L.CircleDashed, "Belum diuji", C.amber50, C.review, [
        "Kualitas bahasa email dari LLM sungguhan (penilaian manusia blind)",
        "Run nyata actor Apify dan pemetaan keluarannya",
        "Pengiriman Gmail ke penerima nyata",
        "Pembandingan A/B/C dengan 10 pengulangan (Bagian 9.1)",
        "Runtime A/B masih dalam satu proses (mobilitas logis)",
      ]],
      [L.Rocket, "Langkah berikutnya", C.teal50, C.teal, [
        "Uji live terbatas: mode satu penerima + mode draf",
        "Label 1.000 pasangan entitas untuk menguji skor S dan classifier",
        "Jalankan evaluasi A/B/C: waktu, p95, biaya per email, kualitas",
        "Dua runtime di mesin terpisah untuk uji mobilitas nyata",
        "Kebijakan retensi data sebelum memakai data nyata",
      ]],
    ];
    for (const [i, [ic, h, bg, fg, items]] of cols.entries()) {
      const x = 0.6 + i * 6.15;
      card(s, x, 1.55, 5.95, 5.2, bg);
      await iconCircle(s, ic, x + 0.3, 1.85, 0.7, fg);
      text(s, h, { x: x + 1.2, y: 1.85, w: 4.4, h: 0.7, fontFace: HEAD, fontSize: 22, bold: true, valign: "middle" });
      text(s, items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
        { x: x + 0.35, y: 2.85, w: 5.3, h: 3.75, fontSize: 17, color: C.ink2, paraSpaceAfter: 14 });
    }
  }

  // ============================================================ 17. Kesimpulan
  {
    const s = dark("Kesimpulan (±45 detik). Tiga poin: agen spesialis dengan konteks sempit membuat hasil dapat ditelusuri; manusia tetap memegang keputusan kirim; " +
      "prototipe membuktikan alur ujung ke ujung dengan pengaman yang teruji. Tutup dengan ajakan tanya jawab.");
    text(s, "Kesimpulan", { x: 0.7, y: 0.75, w: 8, h: 0.8, fontFace: HEAD, fontSize: 36, bold: true, color: C.white });
    const pts = [
      [L.FileSearch, "Dapat ditelusuri", "Setiap klaim email membawa sumber, waktu, dan kutipan."],
      [L.UserCheck, "Manusia memutuskan", "Approval terikat versi; aturan keamanan tidak bisa dibatalkan LLM."],
      [L.CheckCheck, "Terbukti berjalan", "Prototipe ujung ke ujung; 43 tes lulus; simulasi 100 lead."],
    ];
    for (const [i, [ic, h, b]] of pts.entries()) {
      const x = 0.7 + i * 4.05;
      await iconCircle(s, ic, x, 1.95, 0.8, C.amber, C.deep);
      text(s, h, { x, y: 2.95, w: 3.7, h: 0.55, fontFace: HEAD, fontSize: 21, bold: true, color: C.white });
      text(s, b, { x, y: 3.5, w: 3.6, h: 1.0, fontSize: 15, color: C.teal200 });
    }
    s.addShape(pres.shapes.LINE, { x: 0.7, y: 4.95, w: 11.9, h: 0, line: { color: C.tealM, width: 1 } });
    text(s, "Terima kasih — sesi tanya jawab", { x: 0.7, y: 5.25, w: 7.5, h: 0.7, fontFace: HEAD, fontSize: 28, bold: true, color: C.amber });
    text(s, "Repositori: github.com/adityanrrhmn/agen-cerdas-enterprise (privat)", { x: 0.7, y: 6.0, w: 7.5, h: 0.4, fontSize: 14, color: C.teal200 });
    text(s, [
      { text: "Aditya · Leader & Evaluator", options: { breakLine: true } }, { text: "Amar · Presenter", options: { breakLine: true } },
      { text: "Syakirah · Programmer", options: { breakLine: true } }, { text: "Amelia · Designer", options: { breakLine: true } },
      { text: "Jovi · Researcher" },
    ], { x: 9.35, y: 5.2, w: 3.3, h: 1.8, fontSize: 13, color: C.white, align: "right", paraSpaceAfter: 2 });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("Deck ditulis:", OUT, "| slide:", page);
}

main().catch((e) => { console.error(e); process.exit(1); });
