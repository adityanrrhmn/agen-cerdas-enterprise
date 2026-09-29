# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React + TypeScript (Vite) untuk dashboard; backend Python FastAPI (kode murni, bukan n8n). Dikonfirmasi pengguna 2026-09-17.
LLM lewat OpenRouter. Google Sheets sebagai database, Gmail API untuk kirim, Apify untuk enrichment, Firecrawl untuk riset. Key diisi pengguna di `.env`.

## Users
Staf sales B2B yang menyiapkan campaign outreach, meninjau draft email beserta buktinya, lalu menyetujui pengiriman. Dosen/penguji menilai prototipe lewat alur yang sama (tugas kuliah Agen Cerdas Enterprise, Kelompok 1).

## Product Purpose
Mengubah daftar prospek di spreadsheet menjadi email personal yang dapat diaudit. Agen spesialis menangani enrichment, riset bukti, penulisan, dan pemeriksaan keamanan; manusia memegang approval. Sukses = email hanya terkirim bila lolos pemeriksaan dan disetujui, dan setiap klaim di email bisa ditelusuri ke sumbernya.

## Positioning
Berbeda dari Clay/Apollo: kontrol state, kontrak pesan antaragen, approval terikat versi draft, dan eksperimen mobilitas agen (checkpoint, lease, generation) terlihat dan dapat diperiksa, bukan tersembunyi di dalam platform.

## Operating Context
Alur UI: Setup → Monitor → Preview & Approval (Preview & Finalisasi pada mode draf). Pengguna hanya menangani pengecualian (perlu review, diblokir). Jadwal kirim memakai zona waktu Asia/Jakarta secara default. Rancangan acuan: `Laporan_Multi_Agent_Email_Writer_Enrichment_Kelompok_1.docx` (lihat `docs/peta-laporan.md`).

## Capabilities and Constraints
- Status keputusan Security: PASS, REVIEW, BLOCK. Status kirim termasuk SENT_UNKNOWN (hasil ambigu, tidak dikirim ulang otomatis).
- Pengiriman Gmail hanya ke alamat/domain allowlist dan hanya bila pengiriman diaktifkan di `.env`.
- Nama ambigu masuk review, bukan ditebak. Maksimal 3 fakta per draft; maksimal 2 revisi otomatis.
- Perubahan draft membatalkan approval.
- Terminologi campuran Indonesia–Inggris sesuai laporan (lead, campaign, draft, approval, enrichment).
- Belum diputuskan: rubrik penilaian resmi.

## Evidence on Hand
Belum ada data nyata. Data lead fiktif (domain `.example`) disediakan untuk demo. Jangan membuat testimoni, pelanggan, atau angka kinerja palsu; angka kinerja di laporan adalah ilustrasi analitis.

## Product Principles
1. Bukti sebelum klaim: setiap fakta di email membawa sumber dan waktu pengambilan.
2. Manusia memegang keputusan kirim; LLM tidak dapat membatalkan blokir aturan.
3. Tampilkan pengecualian, sembunyikan kebisingan: tidak ada notifikasi per panggilan tool.
4. Status ambigu ditahan dan direkonsiliasi, bukan diulang diam-diam.

## Accessibility & Inclusion
Antarmuka berbahasa Indonesia. Status tidak boleh dibedakan hanya dengan warna.

## Arah visual (koreksi pengguna, 2026-09-29)

Pengguna menilai seluruh aplikasi terlalu monoton dan berbentuk kumpulan kotak, bukan hanya visualisasi robot.
Hindari menjadikan setiap kelompok informasi sebagai kartu berbingkai. Utamakan hierarki tipografi, ruang kosong,
dan pemisah tipis. Setup berupa lembar brief berurutan; Review berupa surat dengan catatan bukti di sampingnya;
Koneksi berupa direktori layanan; Monitor mengutamakan aktivitas agen dan membuka rincian teknis sesuai kebutuhan.
Gaya bersama: latar krem, aksen hijau, judul serif, kontrol sederhana. Di ponsel bukti berada setelah surat dan
layanan tersusun vertikal. Implementasi bersama di `frontend/src/styles/studio.css`.
