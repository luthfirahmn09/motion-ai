# SETUP.md — Daftar Akun & Konfigurasi

Semua yang perlu didaftar/dikonfigurasi sebelum bot bisa jalan.

---

## 1. Telegram Bot

**Daftar via:** @BotFather di Telegram

```
1. Buka Telegram → cari @BotFather
2. Kirim: /newbot
3. Isi nama bot (contoh: "Motion Affiliate Bot")
4. Isi username bot (harus diakhiri "bot", contoh: "motion_affiliate_bot")
5. Simpan token yang diberikan → isi ke TELEGRAM_BOT_TOKEN di .env
```

**Set command list (opsional tapi disarankan):**
```
/setcommands → pilih bot → paste:
buat - Buat video affiliate baru
status - Cek status job terakhir
cancel - Batalkan proses
```

---

## 2. Replicate API (Kling v3 Motion Control)

**Daftar via:** https://replicate.com

```
1. Sign up / login di replicate.com
2. Klik avatar pojok kanan atas → Account Settings
3. Sidebar → API tokens → Create token
4. Simpan token → isi ke REPLICATE_API_TOKEN di .env
```

**Model yang dipakai:** `kwaivgi/kling-v3-motion-control`

**Harga estimasi:**
| Mode | Harga/detik output | Video 10 detik |
|------|-------------------|----------------|
| std (720p) | ~$0.01–0.02 | ~$0.10–0.20 |
| pro (1080p) | ~$0.03–0.05 | ~$0.30–0.50 |

**Tambah kredit:** replicate.com → Billing → Add credits (kartu kredit/PayPal)

---

## 3. Cloudflare R2 (Object Storage)

**Gratis:** 10 GB storage + 1 juta operasi/bulan

**Daftar via:** https://cloudflare.com

```
1. Sign up / login di dash.cloudflare.com
2. Sidebar kiri → R2 Object Storage
3. Klik "Create bucket"
   - Nama bucket: motion-transfer-bot (atau terserah)
   - Region: auto
4. Buka bucket → Settings → catat nama bucket
5. Kembali ke R2 halaman utama → "Manage R2 API Tokens"
6. Klik "Create API Token"
   - Permissions: Object Read & Write
   - Specify bucket: pilih bucket yang baru dibuat
7. Simpan:
   - Access Key ID → S3_ACCESS_KEY_ID
   - Secret Access Key → S3_SECRET_ACCESS_KEY
   - Endpoint format: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
     (ACCOUNT_ID ada di halaman R2 utama, pojok kanan atas)
     → S3_ENDPOINT_URL
```

**Alternatif:** AWS S3 (berbayar, setup sama tapi endpoint = https://s3.amazonaws.com)

---

## 4. Server / VPS (untuk deploy)

Bot butuh:
- IP publik + domain (untuk webhook Telegram)
- Docker + docker-compose terinstall
- Port 8080 terbuka

**Rekomendasi VPS murah:**
| Provider | Spec minimum | Estimasi harga |
|----------|-------------|----------------|
| Hetzner | CX21 (2 vCPU, 4GB RAM) | €4–6/bulan |
| DigitalOcean | Basic Droplet 2GB | $12/bulan |
| Contabo | VPS S | €5/bulan |

**Domain:**
- Beli domain di Namecheap / Niagahoster / dll
- Arahkan A record ke IP server
- Pasang SSL: `certbot --nginx -d yourdomain.com`
- Isi `WEBHOOK_URL=https://yourdomain.com` di .env

---

## 5. Checklist .env

Setelah semua daftar, pastikan semua ini terisi di `.env`:

```bash
# Wajib diisi — bot tidak akan jalan tanpa ini
TELEGRAM_BOT_TOKEN=          # dari @BotFather
WEBHOOK_URL=                 # https://yourdomain.com
REPLICATE_API_TOKEN=         # dari replicate.com
S3_ENDPOINT_URL=             # dari Cloudflare R2
S3_ACCESS_KEY_ID=            # dari Cloudflare R2
S3_SECRET_ACCESS_KEY=        # dari Cloudflare R2
S3_BUCKET_NAME=              # nama bucket yang dibuat

# Sudah ada default, bisa diubah nanti
DATABASE_URL=postgresql://user:password@postgres:5432/motionbot
REDIS_URL=redis://redis:6379/0
KLING_MODE=std
KLING_DURATION=10
MAX_JOBS_PER_USER_PER_DAY=10
CELERY_CONCURRENCY=20
```

---

## 6. Urutan Setup

```
1. Daftar semua akun di atas
2. Clone repo → cp .env.example .env → isi .env
3. Install Docker + docker-compose di server
4. Upload kode ke server (git clone / scp)
5. docker-compose run --rm bot alembic upgrade head   # buat tabel DB
6. docker-compose up -d --build                        # jalankan semua
7. docker-compose ps                                   # verifikasi semua running
8. Test bot di Telegram: kirim /start
```
