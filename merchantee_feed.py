#!/usr/bin/env python3
"""
Převodník Mergado feedu (projekt "Export Merchantee") do XML šablony Merchantee / Allegro.

Vstup:  výstupní feed Mergada (<CHANNEL><ITEM>) s elementy SKU, EAN,
        BASE_PRICE a CAMPAIGN_PRICE_LIMIT v EUR.
Výstup: <MARKETPLACES><MARKETPLACE name="ALLEGRO_xx" currency="..."><item>...</item></MARKETPLACE></MARKETPLACES>

Ceny pro PLN, CZK a HUF přepočítává tento skript z ceny v EUR podle kurzů
v RATES níže (BASE_PRICE × kurz, CAMPAIGN_PRICE_LIMIT = BASE_PRICE × kurz × 0,95).
Při změně kurzu stačí upravit RATES.

Použití:
    python3 merchantee_feed.py                       # stáhne feed z Mergada, zapíše merchantee.xml
    python3 merchantee_feed.py -o /cesta/vystup.xml
    python3 merchantee_feed.py --source feed.xml     # z lokálního souboru
    python3 merchantee_feed.py --skip-without-ean    # vynechá produkty bez EANu

Jen standardní knihovna Pythonu 3.8+, žádné další balíčky.
"""

import argparse
import decimal
import os
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

FEED_URL = "https://feeds.mergado.com/kalibersp-sk-export-merchantee-dbd954175c0386e02f26081acc847b58.xml"

# Kurz ČNB k 30. 10. 2026 (EUR 24,360 CZK; PLN 5,530 CZK; 100 HUF 6,649 CZK),
# přepočteno na 1 EUR. Druhé číslo = počet desetinných míst ve výstupu.
RATES = {
    "EUR": ("1", 2),
    "PLN": ("4.4051", 2),
    "CZK": ("24.36", 0),
    "HUF": ("366.3709", 0),
}
CAMPAIGN_FACTOR = decimal.Decimal("0.95")

# Pořadí trhů ve výstupu (stejné jako ve vzoru Merchantee).
MARKETPLACES = [
    ("ALLEGRO_PL", "PLN"),
    ("ALLEGRO_CZ", "CZK"),
    ("ALLEGRO_SK", "EUR"),
    ("ALLEGRO_HU", "HUF"),
]


def parse_price(value):
    """'1 234,56' i '1234.56' -> Decimal; prázdná nebo neplatná hodnota -> None."""
    value = (value or "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        price = decimal.Decimal(value)
    except decimal.InvalidOperation:
        return None
    return price if price > 0 else None


def fmt(amount, places):
    q = decimal.Decimal(1).scaleb(-places)
    return str(amount.quantize(q, rounding=decimal.ROUND_HALF_UP))


def prices_for(base_eur, currency):
    """Vrátí (BASE_PRICE, CAMPAIGN_PRICE_LIMIT) jako texty pro danou měnu."""
    rate, places = RATES[currency]
    converted = base_eur * decimal.Decimal(rate)
    return fmt(converted, places), fmt(converted * CAMPAIGN_FACTOR, places)


def local(tag):
    """Název elementu bez XML namespace."""
    return tag.rsplit("}", 1)[-1]


def read_items(source):
    """Projde feed po položkách (nenačítá celý soubor do paměti).

    Položkou je každý přímý potomek kořene feedu, který má vlastní elementy
    (Mergado XML: <CHANNEL><ITEM>, Heureka styl: <SHOP><SHOPITEM>).
    """
    depth = 0
    root = None
    for event, elem in ET.iterparse(source, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1:
                root = elem
            continue
        depth -= 1
        if depth != 1:
            continue
        if len(elem):
            values = {}
            for child in elem:
                name = local(child.tag)
                if name not in values:  # bere první výskyt elementu
                    values[name] = (child.text or "").strip()
            yield values
        elem.clear()
        if root is not None:
            root.clear()  # uvolní zpracované položky z paměti


def item_xml(item, currency):
    base, limit = prices_for(item["_base_eur"], currency)
    lines = ["        <item>", "            <SKU>%s</SKU>" % escape(item["SKU"])]
    if item.get("EAN"):
        lines.append("            <EAN>%s</EAN>" % escape(item["EAN"]))
    lines.append("            <BASE_PRICE>%s</BASE_PRICE>" % base)
    lines.append("            <CAMPAIGN_PRICE_LIMIT>%s</CAMPAIGN_PRICE_LIMIT>" % limit)
    lines.append("        </item>")
    return "\n".join(lines)


def convert(source, output, skip_without_ean=False):
    all_items = list(read_items(source))
    print("Ve zdrojovém feedu: %d položek" % len(all_items))
    if all_items:
        print("Elementy první položky: %s" % ", ".join("%s=%r" % kv for kv in list(all_items[0].items())[:15]))
    items = []
    skipped_price = 0
    for i in all_items:
        if not i.get("SKU") or (skip_without_ean and not i.get("EAN")):
            continue
        base_eur = parse_price(i.get("BASE_PRICE"))
        if base_eur is None:
            skipped_price += 1
            continue
        i["_base_eur"] = base_eur
        items.append(i)
    if skipped_price:
        print("Vynecháno bez platné ceny: %d" % skipped_price)
    counts = {}
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(output)) or ".", suffix=".tmp")
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<MARKETPLACES>\n')
        for name, currency in MARKETPLACES:
            out.write("    <MARKETPLACE name=%s currency=%s>\n" % (quoteattr(name), quoteattr(currency)))
            for item in items:
                out.write(item_xml(item, currency) + "\n")
            out.write("    </MARKETPLACE>\n")
            counts[name] = len(items)
        out.write("</MARKETPLACES>\n")
    os.replace(tmp_path, output)  # výstup se přepíše až po úspěšném dokončení
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=FEED_URL, help="URL nebo cesta k Mergado feedu")
    p.add_argument("-o", "--output", default="merchantee.xml", help="výstupní soubor")
    p.add_argument("--skip-without-ean", action="store_true", help="vynechat produkty bez EANu")
    args = p.parse_args()

    if args.source.startswith(("http://", "https://")):
        req = urllib.request.Request(args.source, headers={"User-Agent": "merchantee-feed/1.0"})
        source = urllib.request.urlopen(req, timeout=300)
        print("Stahuji %s (HTTP %s, Last-Modified: %s)" % (
            args.source, source.status, source.headers.get("Last-Modified", "?")))
    else:
        source = args.source

    counts = convert(source, args.output, args.skip_without_ean)
    for name, n in counts.items():
        print("%s: %d položek" % (name, n))
    if not any(counts.values()):
        print("Varování: výstup je prázdný. Zkontroluj, že Mergado už přepočítalo pravidla.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
