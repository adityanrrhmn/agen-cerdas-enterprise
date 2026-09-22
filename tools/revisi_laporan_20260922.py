"""Revisi laporan agar sesuai prototipe. Mengkloning templat XML laporan; gaya asli dipertahankan.

Pakai: python revisi_laporan.py <docx_sumber> <docx_keluaran> <folder_gambar>
"""
import re
import struct
import sys
import zipfile
from xml.sax.saxutils import escape

SRC, OUT, IMG = sys.argv[1], sys.argv[2], sys.argv[3]
zin = zipfile.ZipFile(SRC)
doc = zin.read("word/document.xml").decode("utf-8")
rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
footer = zin.read("word/footer1.xml").decode("utf-8")

head, body_and_tail = doc.split("<w:body>", 1)
body, tail = body_and_tail.rsplit("</w:body>", 1)
blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:p/>|<w:tbl>.*?</w:tbl>|<w:sectPr.*?</w:sectPr>", body, re.S)
assert "".join(blocks) == body, "blok tidak menutup seluruh body"


def text(b):
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", b))


def find(prefix, start=0):
    for i in range(start, len(blocks)):
        if text(blocks[i]).startswith(prefix):
            return i
    raise KeyError(prefix)


def t(s):
    return escape(s, {'"': "&quot;"})


# ------------------------------------------------------------------ pembangun blok (kloning gaya asli)
def run(s, bold=False, size=None):
    rpr = "<w:b/>" if bold else '<w:b w:val="0"/>'
    if size:
        rpr += f'<w:sz w:val="{size}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{t(s)}</w:t></w:r>'


def para(*parts, size=None):
    """parts: str (biasa) atau ("b", str) untuk tebal."""
    runs = "".join(run(p[1], True, size) if isinstance(p, tuple) else run(p, False, size) for p in parts)
    return f"<w:p>{runs}</w:p>"


def h1(s):
    return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t xml:space="preserve">{t(s)}</w:t></w:r></w:p>'


def h2(s):
    return f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t xml:space="preserve">{t(s)}</w:t></w:r></w:p>'


SPACER = '<w:p><w:pPr><w:spacing w:after="0" w:before="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:sz w:val="4"/></w:rPr></w:r></w:p>'
PAGEBREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
CELL_MAR = '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>'


def cell(content, width, fill, header=False):
    rpr = '<w:b/><w:color w:val="FFFFFF"/><w:sz w:val="18"/>' if header else '<w:b w:val="0"/><w:sz w:val="18"/>'
    pieces = content if isinstance(content, list) else [content]
    runs = ""
    rpr_bold = rpr.replace('<w:b w:val="0"/>', "<w:b/>")
    for p in pieces:
        if isinstance(p, tuple):
            runs += f'<w:r><w:rPr>{rpr_bold}</w:rPr><w:t xml:space="preserve">{t(p[1])}</w:t></w:r>'
        else:
            runs += f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{t(p)}</w:t></w:r>'
    return (f'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="{width}"/><w:vAlign w:val="center"/>{CELL_MAR}<w:shd w:fill="{fill}"/></w:tcPr>'
            f'<w:p><w:pPr><w:spacing w:after="20" w:before="0" w:line="247" w:lineRule="auto"/></w:pPr>{runs}</w:p></w:tc>')


