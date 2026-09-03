# KAEL Deal Radar Feed

Independent experimental feed for KAEL Radar. The first pilot monitors Home Depot product pages around ZIP `33189` through Scrape.do, stores observations by location and SKU, and classifies signals without presenting unverified penny prices as confirmed finds.

## Required secret

Add `SCRAPEDO_TOKEN` in **Settings → Secrets and variables → Actions**.

## Pilot inputs

Edit `home-depot-targets.json` to add Home Depot product URLs. GitHub Actions runs the collector and signal engine daily and publishes `penny-radar.json`.

`CONFIRMED` always requires a receipt, register check, or in-store scan.
