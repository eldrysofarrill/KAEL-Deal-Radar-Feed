"""Collect configured Home Depot product pages through Scrape.do."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

TARGETS = Path("home-depot-targets.json")
OUTPUT = Path("home-depot-observations.json")


def _json_ld(html: str):
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    for block in blocks:
        try:
            value = json.loads(unescape(block).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "Product":
                yield item


def _product_from_html(html: str, url: str, location_id: str):
    product = next(_json_ld(html), None)
    if not product:
        raise ValueError("Home Depot product JSON-LD was not found")
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price")
    sku = product.get("sku") or re.search(r"Store SKU #\s*</?[^>]*>?(\d+)", html, re.I)
    if hasattr(sku, "group"):
        sku = sku.group(1)
    availability = str(offers.get("availability") or "")
    return {
        "storeId": location_id,
        "zipCode": location_id.removeprefix("zip:"),
        "sku": str(sku or "").strip(),
        "internetNumber": url.rstrip("/").split("/")[-1].split("?")[0],
        "name": product.get("name"),
        "brand": (product.get("brand") or {}).get("name") if isinstance(product.get("brand"), dict) else product.get("brand"),
        "price": price,
        "regularPrice": price,
        "stock": 0 if "OutOfStock" in availability else None,
        "availability": availability.rsplit("/", 1)[-1] or None,
        "productUrl": url,
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "source": "scrape.do",
    }


def _fetch(token: str, target_url: str) -> str:
    params = urllib.parse.urlencode({
        "token": token,
        "url": target_url,
        "render": "false",
        "super": "false",
        "geoCode": "US",
    })
    request = urllib.request.Request(
        f"https://api.scrape.do/?{params}",
        headers={"User-Agent": "KAEL-Deal-Radar/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def run(targets_path=TARGETS, output_path=OUTPUT):
    token = os.environ.get("SCRAPEDO_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SCRAPEDO_TOKEN is required")
    config = json.loads(Path(targets_path).read_text(encoding="utf-8"))
    zip_code = str(config.get("zipCode") or "33189").strip()
    location_id = f"zip:{zip_code}"
    urls = [str(x).strip() for x in config.get("productUrls", []) if str(x).strip()]
    items, errors = [], []
    for url in urls:
        try:
            items.append(_product_from_html(_fetch(token, url), url, location_id))
        except Exception as exc:  # Preserve partial results and make failures visible.
            errors.append({"url": url, "error": str(exc)})
    payload = {
        "captureComplete": bool(urls) and not errors,
        "capturedStoreIds": [location_id] if urls else [],
        "zipCode": zip_code,
        "source": "scrape.do",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "errors": errors,
    }
    Path(output_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    run()
