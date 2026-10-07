# POS Integration Contract

Dokumen ini mendefinisikan kontrak awal antara aplikasi kasir desktop dan service eksternal. Endpoint dapat diimplementasikan pada repository backend terpisah selama bentuk payload berikut dipertahankan atau adapter POS disesuaikan.

## 1. Inventory API

Base URL dikonfigurasi melalui:

```env
POS_INVENTORY_API_URL=https://inventory.example.internal
POS_BUSINESS_API_TOKEN=...
```

### Lookup product

```http
GET /api/v1/products/lookup?code=8997001000059
Authorization: Bearer <token>
```

Response:

```json
{
  "data": {
    "id": "optional-upstream-id",
    "sku": "BRIN-MG-001",
    "barcode": "8997001000059",
    "name": "Mug BRIN",
    "unit": "pcs",
    "price": 55000,
    "stock": 30,
    "active": true
  }
}
```

### Search product

```http
GET /api/v1/products/search?q=mug&limit=100
```

Response dapat berupa array langsung atau:

```json
{
  "data": {
    "items": [
      {
        "sku": "BRIN-MG-001",
        "barcode": "8997001000059",
        "name": "Mug BRIN",
        "unit": "pcs",
        "price": 55000,
        "stock": 30,
        "active": true
      }
    ]
  }
}
```

Produk remote di-cache ke tabel lokal `products`. Jika API tidak tersedia dan `POS_INTEGRATION_FALLBACK_LOCAL=true`, cache lokal digunakan.

## 2. Membership API

```env
POS_MEMBERSHIP_API_URL=https://membership.example.internal
```

### Search member

```http
GET /api/v1/members/search?q=BRIN-0001&limit=100
```

Response:

```json
{
  "data": [
    {
      "member_no": "BRIN-0001",
      "name": "Nama Anggota",
      "phone": "08123456789",
      "email": "anggota@example.org",
      "membership_type": "MEMBER",
      "active": true
    }
  ]
}
```

`member_no` dan `name` wajib ada. Hasil remote di-cache ke tabel lokal `customers`.

## 3. Pricing API

Client awal sudah tersedia tetapi belum mengubah harga transaksi secara otomatis.

```http
POST /api/v1/pricing/quote
Content-Type: application/json
```

Request:

```json
{
  "member_no": "BRIN-0001",
  "store_id": "BRIN-STORE-001",
  "items": [
    {
      "sku": "BRIN-MG-001",
      "qty": 2,
      "unit_price": 55000
    }
  ]
}
```

Response:

```json
{
  "data": {
    "quote_id": "Q-20261007-001",
    "line_discounts": [
      {
        "sku": "BRIN-MG-001",
        "discount_percent": 10,
        "reason": "Member promo"
      }
    ],
    "cart_discount_percent": 5,
    "messages": [
      "Promo anggota diterapkan"
    ]
  }
}
```

PoS hanya menerapkan `discount_percent` yang dikembalikan Pricing API. Nilai di luar 0–100 ditolak. Tombol **Cek Promo** tidak aktif jika Pricing API belum dikonfigurasi. Dengan demikian aturan promo/member price/voucher tetap server-authoritative, bukan hard-coded pada desktop client.

## 4. POS Event Sync API

Aplikasi menggunakan transactional outbox. Transaksi lokal tidak menunggu koneksi backend.

```env
POS_SYNC_ENABLED=true
POS_SYNC_API_URL=https://pos-backend.example.internal
POS_SYNC_API_TOKEN=...
```

Endpoint:

```http
POST /api/v1/pos/events
Content-Type: application/json
Authorization: Bearer <token>
Idempotency-Key: pos-outbox-123
```

Envelope:

```json
{
  "event_type": "sale.completed",
  "aggregate_type": "sale",
  "aggregate_id": "POS-20261007-080000-1234",
  "terminal": {
    "store_id": "BRIN-STORE-001",
    "register_id": "REG-01",
    "device_id": "POS-KASIR-01"
  },
  "payload": {}
}
```

Event types saat ini:

- `shift.opened`
- `shift.closed`
- `sale.completed`
- `sale.voided`
- `refund.completed`
- `cash.in`
- `cash.out`

Backend **harus memperlakukan `Idempotency-Key` secara idempotent**. Retry event yang sama tidak boleh menggandakan stock movement, transaksi, atau financial posting.

## 5. Offline semantics

1. Transaksi kasir ditulis ke SQLite dalam local transaction.
2. Event integration ditulis ke `integration_outbox` dalam transaction yang sama.
3. Status awal event adalah `PENDING`.
4. Sync berhasil -> `SENT`.
5. Sync gagal -> `FAILED`, `attempts` bertambah dan `last_error` tersimpan.
6. Event `FAILED` dapat dikirim ulang melalui menu **Perangkat & Sinkronisasi**.

Dengan pola ini, gangguan internet tidak menghentikan transaksi front-counter.

## 6. Source of truth target

Saat integrasi penuh:

- Inventory Service: master SKU, barcode, price base, availability dan stock movement.
- Membership Service: master anggota koperasi.
- Pricing Service: promo/member pricing/voucher.
- User/IAM Service: akun, role, permission dan supervisor approval.
- POS Desktop: front-counter UX, local resilience, printer/cash drawer, local shift state.
- POS Backend/Event Consumer: central transaction ledger, reporting, reconciliation dan downstream integration.