def table(header, rows, widths):
    assert sum(widths) == 9978, sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = ('<w:tbl><w:tblPr><w:tblW w:type="auto" w:w="0"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
           '<w:tblLook w:firstColumn="1" w:firstRow="1" w:lastColumn="0" w:lastRow="0" w:noHBand="0" w:noVBand="1" w:val="04A0"/>'
           f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>')
    out += '<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' + "".join(cell(h, w, "17656B", True) for h, w in zip(header, widths)) + "</w:tr>"
    for i, r in enumerate(rows):
        fill = "F5F8F9" if i % 2 == 0 else "FFFFFF"
        out += '<w:tr><w:trPr><w:cantSplit/></w:trPr>' + "".join(cell(c, w, fill) for c, w in zip(r, widths)) + "</w:tr>"
    return out + "</w:tbl>"


def callout(title, body_text, fill="EAF3F3", size=19):
    return ('<w:tbl><w:tblPr><w:tblW w:type="auto" w:w="0"/><w:jc w:val="center"/>'
            '<w:tblLook w:firstColumn="1" w:firstRow="1" w:lastColumn="0" w:lastRow="0" w:noHBand="0" w:noVBand="1" w:val="04A0"/>'
            '</w:tblPr><w:tblGrid><w:gridCol w:w="9978"/></w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr>'
            f'<w:tcW w:type="dxa" w:w="9978"/><w:shd w:fill="{fill}"/><w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/>'
            '<w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar></w:tcPr>'
            f'<w:p><w:pPr><w:spacing w:after="80"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr><w:t xml:space="preserve">{t(title)}</w:t></w:r></w:p>'
            f'<w:p><w:pPr><w:spacing w:after="20" w:line="254" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:b w:val="0"/><w:sz w:val="{size}"/></w:rPr>'
            f'<w:t xml:space="preserve">{t(body_text)}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')


# ------------------------------------------------------------------ gambar & relasi
rid_nums = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels)]
next_rid = max(rid_nums) + 1
new_media = {}
new_rels = []
doc_pr = [6]


def png_size(path):
    with open(path, "rb") as fh:
        head_bytes = fh.read(24)
    return struct.unpack(">II", head_bytes[16:24])


def figure(img_name, caption, alt, max_w=6336000, max_h=6100000):
    global next_rid
    path = f"{IMG}/{img_name}"
    w, h = png_size(path)
    cx = max_w
    cy = int(cx * h / w)
    if cy > max_h:
        cy = max_h
        cx = int(cy * w / h)
    media = f"image{5 + len(new_media) + 1}.png"
    new_media[media] = path
    rid = f"rId{next_rid}"
    next_rid += 1
    new_rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media}"/>')
    pid = doc_pr[0]
    doc_pr[0] += 1
    fig_no = re.match(r"Gambar (\d+)", caption).group(1)
    drawing = (f'<w:p><w:pPr><w:keepNext/><w:spacing w:after="0"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
               f'<wp:inline xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
               f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Picture {pid}" descr="{t(alt)}" title="Gambar {fig_no}"/>'
               '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic>'
               '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
               f'<pic:cNvPr id="0" name="{img_name}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/>'
               '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/>'
               f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"/></pic:spPr></pic:pic></a:graphicData></a:graphic>'
               '</wp:inline></w:drawing></w:r></w:p>')
    cap = f'<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t xml:space="preserve">{t(caption)}</w:t></w:r></w:p>'
    return drawing + cap


def reference(label, links):
    """links: list of (teks, url)."""
    global next_rid
    out = f'<w:p><w:pPr><w:spacing w:after="100" w:line="245" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:b w:val="0"/><w:sz w:val="17"/></w:rPr><w:t xml:space="preserve">{t(label)} </w:t></w:r>'
    for i, (txt, url) in enumerate(links):
        rid = f"rId{next_rid}"
        next_rid += 1
        new_rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{t(url)}" TargetMode="External"/>')
        if i:
            out += '<w:r><w:rPr><w:b w:val="0"/><w:sz w:val="17"/></w:rPr><w:t xml:space="preserve"> | </w:t></w:r>'
        out += f'<w:hyperlink r:id="{rid}"><w:r><w:rPr><w:color w:val="17656B"/><w:sz w:val="17"/><w:u w:val="single"/></w:rPr><w:t>{t(txt)}</w:t></w:r></w:hyperlink>'
    return out + "</w:p>"


def replace_text(i, old, new):
    b = blocks[i]
    assert t(old) in b, (i, old)
    blocks[i] = b.replace(t(old), t(new), 1)


# ------------------------------------------------------------------ halaman kosong: ganti page break manual sebelum §5 dengan pageBreakBefore
i_h5 = find("5. Desain Sistem Multi-Agent")
if blocks[i_h5 - 1] == PAGEBREAK:
    del blocks[i_h5 - 1]
    i_h5 -= 1
    blocks[i_h5] = blocks[i_h5].replace('<w:pStyle w:val="Heading1"/>', '<w:pStyle w:val="Heading1"/><w:pageBreakBefore/>', 1)

