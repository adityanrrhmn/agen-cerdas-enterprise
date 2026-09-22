# Peta laporan

Indeks isi laporan agar tidak perlu membaca ulang seluruh .docx.

| Atribut | Nilai |
|---|---|
| File | `Laporan_Multi_Agent_Email_Writer_Enrichment_Kelompok_1.docx` |
| SHA256 | `6f33526843cca8915c4cebafc4376f59825c91e570271a1407c58387cc1d30d9` |
| Diubah (mtime) | 2026-09-22 20:21 (revisi sesuai prototipe; cadangan versi sebelumnya di `backup/`, hash `2ee3692e…`) |
| Dipetakan | 2026-09-22, dari ekstraksi pandoc 3.10 dan render Word 2016 (x86) |
| Ukuran | 17 halaman A4, 4.627 kata (hitungan Word), 23 tabel, 9 gambar PNG |
| Struktur docx | 1 section, header/footer, tanpa tracked changes, komentar, field, atau footnote |
| Gaya | Title, Subtitle, Heading1, Heading2, Caption; tabel berheader hijau tua |

Jika SHA256 file sekarang berbeda, peta ini usang. Jalankan `tools/periksa-laporan.ps1` dan perbarui bagian yang berubah.

## Struktur bagian

| § | Judul | Hal. | Isi pokok |
|---|---|---|---|
| — | Sampul + "Ringkasan konsep" | 1 | "Laporan perancangan dan prototipe"; ringkasan menyebut prototipe (Bagian 8.4, 9.3) |
| 1 | Identitas Kelompok | 1 | 5 anggota dan peran: Aditya (Leader & Evaluator), Amar (Presenter), Amelia (Designer), Jovi (Researcher), Syakirah (Programmer) |
| 2 | Problem Statement | 1 | 4 pain point, dampak, dan respons; "Batas laporan" (43 tes, simulasi 100 lead, belum uji lapangan) |
| 3 | State of the Art | 2 | Clay, Apollo, HubSpot/Clearbit, ZoomInfo; penelitian AutoGen, ReAct, Ditto, Papaioannou & Edwards |
| 4 | Tujuan Proyek | 2 | Sasaran: fungsi bisnis, integrasi AI, UI/UX, mobile agents |
| 5.1 | Arsitektur | 3 | Gambar 1; urutan eksekusi; scheduler dan Gmail |
| 5.2 | Spesifikasi agen | 4 | 5 agen (Orchestrator, Enrichment, Research, Writer, Security); kontrak input; cognitive overload; kontrol kirim ganda |
| 5.3 | Koordinasi & mobilitas | 5 | Gambar 2 (Contract Net), kontrak pesan, Gambar 3 (checkpoint/lease/generation), batas lingkungan |
| 5.4 | Realisasi pada prototipe | 6 | FastAPI + React; OpenRouter [17]; tabel komponen rancangan → realisasi → batas |
| 6 | Algoritma & AI | 6 | Rule-based, DL/NLP, ML, RL (bandit), GNN opsional |
| 6.1 | Entity linking | 6 | Rumus S dan kandidat A/B |
| 6.2 | Grounding | 6 | Maksimal 3 fakta; reward RL |
| 7.1 | Spreadsheet DB | 7 | 8 tab: Campaigns, Leads, Evidence, Templates, Tasks, Emails, Suppression, Audit |
| 7.2 | Dataset | 7 | 1.000 pasangan berlabel; 100 paket brief; Ditto/ER-Magellan |
| 7.3 | Integrasi API | 8 | CRM simulasi, rahasia di server, allowlist; service account Sheets [19], OAuth + PKCE Gmail [18], mode draf |
| 8.1 | Simulasi | 8 | Campaign 100 lead, 21-09-2026 09.00 WIB, contoh email "Sinta Pramesti" (fiktif) |
| 8.2 | UI/UX | 8 | Gambar 4 (mockup dashboard) |
| 8.3 | Keamanan | 10 | 6 lapisan uji; 5 sudah diuji otomatis (audit & retensi belum) |
| 8.4 | Prototipe yang dibangun | 11–13 | Gambar 5–8 (tangkapan layar simulasi); lead manual, satu penerima, mode draf |
| 9.1 | Desain evaluasi | 9 | Konfigurasi A/B/C, 10 pengulangan, 5 indikator |
| 9.2 | Ilustrasi kinerja | 15 | Gambar 9; rumus waktu, migrasi, pesan, biaya |
| 9.3 | Hasil pengujian prototipe | 15–16 | Tabel 43 tes per kelompok; tabel hasil simulasi 100 lead; daftar belum diuji |
| 10 | Kesimpulan | 10 | Prioritas pengembangan; blockchain bukan prioritas |
| 11 | Referensi | 17 | [1]–[19]; "tautan diperiksa 17 dan 22 September 2026" |
| 12 | Link Kode | 17 | URL repo GitHub (privat); struktur implementasi; cara menjalankan dan menguji |

