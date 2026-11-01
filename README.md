# KaliberSP_merchantee

XML feed pro Merchantee (dynamické ceny na Allegro) pro e-shop kalibersp.sk.

**Feed:** https://ecommerceworld.github.io/KaliberSP_merchantee/merchantee.xml

## Jak to funguje

1. **Shoptet** exportuje produkty (CSV šablona `patternId=72`) včetně EANu.
2. **Mergado**, projekt *Export Merchantee* (ID 363277), z nich počítá:
   - `SKU` = kód produktu
   - `BASE_PRICE` = cena s DPH v EUR, `CAMPAIGN_PRICE_LIMIT` = cena × 0,95
3. **GitHub Actions** každou hodinu v :45 UTC spustí `merchantee_feed.py`. Skript stáhne feed z Mergada, přepočítá ceny z EUR do PLN, CZK a HUF, poskládá strukturu `<MARKETPLACES>` (ALLEGRO_PL, ALLEGRO_CZ, ALLEGRO_SK, ALLEGRO_HU) a zveřejní ji přes GitHub Pages.

## Kurzy

Kurzy jsou v `merchantee_feed.py` v proměnné `RATES` (kurz ČNB k 30. 10. 2026). Při změně kurzu stačí upravit tam a commitnout, feed se hned přegeneruje.

| Měna | Kurz z EUR | Zaokrouhlení |
|---|---|---|
| PLN | 4,4051 | 2 desetinná místa |
| CZK | 24,36 | celá čísla |
| EUR | — | 2 desetinná místa |
| HUF | 366,3709 | celá čísla |


## Ruční spuštění

Na GitHubu: **Actions → Build Merchantee feed → Run workflow**.

Lokálně (Python 3.8+, bez dalších balíčků):

```
python3 merchantee_feed.py -o merchantee.xml
python3 merchantee_feed.py --skip-without-ean   # jen produkty s EANem
```

Když Mergado vrátí prázdný feed, skript skončí chybou a na Pages zůstane poslední funkční verze.