# ------------------------------------------------------------------ penanda posisi (dicari sebelum sisipan)
i_label = find("LAPORAN PERANCANGAN")
i_ringkas = find("Ringkasan konsep")
i_ident = find("Nama kelompok: Kelompok 1.")
i_roles = find("Nama anggotaNIM")
i_batas = find("Batas laporan:")
i_posisi = find("Posisi usulan:")
i_batas_ling = find("Batas lingkungan")
i_api2 = find("API key dan token OAuth")
i_mockup_cap = find("Gambar 4. Mockup")
i_fitur = find("Fitur utama:")
i_sec_tbl = find("Lapisan / uji")
i_gmail_note = find("Gmail send-only tidak cukup")
i_biaya = find("Biaya per email disetujui:")
i_g5cap = find("Gambar 5. Perbandingan")
i_kes1 = find("Sistem yang diusulkan memisahkan")
i_prior = find("Prioritas pengembangan:")
i_ref_intro = find("Dokumentasi primer dan penelitian")
i_ref16 = find("[16] Republik Indonesia")
i_repo = find("Repositori kelompok: belum disertakan")
i_struktur = find("Struktur implementasi yang disarankan:")

# ------------------------------------------------------------------ ubahan di tempat
replace_text(i_label, "LAPORAN PERANCANGAN", "LAPORAN PERANCANGAN DAN PROTOTIPE")
replace_text(i_ringkas, "Google Sheets menjadi database prototipe.",
             "Google Sheets menjadi database prototipe. Prototipe fungsional telah dibangun dan diuji dengan tes otomatis serta simulasi data fiktif (Bagian 8.4 dan 9.3).")
replace_text(i_ident, " Pembagian peran berikut merupakan usulan untuk proyek ini.", " Pembagian peran dalam proyek ini sebagai berikut.")
replace_text(i_roles, "Peran yang diusulkan", "Peran")
replace_text(i_batas, " rancangan konseptual dan rencana prototipe, bukan klaim sistem sudah berjalan. Data contoh, mockup, serta estimasi kinerja bersifat ilustratif; belum ada uji lapangan atau pengiriman massal.",
             " rancangan konseptual beserta prototipe fungsional. Prototipe diuji dengan 43 tes otomatis dan simulasi 100 lead fiktif; belum ada uji lapangan, pengiriman massal, atau pengukuran kinerja dengan layanan berbayar. Data contoh, mockup, dan estimasi pada Bagian 9.2 tetap bersifat ilustratif.")
replace_text(i_posisi, "dengan spreadsheet sebagai sumber state utama.",
             "dengan spreadsheet sebagai sumber state utama. Rancangan ini telah direalisasikan sebagai prototipe fungsional (Bagian 5.4 dan 12).")
replace_text(i_sec_tbl, "Perilaku yang diharapkan (belum diuji)", "Perilaku yang diharapkan")
replace_text(i_g5cap, "Gambar 5.", "Gambar 9.")
blocks[i_g5cap - 1] = blocks[i_g5cap - 1].replace('title="Gambar 5"', 'title="Gambar 9"')
replace_text(i_kes1, "mengeksekusi pengiriman terkontrol.",
             "mengeksekusi pengiriman terkontrol. Prototipe membuktikan bahwa alur tersebut dapat dijalankan dari ujung ke ujung: 100 lead fiktif diproses menjadi keputusan yang dapat diaudit, dengan migrasi task, penolakan hasil generation lama, dan pengaman kirim yang teruji otomatis.")
replace_text(i_prior, "validasi kualitas entitas dan keamanan lebih dahulu;",
             "uji terbatas dengan layanan live memakai mode satu penerima dan mode draf; pelabelan data untuk validasi kualitas entitas; menjalankan pembandingan A/B/C pada Bagian 9.1;")
replace_text(i_ref_intro, "Tautan diperiksa pada 17 September 2026;", "Tautan diperiksa pada 17 dan 22 September 2026;")
blocks[i_repo] = callout("Repositori kelompok",
                         "https://github.com/adityanrrhmn/agen-cerdas-enterprise (privat; akses diberikan kepada anggota kelompok dan penilai atas permintaan). "
                         "README memuat cara instalasi, konfigurasi layanan, dan pembagian peran.", fill="EAF3F3", size=18)
