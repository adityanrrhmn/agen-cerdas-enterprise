# Ruang kerja robot agen

Ditambahkan 29 September 2026. Aset robot 3D transparan dibuat dengan **imagegen bawaan**, lalu dipakai ulang
untuk lima peran dengan variasi warna CSS. Meja, laptop, kursi, lantai, dan dekorasi dibuat dengan CSS.
Gerak berupa ayunan/naik-turun seluruh robot dan animasi layar; belum berupa rig tangan atau model 3D interaktif.

## Coba tanpa layanan berbayar

Dari folder `frontend`, jalankan:

```powershell
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5176 --strictPort
```

Buka `http://127.0.0.1:5176/agent-office.html`, lalu klik **Submit data contoh**.
Demo berjalan otomatis 3,2 detik per tahap dan berhenti pada review manusia. Reset mengembalikan semua robot
ke keadaan siap. Klik robot untuk melihat tugasnya. **Jeda animasi** hanya menghentikan gerakan visual,
bukan pekerjaan campaign. Preferensi sistem `prefers-reduced-motion` juga dihormati.
Halaman demo adalah entry Vite untuk pengembangan; build produksi utama berisi panel Monitor.

## Sudah terpasang di aplikasi

Panel tampil di tab **Monitor**. Setelah **Jalankan agen** di Setup, aplikasi membuka Monitor.
Upload/submit data saja tidak memulai layanan: pekerjaan dimulai lewat tombol Jalankan agen.
Ketika draf tersedia, pengguna tetap membuka **Preview & Approval / Finalisasi** untuk meninjaunya.

Monitor mengambil lead campaign aktif setiap 1,5 detik. Fungsi `officeStates()` mengubah status backend
menjadi status visual; komponen `AgentOffice` hanya menampilkan hasilnya. Tidak ada timer demo yang
dipakai untuk mengarang kemajuan campaign sungguhan.

| Robot | Sumber aktivitas | Gerakan/indikator |
|---|---|---|
| Orchestrator | Ada task RUNNING | Ayunan, indikator membagi pekerjaan |
| Enrichment | Lead enrichment dan task RUNNING | Ayunan, ikon identitas berdenyut |
| Research | Lead research dan task RUNNING | Ayunan, kaca pembesar bergerak |
| Writer | Lead writing dan task RUNNING | Ayunan, baris layar berkedip |
| Security | Stage security/validate; event keputusan untuk lead campaign ini | Pemeriksaan; hasil event diberi label “Baru memeriksa” selama 4 detik |

Status checkpoint seperti `enriched` bukan bukti agen masih bekerja. Task HELD ditandai tertahan.
Campaign PAUSED menghentikan gerakan dan menampilkan label jeda; kegagalan pengambilan data menampilkan
status tidak tersedia. Campaign selesai tidak ditampilkan bekerja. Menunggu persetujuan manusia diberi label
tersendiri, tidak memicu approval atau pengiriman. Tahap sangat singkat dapat terlewat di antara polling;
indikator ini bukan visualisasi setiap panggilan tool atau persentase kemajuan.

## Berkas yang bisa dipakai ulang

- `frontend/public/agents/robot-teal.png`: master PNG transparan, 1280 × 1280.
- `frontend/src/components/AgentOffice.tsx`: susunan ruangan, robot, klik detail, kontrol animasi.
- `frontend/src/components/agent-office.css`: properti warna, posisi, furnitur, animasi, layout mobile.
- `frontend/src/components/office-state.ts`: nama/jobdesk dan pemetaan data ke status visual.
- `frontend/src/office-demo.tsx` dan `frontend/agent-office.html`: demo lokal tanpa backend.

Untuk memasang di halaman React lain:

```tsx
import AgentOffice from "./components/AgentOffice";
import { officeStates } from "./components/office-state";

// summary, leads, dan events berasal dari API campaign milik halaman ini.
const states = officeStates(summary, leads, events, Date.now(), hasFetchError);
return <AgentOffice states={states} />;
```

Salin juga PNG ke folder `public/agents`. Nama dan jobdesk diedit di `AGENTS` dalam `office-state.ts`.
Ubah `hue` untuk warna robot, `color` untuk warna stasiun, `office-work` untuk intensitas gerak.
PNG tunggal memungkinkan aset yang sama di-cache browser untuk kelima robot.

## Memeriksa integrasi secara aman

Backend preview memakai objek Settings kosong dan adapter simulasi, tanpa membaca `.env` atau token pengguna.
Data disimpan dalam direktori sementara baru setiap kali dijalankan. Dari root repo:

```powershell
backend/.venv/Scripts/python tools/preview-agent-office.py
```

Di terminal kedua, dari folder `frontend`:

```powershell
$env:API_TARGET = 'http://127.0.0.1:8006'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5177 --strictPort
```

Buka `http://127.0.0.1:5177`, buat campaign, tambah data contoh, lalu jalankan agen.
Preview menggunakan mode draf dan tidak mengirim email. Tutup proses preview sendiri dengan Ctrl+C setelah selesai.

## Verifikasi

- TypeScript: `node node_modules/typescript/bin/tsc -b` dari frontend.
- Build: `node node_modules/vite/bin/vite.js build` dari frontend.
- Status: `node --experimental-strip-types --test tests/office-state.test.mjs` dari frontend; Node 22.20+.
- Backend: `.venv/Scripts/python -m pytest -q` dari backend.
- Screenshot: `node tools/screenshot.mjs http://127.0.0.1:5177 .impeccable/agent-office monitor-desktop=1440x1000@/?tab=monitor monitor-mobile=390x844@/?tab=monitor` dari root.

Hasil verifikasi final dicatat di runbook aplikasi. Perintah Node langsung digunakan karena launcher npx lokal
menunjuk `npx-cli.js` yang tidak ditemukan; tidak diperlukan pemasangan paket baru.

## Prompt aset (imagegen bawaan)

Use case: stylized-concept. Asset type: reusable transparent PNG character for a React miniature AI office dashboard. Create ONE adorable premium 3D toy robot, full body, white rounded ceramic shell, small teal accents, glossy dark navy face visor, two friendly glowing turquoise eyes, little antenna, stubby arms with hands posed forward typing at an invisible keyboard, seated posture with tiny feet visible, no chair. Three-quarter front view from slightly above, face visible, soft warm studio light, subtle ambient occlusion, polished clay-render style like an architectural miniature office. Centered single character occupies 85 percent of square frame, ample transparent padding around all limbs, actual transparent background. No floor, desk, laptop, chair, props, text, logos, watermark, environment or hard rectangular shadow. This character will be layered over CSS desks and animated gently with CSS transforms. Beautiful clean silhouette, high quality 3D render.
