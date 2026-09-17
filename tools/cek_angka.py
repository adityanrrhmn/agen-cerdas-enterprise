"""Hitung ulang angka turunan di laporan dari asumsinya, lalu pastikan teks laporan memuat hasil yang sama.

Pemakaian: python tools/cek_angka.py <laporan.md hasil pandoc>
Keluar 0 bila semua lulus, 1 bila ada yang gagal. Jika asumsi di laporan diubah,
perbarui konstanta di bawah terlebih dahulu (asumsi = sumber kebenaran, bukan teks hasil).
"""
import math
import sys


def fmt(x, nd):
    """Format angka gaya Indonesia: koma desimal."""
    return f"{x:.{nd}f}".replace(".", ",")


def main(path):
    sys.stdout.reconfigure(encoding="utf-8")  # konsol Windows cp1252 gagal mencetak "−" dan "×"
    text = open(path, encoding="utf-8").read().replace("\\", "")
    flat = " ".join(text.split())
    checks = []

    def expect(label, needle):
        checks.append((label, needle, needle in flat))

    # 6.1 skor entity linking: S = 0,40d + 0,30n + 0,20c + 0,10r
    w = (0.40, 0.30, 0.20, 0.10)
    a = sum(wi * v for wi, v in zip(w, (1.00, 0.95, 0.90, 0.80)))
    b = sum(wi * v for wi, v in zip(w, (0.00, 0.95, 0.10, 0.05)))
    expect("skor A", fmt(a, 3))
    expect("skor B", fmt(b, 3))
    expect("selisih A-B", f"{fmt(a, 3)} − {fmt(b, 3)} = {fmt(a - b, 3)}")

    # 9.2 kinerja persiapan
    per_lead, n, p, o = 6 + 4 + 3 + 2, 100, 5, 30
    t_static = n * per_lead
    t_multi = math.ceil(n / p) * per_lead + o
    expect("per lead", f"= {per_lead} dtk")
    expect("T_statis", f"{t_static:,}".replace(",", ".") + " dtk")
    expect("T_multi", f"= {t_multi} dtk")
    expect("speedup", fmt(t_static / t_multi, 2) + "×")
    expect("reduksi", f"{round((t_static - t_multi) / t_static * 100)}%")

    # migrasi dan komunikasi
    expect("migrasi", f"pengurangan {35 - (3 + 10)} detik")
    k = 5
    star, mesh = 2 * (k - 1), k * (k - 1)
    expect("pesan bintang", f"= {star} pesan")
    expect("pesan mesh", f"= {mesh} pesan")
    expect("selisih pesan", f"{round((mesh - star) / mesh * 100)}%")

    # 7.2 dan 8.1 penjumlahan
    assert 700 + 150 + 150 == 1000 and 80 + 15 + 5 == 100
    expect("split dataset", "700 train / 150 validation / 150 test")
    expect("hasil seleksi", "100 diminta = 80 siap approval + 15 perlu review + 5 diblokir")

    failed = 0
    for label, needle, ok in checks:
        print(f"{'LULUS' if ok else 'GAGAL'}  {label}: {needle}")
        failed += not ok
    print(f"Ringkasan cek angka: {len(checks) - failed} lulus, {failed} gagal")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
