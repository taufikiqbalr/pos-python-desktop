# Koperasi BRIN Point of Sales — Python Desktop

Aplikasi Point of Sales (PoS) desktop untuk kasir toko, dibangun dengan **Python + PySide6 (Qt for Python)** dan **SQLite**. Repository ini fokus pada aktivitas front-counter/kasir. Inventory management, stock opname, procurement, dan administrasi user direncanakan sebagai aplikasi/service terpisah.

## Status

**Operational Cashier MVP**

Alur inti yang sudah didukung:

```text
Login -> Buka Shift -> Scan/Cari Barang -> Cart
      -> Diskon Item/Transaksi
      -> Hold/Resume (opsional)
      -> Split/Single Payment
      -> Simpan Transaksi -> Cetak Struk
      -> Riwayat/Reprint/Void
      -> Tutup Shift & Rekonsiliasi Kas
```

## Fitur PoS

### Login & otorisasi

- Login kasir berbasis username/password.
- Password lokal disimpan dengan PBKDF2-SHA256.
- Role demo `cashier` dan `supervisor`.
- Void transaksi selesai membutuhkan username/password supervisor/admin dan alasan void.

### Shift kasir

- Buka shift dengan input kas awal.
- Satu open shift per kasir.
- Checkout hanya dapat dilakukan jika shift aktif.
- Tutup shift dengan:
  - jumlah transaksi;
  - total penjualan;
  - breakdown metode pembayaran;
  - kas awal;
  - penerimaan tunai;
  - kembalian;
  - expected cash;
  - actual closing cash;
  - cash difference;
  - catatan penutupan.

### Scan, pencarian, dan cart

- Scan barcode menggunakan barcode scanner USB keyboard-wedge.
- Input SKU/barcode manual.
- Cari produk berdasarkan nama, SKU, atau barcode.
- Tambah, kurangi, dan hapus item.
- Validasi stok saat item dimasukkan dan saat checkout.
- Diskon per item (%).
- Diskon transaksi (%).
- Pajak terkonfigurasi.
- Perhitungan subtotal, diskon, pajak, dan grand total otomatis.

### Hold / park transaction

- Hold transaksi yang belum selesai.
- Menyimpan:
  - pelanggan;
  - item dan qty;
  - diskon item;
  - diskon transaksi;
  - catatan.
- Daftar transaksi hold per kasir.
- Resume transaksi hold.
- Stok divalidasi ulang saat transaksi hold dilanjutkan.
- Hold **tidak** melakukan reservasi stok.

### Pembayaran

Metode pembayaran:

- Tunai.
- QRIS.
- Kartu Debit/Kredit.
- Transfer.

Mendukung:

- Single tender.
- **Split payment / dua metode pembayaran**.
- Nominal pembayaran.
- Uang pas.
- Perhitungan kekurangan pembayaran.
- Perhitungan kembalian.
- Kelebihan pembayaran hanya diperbolehkan jika terdapat komponen tunai.

### Transaksi dan struk

- Nomor invoice otomatis.
- Header + detail item transaksi.
- Detail metode pembayaran pada tabel `sale_payments`.
- Transactional database write dengan `BEGIN IMMEDIATE`.
- Pengurangan stok dilakukan dalam transaksi database yang sama dengan penjualan.
- Preview struk.
- Print melalui Qt Printer.
- Arsip struk TXT.
- Riwayat transaksi.
- Reprint struk.
- Status transaksi `COMPLETED` / `VOIDED`.

### Void transaksi

Void transaksi selesai:

1. Kasir memilih transaksi dari riwayat.
2. Supervisor/admin memasukkan kredensial.
3. Alasan void wajib diisi.
4. Status transaksi menjadi `VOIDED`.
5. Stok barang dikembalikan secara transactional.
6. Transaksi void tidak dihitung dalam settlement shift.

Untuk menjaga integritas settlement, transaksi yang berasal dari **shift yang sudah ditutup tidak dapat di-void**. Kasus tersebut nantinya ditangani melalui workflow **return/refund**, bukan void.

## Shortcut kasir

| Shortcut | Fungsi |
|---|---|
| `F2` | Fokus scan barcode |
| `F3` | Cari produk |
| `F4` | Bayar |
| `F5` | Hold transaksi |
| `F6` | Transaksi baru |
| `F7` | Daftar / resume hold |
| `F8` | Riwayat transaksi |
| `F9` | Buka / tutup shift |

