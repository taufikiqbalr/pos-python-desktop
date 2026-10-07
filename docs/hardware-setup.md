# Hardware Setup — ESC/POS & Cash Drawer

## Recommended topology

Untuk toko dengan beberapa workstation kasir, konfigurasi yang paling sederhana adalah printer thermal ESC/POS network per register:

```text
POS Desktop
    |
    +-- LAN --> ESC/POS Printer :9100
                    |
                    +-- RJ11/RJ12 --> Cash Drawer
```

Scanner barcode USB tetap menggunakan mode keyboard-wedge.

## Network printer

```env
POS_PRINTER_MODE=network
POS_PRINTER_HOST=192.168.1.100
POS_PRINTER_PORT=9100
POS_PRINTER_PROFILE=default
```

Lalu install dependency:

```powershell
pip install -r requirements-hardware.txt
```

Buka aplikasi -> **F12 Perangkat** -> **Test Printer ESC/POS**.

## USB printer

Cari Vendor ID (VID) dan Product ID (PID) printer dari Device Manager/USB tooling.

Contoh:

```env
POS_PRINTER_MODE=usb
POS_PRINTER_USB_VENDOR_ID=0x04b8
POS_PRINTER_USB_PRODUCT_ID=0x0202
POS_PRINTER_PROFILE=default
```

Nilai di atas hanya contoh. Gunakan VID/PID perangkat aktual.

## Cash drawer

Cash drawer diasumsikan terhubung ke port drawer printer thermal.

```env
POS_CASH_DRAWER_ENABLED=true
POS_CASH_DRAWER_PIN=2
```

Pin yang didukung adapter: `2` atau `5`.

Test dari **F12 Perangkat -> Buka Cash Drawer**.

Auto-open hanya untuk checkout yang mengandung pembayaran tunai:

```env
POS_AUTO_OPEN_DRAWER_CASH=true
```

## Auto print

```env
POS_AUTO_PRINT_RECEIPT=true
```

Jika printer gagal saat auto-print, transaksi **tetap tersimpan**. Kasir dapat reprint dari **F8 Riwayat** melalui tombol thermal atau Windows printer.

## Multi-register identity

Setiap PC kasir sebaiknya memiliki nilai register/device unik:

Kasir 1:

```env
POS_STORE_ID=BRIN-STORE-001
POS_REGISTER_ID=REG-01
POS_DEVICE_ID=POS-KASIR-01
```

Kasir 2:

```env
POS_STORE_ID=BRIN-STORE-001
POS_REGISTER_ID=REG-02
POS_DEVICE_ID=POS-KASIR-02
```

Jangan menggunakan `REGISTER_ID` yang sama untuk dua terminal aktif di toko yang sama.

## Windows packaged data

Pada executable PyInstaller, default data berada di:

```text
%LOCALAPPDATA%\KoperasiBRIN-POS\data\pos.db
%LOCALAPPDATA%\KoperasiBRIN-POS\receipts\
```

Untuk folder khusus, set:

```env
POS_DATA_DIR=C:\KoperasiBRIN-POS\data
POS_RECEIPT_DIR=C:\KoperasiBRIN-POS\receipts
```

Pastikan user Windows kasir mempunyai write permission ke folder tersebut.

## Troubleshooting

Jika test printer gagal:

1. Untuk network printer, tes konektivitas IP printer dan port TCP 9100.
2. Pastikan firewall tidak memblokir koneksi.
3. Untuk USB, pastikan VID/PID benar.
4. Install `requirements-hardware.txt`.
5. Nonaktifkan sementara auto print dan gunakan Windows Print Dialog jika kasir perlu tetap beroperasi.

Hardware failure tidak boleh menjadi alasan menghapus atau mengulang transaksi yang sudah sukses tersimpan.
