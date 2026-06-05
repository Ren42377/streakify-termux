# Streakify

Streakify adalah automation tool Python untuk menjaga streak di beberapa platform dari Termux.

Status saat ini masih tahap awal. Fitur TikTok sudah bisa membuka messages, mengecek session, memilih chat, dan menjalankan message dry-run melalui Chromium dan Selenium.

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
pkg install chromium termux-x11-nightly
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

tiktok.dry_run=true membuat Streakify memilih chat dan mengisi pesan tanpa mengirim. Untuk benar-benar mengirim pesan, ubah:

```text
tiktok.dry_run=false
```

tiktok.max_chats mengatur jumlah chat yang diproses dalam satu run. Defaultnya `1`.

Jangan commit token, cookie, credential, atau session file.

## Penggunaan

Jalankan flow TikTok:

```sh
sh run.sh
```

Atau langsung lewat Python:

```sh
python -m streakify tiktok
```

Jika belum login dan mode headless aktif, Streakify akan mencoba membuka browser headful saat `DISPLAY` tersedia. Untuk debugging visual, jalankan Termux:X11 lebih dulu, lalu ulang command.

Untuk debugging visual yang langsung membuka browser headful:

```sh
sh debug.sh
```

Script ini mencoba menyalakan service `tx11`, membaca display aktif, lalu menjalankan TikTok check dengan mode headless dimatikan sementara.

## Troubleshooting

Jika browser gagal start, cek:

- `chromium-browser --version`
- `chromedriver --version`
- isi `config.txt`
- apakah Termux:X11 sudah aktif saat memakai mode headful
- `sv status tx11`
- `cat $PREFIX/var/run/tx11.display`

Jika TikTok meminta login, selesaikan login manual di browser lalu tekan Enter di Termux.