blocks[i_struktur] = para(("b", "Struktur implementasi:"),
                          " backend/app/ (orchestrator, agen, scheduler, adapter, Data Gateway, API), backend/tests/ (43 tes), "
                          "frontend/src/ (dashboard React), docs/ (runbook, peta laporan, gambar), tools/ (pemeriksa laporan, screenshot), "
                          ".env.example tanpa rahasia, dan data fiktif. Menjalankan: powershell -ExecutionPolicy Bypass -File run-dev.ps1; "
                          "pengujian: python -m pytest -q.", size=18)

# ------------------------------------------------------------------ sisipan (dari belakang agar indeks depan tidak bergeser)
inserts = {}

# §11: referensi baru
inserts[i_ref16] = [
    reference("[17] OpenRouter. Structured Outputs: keluaran JSON sesuai skema.", [("Dokumentasi", "https://openrouter.ai/docs/features/structured-outputs")]),
    reference("[18] Google. OAuth 2.0 for iOS & Desktop Apps: loopback redirect dan PKCE.", [("Dokumentasi", "https://developers.google.com/identity/protocols/oauth2/native-app")]),
    reference("[19] Google. Using OAuth 2.0 for Server to Server Applications (service account).", [("Dokumentasi", "https://developers.google.com/identity/protocols/oauth2/service-account")]),
]

# §9.3: hasil pengujian prototipe (setelah paragraf biaya, sebelum §10)
inserts[i_biaya] = [
    h2("9.3 Hasil pengujian prototipe"),
    para("Bukti kualitas prototipe berasal dari dua sumber: tes otomatis yang menyatakan kebutuhan laporan (bukan menyalin implementasi), "
         "dan simulasi ujung ke ujung dengan 100 lead fiktif. Layanan eksternal diuji dengan transport tiruan; tidak ada kredit berbayar yang dipakai."),
    table(["Kelompok uji", "Yang dibuktikan", "Tes"], [
        ["Agen", "Bobot skor S dan aturan terima (S ≥ 0,85, selisih ≥ 0,10); BLOCK untuk kontak tanpa izin, suppression, duplikat, dan email invalid; REVIEW untuk angka tanpa bukti; batas 2 revisi writer; halaman injection dan fakta tanpa kutipan dibuang.", "9"],
        ["Orchestrator", "Alur lengkap sampai terkirim tanpa duplikasi; approval batal saat draft diedit; migrasi menaikkan generation dan hasil lama ditolak; runtime mati memindahkan task; pemulihan setelah restart (SENDING menjadi SENT_UNKNOWN).", "7"],
        ["Integrasi", "Bentuk request OpenRouter (structured output), Apify run-sync, Gmail MIME; timeout Gmail menjadi SENT_UNKNOWN; tab dan baris Sheets; JWT service account; OAuth dengan PKCE.", "10"],
        ["Enrichment LinkedIn", "Lead tanpa URL tidak memanggil Apify; URL identik menjadi petunjuk identitas; halaman yang tidak menyebut perusahaan dibuang.", "4"],
        ["Lead manual", "Nama + deskripsi cukup; instansi dan peran dibaca dari deskripsi; riset orang hanya memakai halaman yang menyebut nama dan instansi.", "6"],
        ["Satu penerima", "Kuota satu penerima dijaga saat tambah lead, approval, dan scheduler.", "2"],
        ["Mode draf", "Tanpa kredensial Gmail aplikasi tetap berjalan; draf difinalkan tanpa email penerima; tidak ada pengiriman; unduhan .eml.", "4"],
        ["API", "Semua endpoint berjalan di event loop yang sama dengan agen.", "1"],
    ], [1900, 7278, 800]),
    SPACER,
    para(("b", "Hasil simulasi 100 lead fiktif."),
         " Campaign per lead diproses oleh dua runtime (3 + 2 worker) dengan layanan tiruan. Hasilnya dirangkum pada tabel berikut. "
         "Komposisi keputusan berbeda dari ilustrasi Bagian 8.1 (80/15/5) karena data fiktif sengaja memuat kasus uji."),
    table(["Indikator", "Hasil pada simulasi"], [
        ["Keputusan Security", "76 PASS, 14 REVIEW (13 identitas ambigu, 1 halaman memuat prompt injection), 10 BLOCK (7 tanpa izin, 2 email invalid, 1 duplikat)."],
        ["Koordinasi agen", "1.012 pesan antaragen: 200 CFP, 200 PROPOSE, 100 ACCEPT, 100 REJECT, 244 INFORM_RESULT, 79 REQUEST ke Security."],
        ["Mobilitas", "2 task dipindah dari runtime A ke B di tengah proses; generation naik ke 2 dan task selesai dari checkpoint."],
        ["Pengiriman", "4 draft disetujui; 1 diterima Gmail tiruan (penerima di allowlist), 3 diblokir karena di luar allowlist."],
        ["Waktu", "100 lead selesai dalam ±48 detik; rata-rata persiapan 2,7 detik per lead (p95 3,2 detik). Latensi layanan tiruan dibuat 0,6–1,6 detik, sehingga angka ini bukan ukuran kinerja nyata."],
    ], [2400, 7578]),
    SPACER,
    para(("b", "Belum diuji:"),
         " kualitas email dari LLM sungguhan, run nyata actor Apify, pengiriman Gmail ke penerima nyata, dan pembandingan A/B/C pada Bagian 9.1. "
         "Keempatnya menjadi langkah berikutnya dan perlu anggaran layanan."),
]

