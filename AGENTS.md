# AGENTS.md — Agen Cerdas Enterprise (Kelompok 1)

Panduan kerja agen untuk workspace ini. Aturan stabil ada di sini; langkah rinci di `docs/`.
Terakhir diperbarui: 2026-09-17.

## 1. Karakter workspace

- Workspace **tugas kuliah** (Magister Kecerdasan Artifisial UGM, mata kuliah Agen Cerdas Enterprise), dikerjakan Kelompok 1.
- Isi:
  - Laporan rancangan `Laporan_Multi_Agent_Email_Writer_Enrichment_Kelompok_1.docx` dan helper di `tools/`.
  - **Prototipe "Outreach Control"** (sejak 2026-09-17): `backend/` (Python FastAPI, agen, orchestrator, scheduler)
    dan `frontend/` (React + TypeScript + Vite). Detail: [docs/runbook-aplikasi.md](docs/runbook-aplikasi.md).
  - Konteks produk dan desain UI: [PRODUCT.md](PRODUCT.md).
  - Deck presentasi: `presentasi/Presentasi_Outreach_Control_Kelompok_1.pptx`, dibangun dari `presentasi/build-deck.js`
    (pptxgenjs). Angka di deck harus sama dengan laporan §9.3. Tangkapan layar bersama: `docs/gambar/`.
- Prototipe terhubung ke layanan **sungguhan** lewat `.env`: OpenRouter (LLM), Apify, Firecrawl, Google Sheets
  (database), dan Gmail API (kirim). Semua memakai kredit atau akun milik pengguna.
- Repo Git: https://github.com/adityanrrhmn/agen-cerdas-enterprise (private, branch `main`); README untuk tim. Tenggat: 17-09-2026. Rubrik penilaian resmi belum ada di workspace.
- Keputusan pengguna yang berlaku: backend kode murni (bukan n8n); LLM via OpenRouter; data di Google Sheets;
  auth Google tanpa refresh token manual (service account untuk Sheets, tombol Hubungkan untuk Gmail).

## 2. Sumber konteks dan urutan baca

1. Dokumen ini.
2. [docs/peta-laporan.md](docs/peta-laporan.md): struktur bagian, angka kunci, dan keterkaitan antarbagian. Cukup untuk
   sebagian besar pertanyaan; jangan konversi ulang seluruh .docx tanpa perlu.
3. Isi penuh laporan hanya bila peta tidak cukup atau hash berubah: jalankan `tools/periksa-laporan.ps1`, lalu baca
   bagian yang relevan dari Markdown yang dihasilkan (bukan seluruhnya).
4. [docs/runbook-laporan.md](docs/runbook-laporan.md): cara mengedit, merender, dan memverifikasi laporan.

Sumber kebenaran untuk isi laporan adalah file .docx. Peta hanyalah indeks dengan hash; jika hash berbeda, anggap peta
usang dan perbarui.

## 3. Cara bekerja

- Pertahankan gaya laporan: bahasa Indonesia formal, klaim dibatasi ("rancangan", "ilustratif", "belum diuji"),
  sitasi `[n]` ke bagian 11, angka desimal memakai koma.
- Jangan menambahkan klaim bahwa sistem sudah berjalan, sudah diuji, atau patuh regulasi tanpa bukti baru.
- Setiap perubahan angka/asumsi harus diikuti di semua bagian terkait (lihat matriks keterkaitan di peta) dan di
  `tools/cek_angka.py`. Konstanta di skrip adalah asumsi; jangan mengubah skrip hanya agar lulus.
- Gambar 1–5 hanya tersedia sebagai PNG di dalam .docx; berkas sumbernya tidak ada di workspace. Mengubah isi
  gambar berarti menggambar ulang, jadi konfirmasi dahulu.
- Delegasikan ke subagen hanya pekerjaan independen, misalnya verifikasi tautan referensi.

## 4. Pemeriksaan kualitas

Sebelum menyatakan perubahan laporan selesai:

| Pemeriksaan | Perintah / cara | Kriteria lulus |
|---|---|---|
| Angka turunan | `powershell -ExecutionPolicy Bypass -File tools\periksa-laporan.ps1` | Exit 0; semua baris `LULUS` |
| Tata letak | Tambahkan `-Pdf`, lalu lihat halaman yang berubah | Tidak ada tabel/gambar terpotong, halaman kosong, atau heading yatim |
| Konsistensi silang | Matriks di peta | Nilai sama di semua lokasi |
| Referensi | Setiap `[n]` baru ada di bagian 11 dan sebaliknya | Tidak ada nomor yatim |

Laporkan setiap pemeriksaan sebagai lulus, gagal, dilewati, atau belum dijalankan, beserta hash .docx yang diuji.
Jangan memberi persentase keyakinan tanpa dasar.

