# Runbook prototipe Outreach Control

Terakhir diverifikasi: 2026-09-17 (Windows 11, Python 3.11.9, Node 24.16, FastAPI 0.141, React 19, Vite 8).

## Menjalankan

```powershell
powershell -ExecutionPolicy Bypass -File run-dev.ps1   # backend :8000 + dashboard :5173, lalu membuka browser
```

Manual: `backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000` (dari `backend/`) dan `npm run dev`
(dari `frontend/`). Setelah `npm run build`, backend juga menyajikan UI di `http://127.0.0.1:8000`; bila memakai itu,
ubah `APP_URL` ke alamat tersebut agar login Google kembali ke tempat yang benar. Setelah mengubah `.env`, restart backend.

## Peta komponen

| Komponen | File | Peran (laporan) |
|---|---|---|
| Konfigurasi | `backend/app/config.py` | Membaca `.env`; status "terisi/kurang" tanpa membocorkan nilai |
| Data Gateway | `backend/app/store.py` | Single-writer §7.1; cache memori, flush batch ke Sheets (8 tab) atau file lokal |
| Auth Google | `backend/app/google_auth.py` | Service account (Sheets); OAuth + PKCE dengan tombol Hubungkan (Gmail) |
| Adapter | `backend/app/integrations.py` | OpenRouter (structured output), Apify run-sync, Firecrawl `/v2/search`, Gmail send; kelas simulasi |
| Agen | `backend/app/agents.py` | Enrichment (entity linking S §6.1), Research (grounding + filter injection), Writer (maks. 2 revisi), Security (rule engine) |
| Orchestrator | `backend/app/orchestrator.py` | State machine per lead, Contract Net ke runtime A/B, checkpoint/lease/generation, approval hash, pemulihan |
| Scheduler | `backend/app/scheduler.py` | Jendela kirim bertahap; cek hash approval, suppression, allowlist; `SENDING` disimpan sebelum kirim; `SENT_UNKNOWN` |
| API | `backend/app/main.py` | REST + SSE `/api/events`; semua endpoint `async` |
| Dashboard | `frontend/src/pages/{Setup,Review,Monitor,Connections}.tsx` | Setup → Preview & Approval → Monitor, ditambah Koneksi |
| Data fiktif | `backend/scripts/generate_fictitious_data.py` → `backend/data/leads_fiktif.csv`, `simulasi.json` | 100 lead `.example`, 20 kasus uji; `linkedin_url` sengaja kosong |

## Mode draf (tanpa Gmail)

`Settings.draft_only`: `DELIVERY_MODE=draft`, atau `auto` (default) dengan `GOOGLE_CLIENT_ID/SECRET` kosong dan tanpa
simulasi. Dampaknya: approve menghasilkan status `FINAL` (bukan `APPROVED`); email penerima opsional (`no_email` = info)
dan peringatan allowlist tidak muncul; scheduler tidak mengirim. Campaign otomatis COMPLETED bila semua email final
(termasuk `FINAL`). Unduhan: `GET /api/emails/{send_key}/eml` (header `X-Unsent: 1`, dibuka sebagai draf baru di klien
email) dan `GET /api/campaigns/{id}/export.csv` (UTF-8 BOM untuk Excel). Draf `FINAL` bisa diedit (pemeriksaan dibuka
lagi), dan bisa disetujui untuk dikirim bila nanti mode berubah ke kirim.

## Mode satu penerima

Pilihan "Satu orang" di form campaign (`single_recipient`, opsional `send_now`). Backend memaksa `count=1`,
`cadence=once`, `max_recipients=1`; `send_now` mengisi jadwal = saat campaign dibuat (terkirim di tick scheduler
berikutnya setelah disetujui, dengan syarat Gmail terhubung, `GMAIL_SEND_ENABLED=true`, penerima di allowlist).
Kuota dijaga berlapis: tambah lead kedua ditolak; approval untuk alamat lain ditolak bila kuota terpakai
(status APPROVED/SENDING/SENT/SENT_UNKNOWN); scheduler memblokir alamat lain bila sudah ada kiriman. Campaign
otomatis COMPLETED setelah satu-satunya email final.

