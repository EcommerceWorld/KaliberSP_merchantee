#!/usr/bin/env python3
"""
Převodník Mergado feedu (projekt "Export Merchantee") do XML šablony Merchantee / Allegro.

Vstup:  výstupní feed Mergada  <SHOP><SHOPITEM>...</SHOPITEM></SHOP>
        s elementy SKU, EAN, BASE_PRICE, CAMPAIGN_PRICE_LIMIT
        a BASE_PRICE_PLN / _CZK / _HUF, CAMPAIGN_PRICE_LIMIT_PLN / _CZK / _HUF.
Výstup: <MARKETPLACES><MARKETPLACE name="ALLEGRO_xx" currency="..."><item>...</item></MARKETPLACE></MARKETPLACES>

Použití:
    python3 merchantee_feed.py                       # stáhne feed z Mergada, zapíše merchantee.xml
    python3 merchantee_feed.py -o /cesta/vystup.xml
    python3 merchantee_feed.py --source feed.xml     # z lokálního souboru
    python3 merchantee_feed.py --skip-without-ean    # vynechá produkty bez EANu

Jen standardní knihovna Pythonu 3.8+, žádné další balíčky.
"""

import argparse
import os
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

FEED_URL = "https://feeds.mergado.com/kalibersp-sk-export-merchantee-dbd954175c0386e02f26081acc847b58.xml"

# Pořadí trhů ve výstupu a odkud se berou ceny. Sufix "" = základní elementy v EUR.
MARKETPLACES = [
    ("ALLEGRO_PL", "PLN", "_PLN"),
    ("ALLEGRO_CZ", "CZK", "_CZK"),
    ("ALLEGRO_SK", "EUR", ""),
    ("ALLEGRO_HU", "HUF", "_HUF"),
]


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


def item_xml(item, suffix):
    base = item.get("BASE_PRICE" + suffix, "")
    limit = item.get("CAMPAIGN_PRICE_LIMIT" + suffix, "")
    if not base:
        return None
    lines = ["        <item>", "            <SKU>%s</SKU>" % escape(item.get("SKU", ""))]
    if item.get("EAN"):
        lines.append("            <EAN>%s</EAN>" % escape(item["EAN"]))
    lines.append("            <BASE_PRICE>%s</BASE_PRICE>" % escape(base))
    if limit:
        lines.append("            <CAMPAIGN_PRICE_LIMIT>%s</CAMPAIGN_PRICE_LIMIT>" % escape(limit))
    lines.append("        </item>")
    return "\n".join(lines)


def convert(source, output, skip_without_ean=False):
    all_items = list(read_items(source))
    print("Ve zdrojovém feedu: %d položek" % len(all_items))
    if all_items:
        print("Elementy první položky: %s" % ", ".join("%s=%r" % kv for kv in list(all_items[0].items())[:15]))
    items = [
        i for i in all_items
        if i.get("SKU") and (i.get("EAN") or not skip_without_ean)
    ]
    counts = {}
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(output)) or ".", suffix=".tmp")
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<MARKETPLACES>\n')
        for name, currency, suffix in MARKETPLACES:
            out.write("    <MARKETPLACE name=%s currency=%s>\n" % (quoteattr(name), quoteattr(currency)))
            n = 0
            for item in items:
                xml = item_xml(item, suffix)
                if xml:
                    out.write(xml + "\n")
                    n += 1
            out.write("    </MARKETPLACE>\n")
            counts[name] = n
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