## Arsitektur

```mermaid
flowchart LR
    UI[Qt Desktop UI] --> AUTH[AuthService]
    UI --> CAT[CatalogService]
    UI --> SALE[SaleService]
    UI --> SHIFT[ShiftService]
    UI --> RECEIPT[ReceiptService]

    AUTH --> DB[(SQLite)]
    CAT --> DB
    SALE --> DB
    SHIFT --> DB
    RECEIPT --> PRINT[Printer / TXT Receipt]

    CAT -. future .-> INV[Inventory Service]
    SALE -. future stock movement .-> INV
    AUTH -. future .-> IAM[User Management / IAM]
```

Struktur kode:

```text
.
├── .github/
│   └── workflows/
│       └── tests.yml
├── main.py
├── app/
│   ├── config.py
│   ├── database.py
│   ├── domain.py
│   ├── security.py
│   ├── services.py
│   └── ui/
│       ├── dialogs.py
│       ├── login_window.py
│       ├── pos_window.py
│       └── styles.py
├── tests/
│   ├── test_domain.py
│   ├── test_security.py
│   └── test_services.py
├── receipts/
└── requirements.txt
```

## Menjalankan aplikasi

Direkomendasikan Python 3.11+.

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Database `data/pos.db` dibuat otomatis saat aplikasi pertama kali dijalankan. Database versi MVP lama akan mendapat lightweight migration ketika aplikasi baru dijalankan.

### Akun demo

| Role | Username | Password |
|---|---|---|
| Kasir | `kasir` | `kasir123` |
| Supervisor | `supervisor` | `supervisor123` |

> Akun demo hanya untuk development. Production login harus diarahkan ke User Management/IAM terpusat.

## Produk demo dan barcode scanner

Aplikasi mengisi beberapa data awal merchandise BRIN, ATK, minuman, dan snack.

Barcode scanner USB pada umumnya bekerja sebagai keyboard-wedge: scanner mengetik barcode ke field aktif kemudian mengirim Enter sehingga tidak memerlukan SDK vendor tertentu.

Contoh barcode demo:

```text
8997001000059 -> Mug BRIN
8997002000010 -> Air Mineral 600ml
```

## Konfigurasi environment

```env
POS_STORE_NAME=Toko Koperasi BRIN
POS_STORE_ADDRESS=Badan Riset dan Inovasi Nasional
POS_STORE_PHONE=-
POS_TAX_PERCENT=0
POS_DB_PATH=/path/to/pos.db
POS_RECEIPT_DIR=/path/to/receipts
```

## Test dan CI

Lokal:

```bash
python -m compileall -q app main.py tests
python -m unittest discover -s tests -v
```

GitHub Actions menjalankan syntax check dan unit/service tests pada setiap push ke `main` dan pull request.

Test mencakup:

- cart, diskon item, diskon transaksi, dan pajak;
- password hashing;
- split payment;
- open/close shift dan cash reconciliation;
- hold transaction;
- supervised void dan stock restoration.

## Boundary dengan Inventory & User Management

SQLite masih menyimpan `products` dan `users` agar PoS dapat berjalan standalone untuk development/demo. Namun UI tidak mengakses tabel tersebut langsung.

Integration target:

1. `CatalogService` -> Inventory API untuk SKU, barcode, harga, dan stock availability.
2. Checkout/void/refund -> Inventory API untuk stock movement.
3. `AuthService` -> User Management/IAM API.
4. PoS tetap menjadi front-counter client dan tidak menjadi master inventory/user.

## Fitur berikutnya sebelum production rollout

Fitur yang masih layak ditambahkan setelah MVP ini:

- return/refund untuk transaksi dari shift/hari sebelumnya;
- customer/member lookup dan harga/promosi anggota koperasi;
- cash-in/cash-out selama shift;
- ESC/POS thermal printer adapter dan cash-drawer trigger;
- store/register/device identity;
- audit event yang lebih detail untuk perubahan harga/diskon/void;
- offline sync queue ke backend pusat;
- database backup/restore;
- konfigurasi hak diskon maksimum per role;
- receipt QR code / digital receipt.

Inventory master, stock opname, purchase/receiving, supplier, dan user administration **tidak** dimasukkan ke repository ini.