## Lead manual (nama + deskripsi)

Form "Tambah lead manual" di Setup (`POST /api/campaigns/{id}/leads`). Nama lengkap dan deskripsi wajib; email, instansi,
URL LinkedIn opsional; izin kontak harus dicentang (tanpa izin = BLOCK). Hanya untuk campaign berstatus DRAFT.
- `ProfileHintAgent` (LLM) mengekstrak instansi + singkatan + peran dari deskripsi ke kolom `hints`. Petunjuk hanya dipakai
  untuk skor identitas dan query riset, **tidak** menjadi fakta email. Deskripsi itu sendiri menjadi fakta `crm`
  bersumber `input://pengguna/<lead_id>`.
- Riset mode orang: query `"<nama>" "<instansi>"`; halaman wajib menyebut nama **dan** alias instansi; prompt melarang data
  pribadi sensitif. Nama umum tanpa LinkedIn tetap REVIEW (identitas tidak terverifikasi).
- Email kosong = REVIEW `no_email`; approve ditolak sampai email diisi di panel review (`PUT /api/leads/{id}/email`),
  yang memeriksa ulang draft dan menaikkan versi.

## Alur data lead

1. **Validasi (Security):** email valid, `permission_status=granted`, tidak ada di suppression, tidak duplikat. Gagal = BLOCK tanpa biaya.
2. **Enrichment (runtime A/B):** Apify hanya dipanggil bila placeholder template terisi. Untuk actor
   `anchor~linkedin-profile-enrichment`, lead tanpa `linkedin_url` dilewati. Kandidat dinilai dengan S. Kalau ambigu,
   lead masuk review identitas.
3. **Riset (runtime A/B):** hasil Firecrawl dibuang bila memuat pola injection (dicatat sebagai insiden) atau tidak
   menyebut perusahaan lead. Kutipan fakta dari LLM harus ada persis di halaman sumber. Maksimal 3 fakta dipilih.
4. **Tulis + periksa (core):** anggaran LLM dicek dulu. Security menandai REVIEW bila ada angka yang tidak didukung
   fakta, fact_id tidak dikenal, peringatan writer, galat integrasi, atau identitas belum terverifikasi.
5. **Approval:** terikat hash (penerima, subjek, isi, versi, konfigurasi campaign). Mengedit draft membatalkan approval.
   REVIEW hanya bisa disetujui per item dengan centang konfirmasi.
6. **Kirim:** hanya bila akun Google terhubung, `GMAIL_SEND_ENABLED=true`, dan penerima ada di `GMAIL_ALLOWLIST`.

## Status verifikasi (2026-09-17)

| Hal | Status | Bukti |
|---|---|---|
| Logika agen, orchestrator, migrasi, scheduler, lead manual, mode satu penerima, mode draf | Lulus | 43 tes pytest |
| Bentuk request OpenRouter/Apify/Firecrawl/Gmail/Sheets/OAuth | Lulus (transport tiruan) | `tests/test_integrations.py`, `tests/test_linkedin_enrichment.py` |
| Key OpenRouter, token Apify, key Firecrawl, akses Sheets | Lulus (live, tanpa biaya) | Tes di tab Koneksi; tab Sheets dibuat |
| Alur ujung ke ujung via API + UI | Lulus di **simulasi** | 40 lead: 29 lolos, 6 review, 5 blokir; migrasi A→B gen 2 |
| Tampilan desktop 1440 / mobile 390 | Lulus, 2 putaran | `.impeccable/review/*.png`; detektor desain: 0 temuan |
| Campaign dengan LLM/Firecrawl/Apify live | **Belum dijalankan** | Memakai kredit; tunggu persetujuan pengguna |
| Hubungkan Gmail dan kirim sungguhan | **Belum dijalankan** | Perlu login pengguna di browser |
| Skema output actor Apify | Dipetakan dari skema publik, **belum diuji dengan run nyata** | Build `Gw5UqNxzSnDAGYAwj` |

## Verifikasi tampilan tanpa biaya

