# FACETTE — Pazaryeri Entegrasyon Mimarisi

> Yönetişim dokümanı · Tek Kaynak / Adaptör modeli
> Sahip ajanlar: 🔌 ENTEGRASYON (birincil) · 🏗️ MİMAR · ⚡ PERFORMANS · 🔒 GÜVENLİK · 🚢 DEVOPS
> `FACETTE_AJAN_MIMARISI.md` protokolüne tabidir. Ticimax-bağımsız; yeni kuplaj yasaktır.

---

## 0. ALTIN KURALLAR (ihlal edilemez)

1. **Tek Kaynak.** Ürünün tüm değerleri *kanonik üründe* nötr durur. Her kanal buradan okur.
2. **Trendyol yalnızca yapısal referanstır.** Yeni bir kanal için veri üretirken **Trendyol'dan veri çekilmez**, Trendyol'un payload formatı kopyalanmaz. Kanal, **kanonikten** okur ve **kendi API'sinin istediği** formatta gönderir.
3. **Trendyol bozulmaz.** Tüm değişiklikler eklemeli (additive) ve geri alınabilir olmalı. Trendyol akışına dokunan her şey ayrı fazda, feature-flag arkasında.
4. **Kanallar birbirinden bağımsızdır.** Kanal A'nın çözümleyici/özellik/varsayılan ayarı, Kanal B'yi etkilemez.

---

## 1. Katmanlar

```
┌──────────────────────────────────────────────────────────┐
│  KANONİK ÜRÜN  (products koleksiyonu, platform-bağımsız)  │
│  başlık · stok · fiyat · açıklama · marka · nötr özellik  │
└───────────────┬──────────────────────────────────────────┘
                │ okur (tek yön)
┌───────────────▼──────────────────────────────────────────┐
│  ÇÖZÜMLEYİCİ  (Resolver)                                  │
│  "alan nereden gelir + dönüşüm + varsayılan"              │
│  öncelik: Genel → Kanal → Ürün                            │
└───────┬───────────────┬───────────────┬──────────────────┘
        │               │               │
┌───────▼─────┐  ┌──────▼──────┐  ┌─────▼───────┐
│ TY ADAPTÖR  │  │ HB ADAPTÖR  │  │ N11 ADAPTÖR │  …
│ (referans)  │  │             │  │ (boş şablon)│
└─────────────┘  └─────────────┘  └─────────────┘
  her adaptör kanonikten okur · KENDİ formatında gönderir
```

**Adaptör hiçbir zaman başka bir adaptörden veri okumaz.** Tek girdi kanoniktir.

---

## 2. Trendyol referans analizi (mevcut çalışan akış)

> Aşağıdaki alan adları FACETTE'deki mevcut Trendyol entegrasyon kodundan teyit edilmelidir
> (kod paketi paylaşıldığında bu tablo birebir hizalanacak). Yapı doğru, isimler doğrulanır.

### 2.1 Bağlantı / kimlik
- Auth: Seller ID + API Key/Secret (Basic), env/secret içinde. Ürün dokümanında **asla** tutulmaz.
- Endpoint kökü: `integration/.../sellers/{sellerId}/...`

### 2.2 Eşleştirme modu — ürün hangi kritere göre bağlanır?
Trendyol'da iki anahtar var, ikisi farklı işe yarar:
| Anahtar | İş | FACETTE karşılığı |
|---|---|---|
| `barcode` | Stok/fiyat güncellemede **eşleme anahtarı** | `variant.barcode` |
| `stockCode` | Satıcının kendi stok kodu (gruplama/iz sürme) | `variant.stock_code` |
| `productMainId` | Varyantları gruplayan model kodu | `urun_id` |

**Aktarma filtresi** (hangi ürünler gönderilsin): FACETTE'de *stok koduna göre* veya *barkoda göre* seçilebiliyor — bu ayar korunacak ve her kanala taşınacak (bkz. §5 `match`).

