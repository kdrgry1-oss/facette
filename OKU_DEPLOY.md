# Site İade → Gider Pusulası: Kargo Yeniden Yapılandırması (kümülatif)

## Ne değişti (bu tur — kargo + tutar düzeltmesi)
Site iade GP'si artık **kargoyu ve sipariş indirimini** doğru işliyor. Kargo, açılır
detayda **ayrı, açık etiketli, tiklenebilir** bir satır olarak geliyor.

| Durum | Kargo faturada (shipping_cost>0) | Ücretsiz kargo (shipping_cost=0) |
|---|---|---|
| **Tam iade** | net = tüm fatura tutarı (order.total — kargo dahil) | net = order.total (kargo yok, mahsup yok) |
| **Kısmi iade** | seçili ürün; kargo tiklenirse **+kargo** (iade) | seçili ürün; kargo tiklenirse **-standart ücret** (mahsup) |

- Tam iade = hiç kalem seçilmez **veya** tüm kalemler seçilir -> backend order.total'i esas alir
  (eski hata: yalniz urun toplami -> kargo + kupon indirimi eksikti).
- Kismi iadede siparis-seviyesi (kupon) indirimi secili kalemlere **oransal** dagitilir.
- Ucretsiz kargo standart ucreti /api/settings ile **ayni kaynaktan** okunur.
- Mahsup satiri pusulada **pozitif (kesinti)**, iade satirlari **negatif** basilir.

## Dosyalar
- backend/routes/orders.py — GP endpoint: kalem secimi + tam/kismi + kargo isaret mantigi, totals.net dogru, cargo meta.
- backend/routes/rooftr_returns.py — yanita free_ship_fee + (onceki tur) GP-no projeksiyonu.
- backend/routes/integrations.py — (onceki tur) Trendyol manuel iade koprusu.
- frontend/src/pages/admin/RooftrReturns.jsx — tiklenebilir kargo satiri + include_cargo.
- frontend/src/pages/admin/Returns.jsx — pusula satir tutari isaret-korur (neg() kaldirildi).
- backend/scripts/recompute_site_gp.py — gecmis GP yeniden-hesaplama (DRY-RUN varsayilan).

## Deploy
    cd ~/Downloads/facette_deploy
    unzip -o ~/Downloads/facette_iade_kopru.zip
    git add -A
    git commit -m "Site iade GP: kargo (faturali=+ / ucretsiz=mahsup), tam iade=order.total, kismi=oransal indirim"
    git push
- Railway yesil: [scheduler] Background scheduler started
- Cloudflare Pages: 1-2 dk build + Cmd+Shift+R

## Test
1. Iade Siparisleri -> Web Sitesi -> bir kayit ac.
2. Hic kalem secme -> GP butonu -> tutar = siparis genel toplami (kargo dahil) olmali.
3. Bazi kalemleri sec (kismi) -> kargo satiri aktiflesir:
   - Faturada kargo varsa +TL "iadeye ekle"; tiklersen GP'ye eklenir.
   - Ucretsiz kargoda -TL "musteriye yansit"; tiklersen GP'den dusulur (mahsup).
4. Basilan pusulada: urunler negatif (iade), mahsup satiri pozitif (kesinti), Net Tutar dogru.

## Gecmis GP'leri duzeltme (DIKKAT — muhasebeye gitmis olabilir)
Railway shell, backend/ dizininde:
    python -m scripts.recompute_site_gp          # ONCE: yalniz rapor (hicbir sey degismez)
    python -m scripts.recompute_site_gp --apply  # SONRA: tam iade GP'lerini order.total'a ceker (yedekli)
- Once dry-run ciktisini incele (eski->yeni tablo + net fark).
- --apply yalniz tam iadeleri duzeltir; eski degerler GP'de _recompute_backup'a yedeklenir.
- Kismi iade GP'leri otomatik degismez -> panelden kalem+kargo secerek yeniden uret.
