from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Listing:
    name: str
    tab_name: str
    short_suffix: str
    pms: str
    listing_id: str

    @property
    def promo_tab_name(self) -> str:
        return f"Promo - {self.short_suffix}"

    @property
    def overrides_tab_name(self) -> str:
        return f"Overrides - {self.short_suffix}"


def load_listings(path: Path | None = None) -> list[Listing]:
    path = path or REPO_ROOT / "config" / "listings.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return [
        Listing(
            name=item["name"],
            tab_name=item.get("tab_name", item["name"]),
            short_suffix=item.get("short_suffix", item["name"].split()[0]),
            pms=item["pms"],
            listing_id=item["listing_id"],
        )
        for item in raw["listings"]
    ]


def load_holidays(path: Path | None = None) -> dict[str, str]:
    path = path or REPO_ROOT / "config" / "holidays.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return {str(k): v for k, v in raw.items()}


def get_api_key() -> str:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("PRICELABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "PRICELABS_API_KEY is not set. Copy .env.example to .env and fill "
            "in your PriceLabs API key (Account Settings > API in the "
            "PriceLabs dashboard)."
        )
    return key