### 2.3 Ürün aktarma — alan haritası (referans)
| Trendyol alanı | Kanonik kaynak | Dönüşüm / not |
|---|---|---|
| `barcode` | `variant.barcode` | benzersiz |
| `title` | `title` | trim, kanal karakter limiti |
| `productMainId` | `urun_id` | varyant gruplama |
| `brandId` | `brand` | marka tablosundan ID'ye eşle |
| `categoryId` | kategori eşleme | Kategori Eşleştirme ekranı |
| `quantity` | `variant.quantity` | `max(0, q − rezerv)` |
| `stockCode` | `variant.stock_code` | |
| `listPrice` | `pricing.list_price` | piyasa fiyatı |
| `salePrice` | `pricing.sale_price` | + kanal markup (TY: %0) |
| `vatRate` | `pricing.vat_rate` | varsayılan %10 |
| `currencyType` | sabit | `TRY` |
| `description` | `description.html` | fallback → `plain` |
| `cargoCompanyId` | kanal ayarı | |
| `images[]` | `images[]` | url listesi |
| `attributes[]` | `attributes[]` (nötr) | **özellik eşleme** ile TY attr ID'sine (bkz. §6) |

### 2.4 Stok / fiyat güncelleme
- Endpoint: `price-and-inventory`
- **Eşleme anahtarı:** `barcode`
- Gönderilen: `{ barcode, quantity, salePrice, listPrice }`
- Mod: **delta** — yalnız değişen varyantlar gider (per-order cooldown + günlük limit backoff zaten mevcut).

### 2.5 Sipariş çekme
- Endpoint: `orders`
- Sipariş kaynağı **prefix** ile belirlenir: `TY…` = Trendyol. (Panel etiketine güvenilmez.)

### 2.6 Müşteri sorusu çekme
- Endpoint: `qna / questions`
- Aynı adaptör sözleşmesinin `pull_questions()` metodu.

### 2.7 Özellik (attribute) işleme — kritik
- Bugün: Ticimax'ten çekilen özellikler **yalnızca Trendyol kartında** yaşıyor.
- Hedef: özellikler `products.attributes[]` içinde **nötr** dursun; her kanal kendi eşleme tablosuyla okusun.

---

## 3. Kanonik ürün modeli (nötr)

```jsonc
{
  "urun_id": "2231",
  "title": "Midi Bisiklet Yaka Elbise",
  "brand": "FACETTE",
  "description": { "html": "...", "plain": "..." },
  "pricing": { "list_price": 699.90, "sale_price": 549.90, "vat_rate": 10, "currency": "TRY" },
  "attributes": [                       // PLATFORM-BAĞIMSIZ nötr liste
    { "key": "Kumaş",     "value": "Pamuk" },
    { "key": "Yaka Tipi", "value": "Bisiklet Yaka" },
    { "key": "Boy",       "value": "Midi" },
    { "key": "Kol Tipi",  "value": "Uzun Kol" }
  ],
  "images": ["https://.../1.jpg"],
  "variants": [
    { "barcode": "869...01", "stock_code": "FCT-ELB-2231-S", "quantity": 12, "size": "S" }
  ],
  "marketplace": {                      // sadece bağ/iz; veri kaynağı DEĞİL
    "trendyol":   { "content_id": "...", "category_id": 411, "status": "active" },
    "hepsiburada":{ "listing_id": "...", "category_id": "...", "status": "pending" }
  }
}
```

> `attributes[]` nötr. `marketplace.*` yalnızca eşleştirme/iz tutar; bir kanal başka kanalın `marketplace` bloğunu **okumaz**.

---

## 4. Çözümleyici (Resolver) + Kullanıcı tanımlı varsayılanlar

Her alan için kural: **kaynak + dönüşüm + varsayılan**. Öncelik hiyerarşisi:

```
Genel varsayılan  →  Kanal override  →  Ürün override
(altta tanımlı, üsttekini ezer)
```