```bash
# backend simulasi di :8001 (key dikosongkan hanya untuk proses ini; .env tidak berubah)
cd backend && OPENROUTER_API_KEY= APIFY_TOKEN= FIRECRAWL_API_KEY= GOOGLE_CLIENT_ID= GOOGLE_CLIENT_SECRET= \
  GOOGLE_SERVICE_ACCOUNT_FILE= SIMULATE_INTEGRATIONS=true DATA_BACKEND=local \
  .venv/Scripts/python -m uvicorn app.main:app --port 8001
cd frontend && API_TARGET=http://127.0.0.1:8001 npx vite --port 5174
node tools/screenshot.mjs http://localhost:5174 .impeccable/review desktop-review=1440x1000@/?tab=review mobile-review=390x844@/?tab=review
```

Hapus `backend/data/local-store.json` setelah selesai. Skrip screenshot melaporkan `OVERFLOW` bila ada scroll horizontal.

## Ruang kerja robot (2026-09-29)

Panel robot ditambahkan di Monitor: PNG transparan + animasi CSS untuk lima peran, mengikuti lead campaign
aktif dan event Security. Panduan aset, pemetaan status, serta demo tanpa biaya: [agent-office.md](agent-office.md).
Demo visual di `/agent-office.html` pada server Vite; tidak memanggil backend. Backend preview aman tersedia
melalui `tools/preview-agent-office.py` (port 8006, mode simulasi/draf, tanpa membaca `.env`).

Verifikasi penambahan panel: **lulus** TypeScript dan build Vite; **lulus** 4 tes status visual;
**lulus** 45 tes backend; **lulus** pemeriksaan screenshot demo dan Monitor dengan backend simulasi
pada lebar 1440 dan 390, tanpa overflow horizontal. Bukti: `.impeccable/agent-office/`.
Tes koneksi layanan live **dilewati**, karena perubahan hanya presentasi dan sudah diperiksa memakai adapter simulasi.
Laporan `.docx` tidak diubah; pemeriksaan laporan **dilewati**.

## Masalah umum (operasional)

### Desain halaman terbuka (2026-09-29)

Koreksi pengguna: tampilan seluruh aplikasi terlalu berupa kotak. `frontend/src/styles/studio.css` memberi gaya bersama
untuk shell, Setup, Review, Monitor, dan Koneksi; diimpor dari `main.tsx` setelah `styles/base.css`, lalu
`styles/dark.css` (mode gelap lewat `data-theme` di `<html>`, dipasang sebelum render di `index.html`, tersimpan di
`localStorage.theme`). Warna mengikuti logo (master: `docs/gambar/logo.png`). Komponen robot/demo mandiri tetap
memakai stylesheet sendiri. Setup mendapat panduan tahap; Review memisahkan surat dan bukti; rincian runtime,
pemakaian, dan log Monitor tersedia lewat **Di balik layar**. Semua kontrol tetap tersedia.

Verifikasi: **lulus** TypeScript, build produksi, 45 tes backend, dan 4 tes status robot.
Screenshot empat halaman pada 1440/390: **lulus**, tanpa overflow horizontal halaman
(`.impeccable/studio-review/`). Pemeriksaan memakai backend simulasi khusus port 8006 dan frontend 5177.
Tes layanan live **dilewati** (perubahan UI); pemeriksaan laporan **dilewati** (.docx tidak diubah).

### Operasional layanan

| Gejala | Penyebab / tindakan |
|---|---|
| Sheets 403 | Spreadsheet belum di-share ke email service account (terlihat di tab Koneksi) sebagai Editor |
| "Koneksi Google kedaluwarsa" | OAuth app berstatus Testing: token berlaku 7 hari. Klik Hubungkan lagi |
| Semua lead per_lead masuk REVIEW "tidak terverifikasi" | Lead tanpa `linkedin_url` (enrichment dilewati). Isi kolom itu, atau setujui per item setelah diperiksa |
| Status `SENT_UNKNOWN` | Timeout setelah request kirim. Cek folder Terkirim, lalu catat hasilnya di dashboard; sistem tidak mengirim ulang |