# §8.4: prototipe yang telah dibangun (setelah catatan Gmail, sebelum §9)
inserts[i_gmail_note] = [
    para("Pada prototipe, lima dari enam lapisan di atas telah diuji otomatis (Bagian 9.3). Kegagalan Gmail diuji dengan transport tiruan; "
         "audit dan retensi data belum diuji."),
    PAGEBREAK,
    h2("8.4 Prototipe yang telah dibangun"),
    para("Prototipe Outreach Control merealisasikan alur Setup → Preview & Approval → Monitor. Seluruh tangkapan layar berikut diambil "
         "dalam mode simulasi dengan data fiktif (domain .example); label “Mode simulasi aktif” sengaja tetap ditampilkan."),
    figure("preview-approval.png", "Gambar 5. Preview & Approval: status keputusan Security per lead, draft email, dan jejak bukti bernomor (data fiktif, mode simulasi).",
           "Dashboard Preview & Approval berisi daftar 100 lead dengan status, draft email untuk Sinta Pramesti, dan jejak bukti dengan sumber CRM, Apify, dan web."),
    para(("b", "Jejak bukti."),
         " Kata di email yang berasal dari fakta ditandai nomor yang merujuk ke daftar bukti: sumber (CRM, Apify, atau web), waktu pengambilan, "
         "skor identitas, dan kutipan asli. Pengguna menyetujui versi draft tertentu; mengedit draft membatalkan approval lama."),
    figure("review-identitas.png", "Gambar 6. Review identitas: agen tidak menebak; kandidat diurutkan dengan skor S dan pengguna memilih (data fiktif).",
           "Panel review identitas dengan empat kandidat bernama Sinta beserta nilai d, n, c, r, dan S, serta tombol Pilih.", max_h=5200000),
    para(("b", "Perluasan dari rancangan."),
         " Tiga fitur ditambahkan berdasarkan kebutuhan pengguna selama pengembangan. (1) Lead manual: cukup nama lengkap dan deskripsi, "
         "misalnya “Dosen di UGM serta guru besar di sana”; agen membaca instansi dan peran dari deskripsi sebagai petunjuk pencarian, "
         "bukan sebagai fakta email. (2) Mode satu penerima: campaign dikunci untuk tepat satu orang di tiga lapis (tambah lead, approval, scheduler). "
         "(3) Mode draf: bila kredensial Gmail tidak diisi, keluaran berupa isi email yang difinalkan lalu disalin atau diunduh (.eml, CSV)."),
    figure("monitor.png", "Gambar 7. Monitor: alur task, runtime A/B beserta riwayat migrasi, antrean kirim, pemakaian layanan, dan pesan antaragen langsung.",
           "Halaman Monitor berisi alur task, dua runtime, riwayat migrasi A ke B, antrean kirim, pemakaian, dan log pesan antaragen.", max_w=5800000),
    figure("mode-draf-final.png", "Gambar 8. Mode draf: draf final dapat disalin atau diunduh sebagai .eml; aplikasi tidak mengirim email.",
           "Draf final untuk Azhari dengan tombol Salin subjek, Salin isi, Salin semua, dan Unduh .eml.", max_w=4800000),
]