Untuk perubahan prototipe:

| Pemeriksaan | Perintah | Kriteria lulus |
|---|---|---|
| Tes backend | `backend\.venv\Scripts\python -m pytest -q` (dari `backend/`) | Semua lulus (43 pada 2026-09-22) |
| Tipe frontend | `npx tsc -b` (dari `frontend/`) | Tanpa galat |
| Tampilan | Backend simulasi + `node tools/screenshot.mjs ...` (lihat runbook aplikasi) | Desktop 1440 dan mobile 390 tanpa overflow |
| Koneksi layanan | Tombol **Tes** di tab Koneksi, atau `POST /api/integrations/<nama>/test` | `ok: true`; tanpa biaya |

Tes harus menyatakan kebutuhan laporan (misalnya rumus S, BLOCK tanpa izin, approval batal saat draft diedit, tidak
kirim ganda), bukan menyalin implementasi. Integrasi eksternal diuji dengan transport tiruan.

## 5. Batas tindakan dan otorisasi

Boleh mandiri:
- Membaca file workspace; membuat salinan/keluaran di `%TEMP%` atau scratchpad; menjalankan `tools/`.
- Memperbarui `AGENTS.md`, `docs/`, dan `tools/`.
- Mengubah kode prototipe sesuai permintaan; menjalankan tes; menjalankan instance **simulasi** (port lain,
  key dikosongkan lewat env, `DATA_BACKEND=local`) untuk verifikasi tanpa biaya.
- Endpoint tes tanpa biaya (validasi key, info akun, metadata spreadsheet).

Perlu konfirmasi sesuai permintaan konkret:
- Menjalankan campaign dengan layanan live (memakai kredit OpenRouter/Apify/Firecrawl dan menulis ke Sheets).
- Mengirim email sungguhan, mengubah `GMAIL_SEND_ENABLED`/`GMAIL_ALLOWLIST`, atau menyetujui draft atas nama pengguna.
- Mengubah nilai rahasia di `.env`. Nilai rahasia tidak boleh dibaca, dicetak, atau disalin ke dokumentasi; cek
  hanya "terisi/kosong". File `secrets/`, `.env`, dan `backend/data/google-oauth.json` di-gitignore.
- **Mengedit file .docx asli.** Buat cadangan `backup/<nama>-<yyyyMMdd-HHmm>.docx` terlebih dahulu dan pastikan file
  tidak sedang dibuka di Word.
- Membaca file di luar workspace (misalnya lampiran WhatsApp/Downloads). Minta pengguna menyalinnya ke sini.
- Menghentikan proses (termasuk WINWORD.EXE), memasang paket/alat, atau membuat akun/layanan.
- Push ke GitHub (hanya atas permintaan). Sebelum commit: pastikan `.env`, `secrets/`, token OAuth tidak ter-stage dan pindai pola key.
- Tindakan eksternal apa pun: publikasi, unggah, mengirim pesan/email, mengakses API berbayar.

Data pribadi: laporan memuat nama dan NIM anggota. Jangan menyalin NIM ke dokumentasi, log, atau keluaran chat.
Contoh data di laporan harus tetap fiktif (domain `.example`).

## 6. Kegagalan yang diketahui

- File .docx bisa terkunci oleh Word atau proses lain. Skrip membaca dengan mode berbagi; jika perlu mengedit, minta
  pengguna menutup Word.
- Render PDF via Word COM pernah macet (lihat [docs/insiden.md](docs/insiden.md)). Karena itu PDF bersifat opsional
  dan dibatasi waktu.
- Endpoint FastAPI **wajib `async def`**: endpoint sinkron berjalan di threadpool, sehingga `asyncio.create_task`
  gagal dan state orchestrator tersentuh dari thread lain. Dijaga oleh `tests/test_api_routes.py`.
- Edge headless dengan `--virtual-time-budget` tidak pernah selesai pada halaman ber-SSE (Monitor). Pakai
  `tools/screenshot.mjs` (CDP, jeda waktu nyata).
- Heredoc bash berisi kutip kompleks bisa gagal di Git Bash Windows; tulis skrip ke scratchpad lalu jalankan.

## 7. Pemeliharaan panduan

Perbarui dokumen ini, peta, atau runbook **saat itu juga** pada kondisi berikut: perubahan penting pada laporan
(sertakan hash baru), koreksi dari pengguna yang berlaku seterusnya, insiden atau error berulang, tonggak kerja, dan
sebelum serah terima. Kronologi masalah dicatat di `docs/insiden.md`, dengan penyebab yang belum terbukti ditandai
"dugaan". Hapus atau koreksi aturan yang terbukti usang; jangan menjadikan izin satu kali sebagai aturan tetap.