## Matriks keterkaitan angka dan istilah

Ubah satu lokasi, periksa lokasi lain di baris yang sama. Status: **T** = terverifikasi otomatis oleh `tools/cek_angka.py`,
**M** = diperiksa manual pada 2026-09-17.

| Nilai | Lokasi | Status |
|---|---|---|
| 100 lead = 80 siap + 15 review + 5 blokir | §8.1 tabel, Gambar 4 | T (teks), M (gambar) |
| 5 worker paralel | §5.2 cognitive overload, §9.1, §9.2, Gambar 5 | M |
| Batch 25, 3 fakta, 2 revisi, retry 3 | §5.2; 3 fakta juga di §5.2 tabel Research, §6.2 | M |
| Bobot S 0,40/0,30/0,20/0,10; skor 0,945/0,310; ambang 0,85 dan selisih 0,10 | §6.1 | T |
| 15 dtk/lead, 1.500 vs 330 dtk, 4,55×, 78% | §9.2 teks dan Gambar 5 | T (teks), M (gambar) |
| Migrasi 35 > 3 + 10, hemat 22 dtk | §9.2 | T |
| Pesan 8 vs 20, 60% | §9.2 | T |
| 700/150/150 | §7.2 | T |
| Jadwal 21 Sep 2026 09.00 WIB | §8.1, Gambar 4 | M |
| Status PASS/REVIEW/BLOCK; SENT_UNKNOWN | §5.2, Gambar 2, §8.3 | M |
| Kunci kirim campaign_id+occurrence_id+lead_id+step_id | §5.2; kolom tab Emails di §7.1 memakai `send_key`, `occurrence_id` | M |
| Nomor referensi [1]–[19] | Sitasi di §3–§8.4 dan daftar §11 | M: semua dipakai; [17] di §5.4, [18][19] di §7.3 |
| Hasil simulasi 76 PASS / 14 REVIEW / 10 BLOCK; 1.012 pesan; 2 migrasi | §9.3, Gambar 5 & 7 | M (sumber: seed simulasi 2026-09-22) |
| 43 tes (9+7+10+4+6+2+4+1) | §2, §9.3, §12, README | M |

## Gambar (Gambar 1–4 dan 9 hanya PNG; Gambar 5–8 bersumber dari `docs/gambar/`)

| No | Hal. | Isi | Catatan |
|---|---|---|---|
| 1 | 3 | Arsitektur: user → orchestrator → agen → security → approval → scheduler → Gmail; Data Gateway → Sheets | Legenda panah ada di dalam gambar |
| 2 | 5 | Sequence Contract Net: CFP, PROPOSE, ACCEPT/REJECT, INFORM, REQUEST, PASS/REVIEW/BLOCK | |
| 3 | 5 | Migrasi Runtime A → checkpoint → Runtime B, agen E-07/task T-042 | |
| 4 | 8 | Mockup dashboard "Outreach Control" | Angka harus cocok dengan §8.1 |
| 5 | 11 | Tangkapan layar Preview & Approval | `docs/gambar/preview-approval.png` |
| 6 | 12 | Tangkapan layar review identitas | `docs/gambar/review-identitas.png` |
| 7 | 13 | Tangkapan layar Monitor | `docs/gambar/monitor.png` |
| 8 | 13 | Tangkapan layar mode draf | `docs/gambar/mode-draf-final.png` |
| 9 | 15 | Bar chart 1.500 vs 330 dtk (dulu Gambar 5) | Font chart (gaya matplotlib) berbeda dari font laporan |

## Hal terbuka (bukan kesalahan terverifikasi)

- Rubrik penilaian dirujuk di §5.3 dan §6, tetapi tidak ada di workspace. Kesesuaian laporan terhadap rubrik **belum diperiksa**.
- Metadata docx: tanggal dibuat/diubah 2013-12-23, kemungkinan warisan templat. Tidak memengaruhi tampilan.
- Tautan referensi belum diverifikasi ulang oleh agen; klaim "diperiksa 17 September 2026" berasal dari teks laporan.
