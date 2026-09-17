# Runbook laporan

## Alat yang tersedia (diverifikasi 2026-09-17)

| Alat | Versi | Kegunaan | Status |
|---|---|---|---|
| pandoc | 3.10 | docx → Markdown (teks) | Berfungsi |
| Python | 3.11.9 (`python`), 3.14.5 (`python3`) | `tools/cek_angka.py` | Berfungsi; `python-docx` **tidak** terpasang |
| Microsoft Word 2016 x86 | Office16 | Render PDF via COM, hitung halaman | Berfungsi 1 dari 2 kali (lihat insiden) |
| LibreOffice | — | — | Tidak terpasang |
| Docker | 29.4.3 (CLI) | — | Daemon tidak berjalan; tidak diperlukan |
| Git | 2.54 | — | Terpasang; workspace belum repo |

## Memeriksa laporan

```powershell
powershell -ExecutionPolicy Bypass -File tools\periksa-laporan.ps1          # hash + Markdown + cek angka
powershell -ExecutionPolicy Bypass -File tools\periksa-laporan.ps1 -Pdf     # + render PDF (maks. 120 dtk)
```

Keluaran ditulis ke `%TEMP%\agen-cerdas-cek\` dengan nama bertanda waktu, sehingga workspace tetap bersih. Untuk
melihat tata letak, buka halaman tertentu dari PDF (misalnya Read dengan `pages`), bukan seluruh dokumen.

## Mengedit laporan

1. Pastikan permintaan perubahan jelas dan pengguna mengizinkan pengeditan .docx.
2. Minta pengguna menutup file di Word. Jangan menghentikan proses Word milik pengguna.
3. Jalankan pemeriksaan dan catat hash baseline.
4. Buat cadangan: `backup\<nama>-<yyyyMMdd-HHmm>.docx`.
5. Edit dengan pilihan berikut, dari yang paling aman:
   - **Teks sederhana:** Word COM `Find.Execute` dengan penggantian, pada dokumen yang dibuka tidak read-only. Cara
     ini mempertahankan format run.
   - **Perubahan struktur (tabel/paragraf baru):** Word COM, atau `python-docx` bila dipasang (lihat bawah).
   - Hindari round-trip pandoc Markdown → docx karena gaya, tabel berwarna, header/footer, dan kotak callout akan hilang.
6. Perbarui `tools/cek_angka.py` bila asumsi berubah, jalankan pemeriksaan dengan `-Pdf`, lalu periksa halaman terdampak.
7. Perbarui hash dan bagian terkait di `docs/peta-laporan.md`.

## Pemulihan

- Salin cadangan terakhir dari `backup\` ke nama file asli, lalu cocokkan hash dengan catatan baseline.
- Jika render macet, lihat langkah di `docs/insiden.md`.

## Pemasangan opsional (belum diperlukan)

`python -m pip install python-docx` untuk Python 3.11 (per pengguna). Manfaatnya: edit struktur .docx tanpa Word.
Verifikasi dengan `python -c "import docx"`. Pasang hanya bila ada pengeditan struktur yang nyata.
