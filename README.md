# Streakify

Streakify adalah automation tool Python untuk menjaga streak di beberapa platform dari Termux.

Status saat ini masih tahap awal. Fitur pertama hanya mengecek session TikTok melalui browser Chromium dan Selenium.

## Kebutuhan

- Termux terbaru dari F-Droid atau sumber resmi Termux.
- Python.
- Chromium dan ChromeDriver yang cocok.
- Akses internet.
- Termux:X11 jika ingin melihat browser saat debugging.

## Instalasi

Cara paling mudah:

```sh
sh install.sh
```

Atau install manual:

```sh
pkg update
pkg install python
pkg install x11-repo
pkg install chromium
python -m pip install -r requirements.txt
```

Pastikan browser dan driver tersedia:

```sh
chromium-browser --version
chromedriver --version
```

Jika salah satu command tidak ditemukan, cek kembali paket Chromium dari repo Termux atau Termux X11.

## Konfigurasi

Edit `config.txt` jika path browser atau driver di HP kamu berbeda.

Default profile browser disimpan di `~/.streakify/selenium-profile`.

Jangan simpan profile browser di folder `/storage/emulated/0/...` karena Chromium bisa gagal membuat lock file di shared storage Android.

Jangan commit token, cookie, credential, atau session file.

## Penggunaan

Jalankan pengecekan session TikTok:

```sh
sh run.sh
```

Atau langsung lewat Python:

```sh
python -m streakify tiktok
```

Jika belum login dan mode headless aktif, Streakify akan mencoba membuka browser headful saat `DISPLAY` tersedia. Untuk debugging visual, jalankan Termux:X11 lebih dulu, lalu ulang command.

## Troubleshooting

Jika browser gagal start, cek:

- `chromium-browser --version`
- `chromedriver --version`
- isi `config.txt`
- apakah Termux:X11 sudah aktif saat memakai mode headful

Jika TikTok meminta login, selesaikan login manual di browser lalu tekan Enter di Termux.