### 4.1 Varsayılanlar kullanıcı tarafından yönetilir
Cinsiyet=`Kadın`, Menşei=`Türkiye` yalnızca **örnek**. Bunlar UI'dan düzenlenebilir **ve yeni varsayılan eklenebilir**:

```jsonc
"defaults": {                 // Alan Kaynağı ekranından eklenir/düzenlenir
  "gender":    "Kadın",
  "origin":    "Türkiye",
  "warranty":  "2 yıl",       // örnek: kullanıcı ekledi
  "wash_care":  "30°C"        // örnek: kullanıcı ekledi
}
```
Kural: bir alan kanonik üründe boşsa **defaults** devreye girer; doluysa kanonik kazanır. Önizlemede "varsayılandan dolduruldu" diye işaretlenir (amber).

### 4.2 Stok & Fiyat eşleme (ayrı, net alan)
```jsonc
"stock_price": {
  "stock_source":  "variant.quantity",
  "reserve":       2,                 // güvenlik stoğu, kanal başına
  "price_source":  "pricing.sale_price",
  "list_price_source": "pricing.list_price",
  "markup_pct":    0,                 // kanal komisyon farkı
  "update_key":    "barcode",         // veya "stock_code"
  "update_mode":   "delta"
}
```

---

## 5. Pazaryeri başına yapılandırma şablonu

> Bu şablon her kanal için bağımsız doldurulur. Trendyol dolu örnek; diğerleri kendi API'sine göre.
> **Hiçbir kanal başka kanalın config'inden veya payload'undan değer almaz.**

### 5.1 Trendyol (referans — dolu)
```yaml
channel: trendyol
match:
  link_key: barcode            # güncelleme eşleme anahtarı
  push_filter: stock_code      # hangi ürünler aktarılsın (stok kodu / barkod)
fields:
  title:       { source: title, transform: "trim|max:100" }
  brand:       { source: brand, map: brand_table }
  category:    { source: category_map }
  quantity:    { source: variant.quantity, transform: "max(0,q-reserve)" }
  stock_code:  { source: variant.stock_code }
  list_price:  { source: pricing.list_price }
  sale_price:  { source: pricing.sale_price, markup_pct: 0 }
  vat_rate:    { source: pricing.vat_rate, default: 10 }
  currency:    { const: TRY }
  description: { source: description.html, fallback: description.plain }
  images:      { source: images }
defaults: { gender: "Kadın", origin: "Türkiye" }
attributes:
  map: attribute_map(trendyol)         # nötr key → TY attributeId/valueId
update:  { key: barcode, fields: [quantity, salePrice, listPrice], mode: delta }
```

### 5.2 Hepsiburada (kendi formatı — Trendyol'dan KOPYALANMAZ)
```yaml
channel: hepsiburada
match:
  link_key: merchant_sku       # HB'nin eşleme anahtarı (≈ stok_code)
  push_filter: stock_code
fields:
  title:        { source: title, transform: "trim|max:HB_LIMIT" }
  brand:        { source: brand, map: brand_table_hb }
  category:     { source: category_map_hb }
  stock:        { source: variant.quantity, transform: "max(0,q-reserve)" }
  merchant_sku: { source: variant.stock_code }
  price:        { source: pricing.sale_price, markup_pct: 8 }   # HB komisyon farkı örnek
  description:  { source: description.html, fallback: description.plain }
  images:       { source: images }
defaults: { gender: "Kadın", origin: "Türkiye" }    # aynı nötr kaynaktan, HB'ye göre
attributes:
  map: attribute_map(hepsiburada)      # nötr key → HB özellik adı/değeri
update:  { key: merchant_sku, fields: [price, stock], mode: delta }
```
> Not: HB alan adları (`merchant_sku`, `price`, `availableStock`, kategori-bazlı zorunlu özellikler) HB Entegratör API'sine göre netleşir. Önemli olan: **değerler kanonikten, format HB'ye göre.**

