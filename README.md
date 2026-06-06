<p align="center">
  <h1 align="center">Streakify</h1>
  <p align="center">
    Jaga streak di berbagai platform secara otomatis, langsung dari HP Android kamu.
    <br />
    Dibangun khusus untuk <strong>Termux</strong>.
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Platform-Termux-black?style=flat-square&logo=android&logoColor=white" alt="Platform">
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Browser-Chromium-4285F4?style=flat-square&logo=googlechrome&logoColor=white" alt="Browser">
    <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
  </p>
</p>

---

## Apa Itu Streakify?

Streakify adalah tool otomasi Python yang berjalan di **Termux** (terminal Linux di Android). Tool ini membantu kamu menjaga streak di berbagai platform tanpa harus membuka aplikasi satu per satu setiap hari.

**Saat ini mendukung:**
- **TikTok** -- Kirim pesan otomatis ke chat untuk menjaga streak.

> Platform lain bisa ditambahkan di masa depan sebagai adapter terpisah.

---

## Cara Kerja

```
Kamu jalankan Streakify di Termux
        |
        v
Streakify buka Chromium secara otomatis (headless / tanpa tampilan)
        |
        v
Masuk ke halaman messages platform
        |
        v
Pilih chat --> Ketik pesan --> Kirim
        |
        v
Selesai. Streak aman.
```

---

## Yang Kamu Butuhkan

