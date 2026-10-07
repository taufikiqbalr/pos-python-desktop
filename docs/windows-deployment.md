# Windows Deployment

## Local build

Pada Windows PowerShell:

```powershell
git clone https://github.com/taufikiqbalr/pos-python-desktop.git
cd pos-python-desktop
./scripts/build_windows.ps1
```

Hasil:

```text
dist\KoperasiBRIN-POS.exe
```

Build memasukkan dependency PySide6 dan python-escpos sehingga satu executable dapat menggunakan mode printer disabled, network, atau USB.

## GitHub Actions build

Workflow:

```text
.github/workflows/build-windows.yml
```

Build dapat dijalankan:

- manual melalui Workflow Dispatch;
- saat tag `v*` dibuat;
- ketika file packaging utama berubah pada branch `main`.

Artifact:

```text
KoperasiBRIN-POS-windows
  └── KoperasiBRIN-POS.exe
```

## Per-terminal configuration

Environment variable dapat didefinisikan pada Windows System/User Environment Variables atau melalui launcher script. Jangan bake API token rahasia ke executable atau repository.

Minimum recommended terminal configuration:

```env
POS_STORE_ID=BRIN-STORE-001
POS_REGISTER_ID=REG-01
POS_DEVICE_ID=POS-KASIR-01
POS_PRINTER_MODE=network
POS_PRINTER_HOST=192.168.1.100
POS_CASH_DRAWER_ENABLED=true
```

## Production hardening before wide rollout

Sebelum distribusi luas:

1. Code-sign executable.
2. Gunakan managed installer/MSI.
3. Backup SQLite runtime folder.
4. Aktifkan central sync endpoint.
5. Pastikan setiap register mempunyai identity unik.
6. Simpan API token melalui mekanisme secret/config deployment, bukan source code.
7. Uji thermal printer, drawer, scanner, offline transaction, restart recovery, dan refund.
