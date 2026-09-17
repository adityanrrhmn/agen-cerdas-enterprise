<#
.SYNOPSIS
  Pemeriksaan non-destruktif laporan .docx: hash, ekstraksi Markdown (teks saja), render PDF via Word, statistik, cek angka.
.DESCRIPTION
  File asli tidak pernah dibuka untuk ditulis: skrip menyalinnya ke folder keluaran lalu bekerja pada salinan.
  Keluaran default berada di %TEMP%, bukan di workspace.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\periksa-laporan.ps1
  powershell -ExecutionPolicy Bypass -File tools\periksa-laporan.ps1 -Docx .\draf.docx -OutDir C:\tmp\cek -Pdf
#>
param(
  [string]$Docx = (Join-Path $PSScriptRoot '..\Laporan_Multi_Agent_Email_Writer_Enrichment_Kelompok_1.docx'),
  [string]$OutDir = (Join-Path $env:TEMP 'agen-cerdas-cek'),
  [switch]$Pdf,
  [int]$PdfTimeoutSec = 120
)
$ErrorActionPreference = 'Stop'
$Docx = (Resolve-Path $Docx).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
# Nama unik per run: salinan lama bisa masih dipegang proses Word yang macet.
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$copy = Join-Path $OutDir "salinan-$stamp.docx"
# Baca dengan FileShare.ReadWrite: Copy-Item gagal bila Word/proses lain memegang handle tulis.
$in = [IO.File]::Open($Docx, 'Open', 'Read', 'ReadWrite, Delete')
try { $out = [IO.File]::Create($copy); try { $in.CopyTo($out) } finally { $out.Dispose() } } finally { $in.Dispose() }

"Sumber : $Docx"
# Hash dari salinan: file asli bisa terkunci saat dibuka di Word, sedangkan salinannya byte-identik.
"SHA256 : " + (Get-FileHash $copy -Algorithm SHA256).Hash.ToLower()
$lock = Join-Path (Split-Path $Docx) ('~$' + (Split-Path $Docx -Leaf).Substring(2))
if (Test-Path -LiteralPath $lock) { "PERINGATAN: file sedang dibuka di Word; simpan dahulu agar yang diperiksa adalah versi terbaru." }
"Diubah : " + (Get-Item $Docx).LastWriteTime.ToString('yyyy-MM-dd HH:mm')

$md = Join-Path $OutDir "laporan-$stamp.md"
& pandoc $copy -t gfm -o $md
if ($LASTEXITCODE -ne 0) { throw 'pandoc gagal' }
"Markdown: $md"

& python (Join-Path $PSScriptRoot 'cek_angka.py') $md
$code = $LASTEXITCODE

if ($Pdf) {
  # Word COM pernah macet tanpa dialog terlihat (17-09-2026); jalankan di job dengan batas waktu.
  $pdfPath = Join-Path $OutDir "laporan-$stamp.pdf"
  $job = Start-Job -ArgumentList $copy, $pdfPath -ScriptBlock {
    param($src, $dst)
    $w = New-Object -ComObject Word.Application
    $w.Visible = $false; $w.DisplayAlerts = 0
    try {
      $d = $w.Documents.Open($src, $false, $true)
      "Halaman: " + $d.ComputeStatistics(2) + " | Kata: " + $d.ComputeStatistics(0)
      $d.ExportAsFixedFormat($dst, 17)
      $d.Close($false)
    } finally { $w.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($w) }
    "PDF    : $dst"
  }
  if (Wait-Job $job -Timeout $PdfTimeoutSec) { Receive-Job $job } else {
    Stop-Job $job
    "GAGAL  render PDF melewati $PdfTimeoutSec dtk. Periksa proses WINWORD.EXE berargumen /Automation di Task Manager."
    $code = 1
  }
  Remove-Job $job -Force
}
exit $code