| Kebutuhan | Keterangan |
|-----------|------------|
| **HP Android** | Dengan penyimpanan cukup untuk Termux dan Chromium |
| **Termux** | Versi terbaru dari [F-Droid](https://f-droid.org/en/packages/com.termux/) (jangan dari Play Store) |
| **Internet** | Untuk install paket dan menjalankan automasi |
| **Termux:X11** | Hanya jika perlu login manual lewat browser (opsional) |

> **Penting:** Termux dari Play Store sudah tidak di-update dan sering bermasalah. Selalu install dari **F-Droid** atau dari [GitHub Releases Termux](https://github.com/termux/termux-app/releases).

---

## Instalasi

### Cara Cepat (Recommended)

Buka Termux, lalu jalankan:

```sh
# Clone repo
git clone https://github.com/Ren42377/streakify-termux.git
cd streakify-termux

# Install semua kebutuhan
sh install.sh
```

Script `install.sh` akan otomatis:
1. Update paket Termux
2. Install Python, Chromium, dan Termux:X11
3. Install dependency Python dari `requirements.txt`
4. Verifikasi Chromium dan ChromeDriver sudah tersedia

### Cara Manual

Jika kamu lebih suka install satu per satu:

```sh
pkg update
pkg install python x11-repo
pkg install chromium termux-x11-nightly
```

Clone repo dan install dependency Python:

```sh
git clone https://github.com/Ren42377/streakify-termux.git
cd streakify-termux
python -m pip install -r requirements.txt
```

Pastikan browser dan driver sudah ter-install:

```sh
chromium-browser --version
chromedriver --version
```

Jika salah satu perintah di atas error atau tidak ditemukan, cek kembali instalasi Chromium dari repo Termux.

---

## Konfigurasi

Sebelum menjalankan Streakify, sesuaikan file `config.txt` di folder utama project. File ini sudah berisi default yang bisa langsung dipakai.

### Edit Config

Buka `config.txt` dan sesuaikan sesuai kebutuhan:

```txt
tiktok=true
browser.headless=true
tiktok.message=gm
tiktok.max_chats=10
```

### Penjelasan Setiap Setting

| Setting | Nilai | Fungsi |
|---------|-------|--------|
| `tiktok` | `true` / `false` | Aktifkan atau matikan flow TikTok |
| `browser.headless` | `true` / `false` | `true` = browser tanpa tampilan (lebih cepat). `false` = browser dengan jendela (butuh Termux:X11) |
| `tiktok.message` | teks apapun | Pesan yang akan dikirim ke setiap chat. Mendukung emoji jika file disimpan sebagai UTF-8 |
| `tiktok.max_chats` | angka positif | Jumlah chat yang diproses dalam satu kali jalan |

> **Tips:** Untuk pemakaian sehari-hari, gunakan `browser.headless=true`. Mode ini lebih cepat dan tidak butuh Termux:X11.

---

## Cara Pakai

### Jalankan Streakify

```sh
sh run.sh
```

Atau langsung lewat Python:

```sh
python -m streakify tiktok
```

### Pertama Kali Pakai (Login)

Saat pertama kali dijalankan, kamu perlu login ke TikTok:

1. Jika `browser.headless=true` dan DISPLAY tersedia, Streakify otomatis membuka browser dengan jendela untuk login.
2. Login ke akun TikTok kamu di browser yang muncul.
3. Setelah login berhasil, tekan **Enter** di Termux.
4. Session akan tersimpan, jadi kamu tidak perlu login lagi di run berikutnya.

> **Butuh Termux:X11?** Hanya saat login manual pertama kali. Setelah session tersimpan, kamu bisa pakai mode headless terus.

### Memindahkan Data Runtime

Secara default, semua data runtime (profil browser, cache driver) disimpan di:

```
$HOME/.streakify/
```

Jika ingin lokasi berbeda:

```sh
STREAKIFY_HOME="$HOME/.streakify-alt" sh run.sh
```

> Jangan arahkan `STREAKIFY_HOME` ke folder repo atau shared storage Android, karena Chromium bisa gagal membuat file kunci.

---

## Troubleshooting

### Browser Gagal Start

Cek hal-hal berikut:

```sh
# Apakah Chromium ter-install?
chromium-browser --version

# Apakah ChromeDriver ter-install?
chromedriver --version

# Apakah config.txt sudah benar?
cat config.txt
```

### Login Diminta Terus

Session mungkin expired. Hapus profil browser dan login ulang:

```sh
rm -rf $HOME/.streakify/auth/selenium-profile
sh run.sh
```

### Termux:X11 Bermasalah

Jika mode headful atau login manual tidak bisa jalan:

```sh
# Apakah Termux:X11 ter-install?
command -v termux-x11

# Cek status service
sv status tx11

# Cek display file
cat $PREFIX/var/run/tx11.display
```

> **Alternatif:** Jika tidak mau repot dengan Termux:X11, pastikan kamu login dulu lewat cara lain, lalu jalankan dengan `browser.headless=true`.

### Error "Config error"

Streakify akan menolak jalan dan menampilkan pesan jelas jika:
- Ada setting yang hilang
- Nama setting salah ketik
- Value kosong atau tidak valid
- Memakai setting yang sudah deprecated

Ikuti petunjuk di pesan error untuk memperbaiki `config.txt`.

---

## Struktur Project

```
streakify-termux/
├── install.sh              # Script instalasi otomatis
├── run.sh                  # Script untuk menjalankan Streakify
├── config.txt              # Konfigurasi (edit sesuai kebutuhan)
├── requirements.txt        # Dependency Python
├── LICENSE                 # Lisensi MIT
├── README.md               # Dokumentasi (file ini)
└── streakify/              # Package Python utama
    ├── __init__.py
    ├── __main__.py          # Entry point CLI
    ├── browser.py           # Setup dan manajemen browser
    ├── config.py            # Parsing dan validasi config
    ├── results.py           # Data class untuk hasil run
    ├── runtime_paths.py     # Path management
    └── tiktok.py            # Adapter automasi TikTok
```

---

## FAQ

**Q: Apakah ini aman?**
A: Streakify berjalan di HP kamu sendiri dan tidak mengirim data ke server manapun. Session browser disimpan secara lokal di `$HOME/.streakify/`. Pastikan kamu tidak membagikan folder ini ke orang lain.

**Q: Apakah akun bisa kena ban?**
A: Streakify menggunakan browser sungguhan (Chromium), bukan API tidak resmi. Tapi setiap automasi punya risiko. Gunakan dengan bijak dan jangan set `max_chats` terlalu tinggi.

**Q: Bisa dijadwalkan otomatis setiap hari?**
A: Belum ada fitur scheduling bawaan, tapi kamu bisa pakai `crond` atau `termux-job-scheduler` untuk menjalankan `sh run.sh` secara berkala.

**Q: HP harus root?**
A: Tidak perlu root. Streakify berjalan sepenuhnya di dalam Termux.

**Q: Bisa tambah platform lain?**
A: Bisa. Streakify didesain modular. Setiap platform adalah adapter terpisah di folder `streakify/`.

---

## Lisensi

[MIT License](LICENSE) -- bebas digunakan, dimodifikasi, dan didistribusikan.
