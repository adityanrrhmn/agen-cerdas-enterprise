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
