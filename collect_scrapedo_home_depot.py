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


def _fetch(token: str, target_url: str, render: bool = False) -> str:
    params = urllib.parse.urlencode({
        "token": token,
        "url": target_url,
        "render": "true" if render else "false",
        "super": "false",
        "geoCode": "US",
    })
    request = urllib.request.Request(
        f"https://api.scrape.do/?{params}",
        headers={"User-Agent": "KAEL-Deal-Radar/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def _with_store(url: str, store_id: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["storeSelection"] = store_id.lstrip("0") or "0"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _discover_product_urls(html: str, limit: int):
    found = []
    for match in re.finditer(r'(?:https://www\.homedepot\.com)?(/p/[^"\'<>\\ ]+/\d{6,12})', unescape(html), re.I):
        url = "https://www.homedepot.com" + match.group(1).split("?")[0]
        if url not in found:
            found.append(url)
        if len(found) >= limit:
            break
    return found


def run(targets_path=TARGETS, output_path=OUTPUT):
    token = os.environ.get("SCRAPEDO_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SCRAPEDO_TOKEN is required")
    config = json.loads(Path(targets_path).read_text(encoding="utf-8"))
    zip_code = str(config.get("zipCode") or "33189").strip()
    configured_urls = [str(x).strip() for x in config.get("productUrls", []) if str(x).strip()]
    stores = [str(x).strip() for x in config.get("storeIds", []) if str(x).strip()] or [f"zip:{zip_code}"]
    discovery_urls = [str(x).strip() for x in config.get("discoveryUrls", []) if str(x).strip()]
    limit = max(1, min(int(config.get("maxDiscoveredProductsPerStore", 12)), 50))
    items, errors = [], []
    attempted = 0
    for store in stores:
        location_id = store if store.startswith("zip:") else store.lstrip("0")
        urls = list(configured_urls)
        for discovery_url in discovery_urls:
            scoped_discovery = _with_store(discovery_url, location_id)
            try:
                urls.extend(_discover_product_urls(_fetch(token, scoped_discovery, render=True), limit))
            except Exception as exc:
                errors.append({"storeId": location_id, "url": scoped_discovery, "stage": "discovery", "error": str(exc)})
        urls = list(dict.fromkeys(urls))[:limit + len(configured_urls)]
        for url in urls:
            attempted += 1
            try:
                items.append(_product_from_html(_fetch(token, _with_store(url, location_id)), url, location_id))
            except Exception as exc:
                errors.append({"storeId": location_id, "url": url, "stage": "product", "error": str(exc)})
    payload = {
        "captureComplete": attempted > 0 and not errors,
        "capturedStoreIds": [x if x.startswith("zip:") else x.lstrip("0") for x in stores] if attempted else [],
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
