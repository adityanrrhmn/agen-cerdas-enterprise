# Peta laporan

Indeks isi laporan agar tidak perlu membaca ulang seluruh .docx.

| Atribut | Nilai |
|---|---|
| File | `Laporan_Multi_Agent_Email_Writer_Enrichment_Kelompok_1.docx` |
| SHA256 | `2ee3692e1f2c91fcbcbaf2f9d4ac7a996cd1ea7f722e0c3e79d9cbfeea29a11f` |
| Diubah (mtime) | 2026-09-17 22:34 (peran §1 diganti; cadangan versi sebelumnya di `backup/`) |
| Dipetakan | 2026-09-17, dari ekstraksi pandoc 3.10 dan render Word 2016 (x86) |
| Ukuran | 11 halaman A4, 3.501 kata (hitungan Word), 20 tabel, 5 gambar PNG |
| Struktur docx | 1 section, header/footer, tanpa tracked changes, komentar, field, atau footnote |
| Gaya | Title, Subtitle, Heading1, Heading2, Caption; tabel berheader hijau tua |

Jika SHA256 file sekarang berbeda, peta ini usang. Jalankan `tools/periksa-laporan.ps1` dan perbarui bagian yang berubah.

## Struktur bagian

| § | Judul | Hal. | Isi pokok |
|---|---|---|---|
| — | Sampul + "Ringkasan konsep" | 1 | Judul, subjudul, UGM 2026 |
| 1 | Identitas Kelompok | 1 | 5 anggota dan peran: Aditya (Leader & Evaluator), Amar (Presenter), Amelia (Designer), Jovi (Researcher), Syakirah (Programmer) |
| 2 | Problem Statement | 1 | 4 pain point, dampak, dan respons; "Batas laporan" |
| 3 | State of the Art | 2 | Clay, Apollo, HubSpot/Clearbit, ZoomInfo; penelitian AutoGen, ReAct, Ditto, Papaioannou & Edwards |
| 4 | Tujuan Proyek | 2 | Sasaran: fungsi bisnis, integrasi AI, UI/UX, mobile agents |
| 5.1 | Arsitektur | 3 | Gambar 1; urutan eksekusi; scheduler dan Gmail |
| 5.2 | Spesifikasi agen | 4 | 5 agen (Orchestrator, Enrichment, Research, Writer, Security); kontrak input; cognitive overload; kontrol kirim ganda |
| 5.3 | Koordinasi & mobilitas | 5 | Gambar 2 (Contract Net), kontrak pesan, Gambar 3 (checkpoint/lease/generation), batas lingkungan |
| 6 | Algoritma & AI | 6 | Rule-based, DL/NLP, ML, RL (bandit), GNN opsional |
| 6.1 | Entity linking | 6 | Rumus S dan kandidat A/B |
| 6.2 | Grounding | 6 | Maksimal 3 fakta; reward RL |
| 7.1 | Spreadsheet DB | 7 | 8 tab: Campaigns, Leads, Evidence, Templates, Tasks, Emails, Suppression, Audit |
| 7.2 | Dataset | 7 | 1.000 pasangan berlabel; 100 paket brief; Ditto/ER-Magellan |
| 7.3 | Integrasi API | 7 | CRM simulasi, rahasia di server, dry-run dan allowlist |
| 8.1 | Simulasi | 8 | Campaign 100 lead, 21-09-2026 09.00 WIB, contoh email "Sinta Pramesti" (fiktif) |
| 8.2 | UI/UX | 8 | Gambar 4 (mockup dashboard) |
| 8.3 | Keamanan | 9 | 6 lapisan uji ("belum diuji"); Gmail send-only |
| 9.1 | Desain evaluasi | 9 | Konfigurasi A/B/C, 10 pengulangan, 5 indikator |
| 9.2 | Ilustrasi kinerja | 10 | Gambar 5; rumus waktu, migrasi, pesan, biaya |
| 10 | Kesimpulan | 10 | Prioritas pengembangan; blockchain bukan prioritas |
| 11 | Referensi | 11 | [1]–[16]; "tautan diperiksa 17 September 2026" |
| 12 | Link Kode | 11 | Repositori **belum disertakan**; usulan struktur folder implementasi |

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
| Nomor referensi [1]–[16] | Sitasi di §3–§8.3 dan daftar §11 | M: semua 16 dipakai; [14] juga di §3 |

## Gambar (hanya PNG; sumber tidak tersedia)

| No | Hal. | Isi | Catatan |
|---|---|---|---|
| 1 | 3 | Arsitektur: user → orchestrator → agen → security → approval → scheduler → Gmail; Data Gateway → Sheets | Legenda panah ada di dalam gambar |
| 2 | 5 | Sequence Contract Net: CFP, PROPOSE, ACCEPT/REJECT, INFORM, REQUEST, PASS/REVIEW/BLOCK | |
| 3 | 5 | Migrasi Runtime A → checkpoint → Runtime B, agen E-07/task T-042 | |
| 4 | 8 | Mockup dashboard "Outreach Control" | Angka harus cocok dengan §8.1 |
| 5 | 10 | Bar chart 1.500 vs 330 dtk | Font chart (gaya matplotlib) berbeda dari font laporan |

## Hal terbuka (bukan kesalahan terverifikasi)

- Rubrik penilaian dirujuk di §5.3 dan §6, tetapi tidak ada di workspace. Kesesuaian laporan terhadap rubrik **belum diperiksa**.
- §12 masih menulis "Repositori kelompok: belum disertakan", padahal repo sudah ada (github.com/adityanrrhmn/agen-cerdas-enterprise, private). Perlu diperbarui bila laporan akan dikumpulkan.
- Metadata docx: tanggal dibuat/diubah 2013-12-23, kemungkinan warisan templat. Tidak memengaruhi tampilan.
- Tautan referensi belum diverifikasi ulang oleh agen; klaim "diperiksa 17 September 2026" berasal dari teks laporan.