### 5.3 Yeni kanal (boş şablon)
```yaml
channel: <n11 | amazon | pttavm>
match:        { link_key: <?>, push_filter: <stock_code|barcode> }
fields:       { ... kanonik kaynaklar, kanalın istediği alan adlarıyla ... }
defaults:     { ... ortak nötr varsayılanlar ... }
attributes:   { map: attribute_map(<channel>) }
update:       { key: <?>, fields: [...], mode: delta }
```

Yeni kanal eklemek = **bu şablonu doldurmak + adaptör sözleşmesini implemente etmek.** Kod kopyalama yok.

---

## 6. Özellik eşleme (attribute mapping)

Nötr `attributes[]` → kanal özellik kimliği. Kanal başına ayrı tablo:

```
nötr key "Kumaş" ──┬─→ Trendyol:    attributeId 338, valueId 4521
                   └─→ Hepsiburada: "Materyal" = "Pamuklu"
```
- Trendyol kolonu **mevcut çalışan eşlemeden otomatik göç eder** (sıfırdan giriş yok).
- HB kolonu, aynı nötr listeden kendi ID/adlarına bağlanır.
- Eksik eşleme önizlemede kırmızı → o üründe o kanala gönderim **bloke**.

---

## 7. Adaptör sözleşmesi (her kanal aynı arabirimi uygular)

```python
class MarketplaceAdapter(Protocol):
    def push_product(canonical, config) -> Result      # kanonik → kanal payload
    def update_stock(canonical, config) -> Result      # delta
    def update_price(canonical, config) -> Result      # delta
    def pull_orders(since) -> list[Order]
    def pull_questions(since) -> list[Question]
    def map_attributes(canonical, config) -> list       # nötr → kanal attr
```
Tek `MarketplaceService` orkestratör adaptörleri çağırır. **Kanonik bir kez okunur, N adaptöre dağıtılır.**

---

## 8. Mevcut Trendyol'da yapılacak MİNİK değişiklikler (düşük risk)

1. **Gölge-yazım:** Trendyol kartındaki özellikleri `products.attributes[]` nötr listeye **kopyala** (kart değişmez).
2. **Varsayılanları resolver'dan oku:** cinsiyet/menşei gibi sabitler kod içinden çıkıp `defaults` config'ine taşınır (değer aynı).
3. **Eşleştirme modunu UI'da göster:** stok kodu / barkod seçimi zaten arkada var, panelde görünür kılınır.
> Üçü de eklemeli; Trendyol'un gönderdiği değer **birebir aynı** kalır.

---

## 9. Fazlar (geri alınabilir)

| Faz | İş | Trendyol riski |
|---|---|---|
| 1 | Nötr `attributes[]` + gölge-yazım göçü | sıfır (yalnız kopyala) |
| 2 | Resolver + `defaults` + stok/fiyat eşleme config | sıfır (değer değişmez) |
| 3 | HB adaptörünü kanonikten okut + özellik/kategori eşle | sıfır (ayrı kanal) |
| 4 | Yeni kanal şablonu (N11 vb.) | sıfır (ayrı kanal) |

---

## 10. Guardrails / DoD

- ❌ Bir kanal başka kanalın `marketplace.*` bloğunu veya payload'unu okuyamaz.
- ❌ Trendyol'a giden değer bu çalışma boyunca değişmez (regression testi).
- ✅ Yeni kanal yalnızca §5 şablonu + §7 sözleşmesiyle eklenir.
- ✅ Her alanın kaynağı config'te tanımlı (kod içine gömülü değer yok).
- ✅ DoD: `ast.parse` geçer · esbuild geçer · Trendyol payload diff = 0.

---

## 11. Açık noktalar (kod paylaşımında netleşir)

- Trendyol entegrasyon dosyalarının (`trendyol_*.py`) gerçek alan adları → §2.3 tablosu birebir hizalanacak.
- HB Entegratör zorunlu kategori-özellik şeması → §5.2 doldurulacak.
- `attribute_map` saklama yeri (ayrı koleksiyon mu, kategori eşleme içinde mi) → kararlaştırılacak.