# §8.2: rujukan mockup ke realisasi
inserts[i_fitur] = [para("Mockup ini telah direalisasikan pada prototipe; tangkapan layarnya ditunjukkan pada Bagian 8.4.")]

# §7.3: autentikasi pada prototipe
inserts[i_api2] = [
    para("Pada prototipe, akses Google Sheets memakai service account: spreadsheet cukup dibagikan ke email service account, tanpa token "
         "yang disalin manual [19]. Gmail memakai OAuth dengan PKCE melalui tombol “Hubungkan akun Google” dan hanya meminta izin kirim [18]. "
         "Token disimpan di berkas privat backend. Bila kredensial Gmail tidak diisi, aplikasi berjalan dalam mode draf."),
]

# §5.4: realisasi rancangan (setelah kotak "Batas lingkungan")
inserts[i_batas_ling + 1] = [
    PAGEBREAK,
    h2("5.4 Realisasi pada prototipe"),
    para("Rancangan pada Bagian 5.1–5.3 direalisasikan sebagai prototipe dengan backend Python (FastAPI) dan dashboard React + TypeScript. "
         "LLM diakses melalui OpenRouter dengan keluaran JSON sesuai skema [17]; model bawaan anthropic/claude-sonnet-5 dapat diganti lewat konfigurasi. "
         "Tabel berikut memetakan komponen rancangan ke implementasinya."),
    table(["Komponen rancangan", "Realisasi pada prototipe", "Batas yang disadari"], [
        ["Orchestrator / Broker", "State machine per lead; Contract Net ke runtime A/B (CFP, PROPOSE, ACCEPT/REJECT); checkpoint, lease, dan generation; pemulihan setelah restart.", "Runtime A/B berjalan dalam satu proses (mobilitas logis)."],
        ["Enrichment Agent", "Actor Apify berbasis URL LinkedIn; skor S dari Bagian 6.1; lead tanpa URL dilewati tanpa biaya; petunjuk instansi dari deskripsi lead manual.", "Keluaran actor dipetakan dari skema publik; belum diuji dengan run nyata."],
        ["Research Agent", "Firecrawl Search; halaman wajib menyebut perusahaan (atau nama dan instansi); filter prompt injection; kutipan fakta harus ada persis di sumber.", "Maksimal 3 fakta per draft."],
        ["Email Writer Agent", "Structured output (subject, body, used_fact_ids, warnings); maksimal 2 revisi; kalimat berhenti ditambahkan sistem.", "Kualitas bahasa LLM belum dinilai manusia."],
        ["Security & Quality Agent", "Rule engine: izin, suppression, duplikat, format email, angka tanpa bukti, fakta tak dikenal, insiden.", "Tanpa evaluator LLM; BLOCK tidak dapat dibatalkan LLM."],
        ["Scheduler & sender", "Gmail API dengan OAuth; kunci kirim; status SENDING disimpan sebelum kirim; SENT_UNKNOWN direkonsiliasi manual; allowlist.", "Mode draf bila kredensial Gmail tidak diisi."],
        ["Data Gateway", "Google Sheets 8 tab melalui service account; tulis batch; fallback berkas lokal.", "Satu proses penulis."],
        ["Dashboard", "Setup, Preview & Approval, Monitor, Koneksi; pesan antaragen langsung (SSE).", "Diuji di desktop 1440 px dan ponsel 390 px."],
    ], [2200, 4978, 2800]),
    SPACER,
]

for idx in sorted(inserts, reverse=True):
    blocks[idx + 1:idx + 1] = inserts[idx]

# ------------------------------------------------------------------ footer, relasi, media
footer = footer.replace("Rancangan sistem", "Rancangan &amp; prototipe")
rels = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>")
new_doc = head + "<w:body>" + "".join(blocks) + "</w:body>" + tail

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        if info.filename == "word/document.xml":
            data = new_doc.encode("utf-8")
        elif info.filename == "word/_rels/document.xml.rels":
            data = rels.encode("utf-8")
        elif info.filename == "word/footer1.xml":
            data = footer.encode("utf-8")
        else:
            data = zin.read(info.filename)
        zout.writestr(info, data)
    for name, path in new_media.items():
        zout.write(path, f"word/media/{name}")
print("blok:", len(blocks), "| gambar baru:", list(new_media), "| relasi baru:", len(new_rels))
