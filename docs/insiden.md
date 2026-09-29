# Catatan insiden

## 2026-09-17: Render PDF via Word COM macet

- **Gejala:** percobaan pertama (salinan .docx di scratchpad) sukses menghasilkan PDF 11 halaman. Percobaan kedua
  lewat `tools/periksa-laporan.ps1` berhenti setelah mencetak statistik, pada `ExportAsFixedFormat`, lebih dari 240 dtk
  tanpa dialog terlihat.
- **Dampak:** proses `WINWORD.EXE /Automation` (PID 10224) tertinggal dan mengunci `%TEMP%\agen-cerdas-cek\salinan.docx`.
  File laporan asli tidak berubah (hash tetap `a159db82…`).
- **Tindakan:** task latar dihentikan. Agen tidak diizinkan menghentikan proses Word, jadi proses itu mungkin
  masih berjalan. Skrip diubah: PDF opsional (`-Pdf`) dalam job dengan batas waktu, nama salinan unik per run, dan
  pembacaan sumber dengan mode berbagi.
- **Penyebab:** belum terbukti. Dugaan: dialog tersembunyi atau konflik dengan instance Word pengguna yang sedang
  membuka laporan di Protected View.
- **Pemulihan manual:** di Task Manager → Details, akhiri `WINWORD.EXE` yang tidak punya jendela dan berbaris perintah
  `/Automation` (aktifkan kolom "Command line"). Jangan mengakhiri Word yang sedang dipakai.
- **Tindak lanjut:** jika macet berulang, coba render saat Word pengguna tertutup, lalu catat hasilnya di sini.
- **2026-09-17 22:34:** render `-Pdf` berhasil (11 halaman) saat laporan tidak sedang dibuka di Word. Dugaan konflik dengan instance Word pengguna makin kuat, tetapi belum terbukti.

## 2026-09-23: Writer selalu gagal — "keluaran LLM bukan JSON"

- **Gejala:** campaign live berhenti di tab Preview & Approval. Semua lead berstatus `NEEDS_REVIEW` dengan alasan
  `no_draft` ("Draft belum tersedia") dan `Writer: openrouter: keluaran LLM bukan JSON`. Tombol "Setujui semua yang
  lolos" tetap 0. Kredit OpenRouter tetap terpakai.
- **Penyebab (terbukti):** `LLM_MAX_TOKENS=1200` dihabiskan oleh *reasoning*. Panggilan uji ke
  `anthropic/claude-sonnet-5` mengembalikan `finish_reason: length`, `completion_tokens: 1200` dengan
  `reasoning_tokens: 1182`; hanya 31 karakter JSON yang sempat ditulis, sehingga `parse_json_content` gagal.
  Model keluarga Claude 5 berpikir lebih dulu dan reasoning ikut dihitung ke `max_tokens`.
- **Perbaikan:** `OpenRouterClient.structured` mengirim `reasoning: {"enabled": false}`; default `LLM_MAX_TOKENS`
  naik 1200 → 2000; `finish_reason == "length"` kini memunculkan pesan "keluaran LLM terpotong … naikkan
  LLM_MAX_TOKENS", dan pesan "bukan JSON" menyertakan cuplikan keluaran.
- **Verifikasi:** panggilan uji ulang → `finish_reason: stop`, `reasoning_tokens: 0`, JSON lengkap 773 karakter.
  Biaya per panggilan turun dari US$0,0136 ke US$0,0055. `pytest -q` 43 lulus.
- **Catatan:** bila nanti memakai model yang memang butuh reasoning, jangan matikan reasoning — naikkan
  `LLM_MAX_TOKENS` jauh di atas anggaran reasoning-nya.
- **2026-09-23, lanjutan:** setelah Writer gagal, campaign tidak bisa dipulihkan dari UI. `run_campaign` menolak
  campaign non-`DRAFT` ([orchestrator.py:266](../backend/app/orchestrator.py:266)) dan `maybe_next_occurrence` tidak
  pernah menutup campaign karena `NEEDS_REVIEW` bukan anggota `FINAL_EMAIL`, sehingga status menetap `RUNNING`.
  Pesan `no_draft` menyuruh "jalankan ulang" padahal jalurnya tidak ada. Ditambahkan
  `POST /api/emails/{send_key}/regenerate` + `Orchestrator.regenerate_draft` dan tombol **Tulis ulang** di panel
  Preview & Approval. Tulis ulang mempertahankan checkpoint prep (tidak ada biaya Apify/Firecrawl tambahan), menaikkan
  `generation` supaya runner lama tidak lagi current, dan menaikkan `draft_version` sehingga approval lama batal.
  Dijaga `tests/test_orchestrator.py::test_draft_gagal_dapat_ditulis_ulang_tanpa_mengulang_enrichment`.
