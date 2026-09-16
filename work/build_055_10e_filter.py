#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_DIR = Path("/Users/christina/self/poe")
SOURCE = PROJECT_DIR / "[06]打宝82物等-T17+ 天枢过滤器-POE2-曼波语音.filter"
OUTPUT_NAME = "[08]0.5.5赛季10E-T15+ 天枢过滤器-POE2-曼波语音.filter"
OUTPUT = PROJECT_DIR / OUTPUT_NAME
DELIVERY_DIR = Path("/Users/christina/Documents/Codex/2026-08-17/dan/outputs")
DELIVERY_OUTPUT = DELIVERY_DIR / OUTPUT_NAME
SCRIPT_NAME = "build_055_10e_filter.py"
TEST_NAME = "test_build_055_10e_filter.py"
PROJECT_SCRIPT = PROJECT_DIR / "work" / SCRIPT_NAME
PROJECT_TEST = PROJECT_DIR / "work" / TEST_NAME
DELIVERY_SCRIPT = Path("/Users/christina/Documents/Codex/2026-08-17/dan/work") / SCRIPT_NAME
DELIVERY_TEST = Path("/Users/christina/Documents/Codex/2026-08-17/dan/work") / TEST_NAME
SNAPSHOT_NAME = "forbidden_rites_0.5.5_10e_market_snapshot.json"
PROJECT_SNAPSHOT = PROJECT_DIR / "work" / SNAPSHOT_NAME
DELIVERY_SNAPSHOT = Path("/Users/christina/Documents/Codex/2026-08-17/dan/work") / SNAPSHOT_NAME

LEAGUE = "Forbidden Rites"
PATCH_VERSION = "0.5.5"
MIN_VALUE_E = 10.0
HIDE_BELOW_E = 8.0
SHOW_AT_OR_ABOVE_E = 12.0
UNIQUE_MIN_VALUE_E = 50.0
UNIQUE_HIDE_BELOW_E = 40.0
UNIQUE_SHOW_AT_OR_ABOVE_E = 60.0
MIN_EXCHANGE_VOLUME_E = 100.0
MIN_UNIQUE_LISTINGS = 3
TEN_DIVINE_MULTIPLIER = 10.0
DIVINE_ORB_NAME = "Divine Orb"
POE_NINJA_ROOT = "https://poe.ninja/poe2/api/economy"
POE2DB_ROOT = "https://poe2db.tw/us"
CHANGE_REPORT_NAME = "forbidden_rites_0.5.5_10e_change_report.txt"
CLASSIFICATION_SCHEMA_VERSION = 4
SUPPORTED_CLASSIFICATION_SCHEMA_VERSIONS = {2, 3, 4}
PROJECT_CHANGE_REPORT = PROJECT_DIR / "work" / CHANGE_REPORT_NAME
DELIVERY_CHANGE_REPORT = Path("/Users/christina/Documents/Codex/2026-08-17/dan/work") / CHANGE_REPORT_NAME

STACK_SIZE_PAGES = (
    "Currency",
    "Stackable_Currency",
    "Essence",
    "Rune",
    "Soul_Core",
    "Idol",
    "Omen",
    "Ritual",
    "Abyss",
    "Breach",
)

EXCHANGE_SPECS: tuple[tuple[str, str, str | list[str] | None, bool], ...] = (
    ("Currency", "基础通货", ["Incubators", "Stackable Currency"], True),
    ("Fragments", "地图碎片与钥匙", None, True),
    ("Abyss", "深渊骨骸", "Stackable Currency", True),
    ("UncutGems", "未切割宝石", ["Skill Gems", "Support Gems"], False),
    ("LineageSupportGems", "血脉辅助宝石", ["Skill Gems", "Support Gems"], False),
    ("Essences", "精华", "Stackable Currency", True),
    ("SoulCores", "灵核", "Augment", True),
    ("Idols", "雕像", "Augment", True),
    ("Runes", "符文", "Augment", True),
    # This endpoint also contains Sacred Bloom (Map Fragments), not only Omens.
    ("Ritual", "预兆与Sacred Bloom", None, True),
    ("Expedition", "先祖密藏", "Stackable Currency", True),
    ("Delirium", "液化情感", "Stackable Currency", True),
    ("Breach", "催化剂", "Stackable Currency", True),
    ("Verisium", "维里西姆", "Stackable Currency", True),
)

UNIQUE_STASH_TYPES = (
    "UniqueWeapons",
    "UniqueArmours",
    "UniqueAccessories",
    "UniqueFlasks",
    "UniqueCharms",
    "UniqueJewels",
    "UniqueSanctumRelics",
    "UniqueTablets",
    "PrecursorTablets",
)

# 0.10.4 Event Support added this event drop before the exchange had a price row.
EVENT_SAFE_ITEMS = {"Sacred Bloom"}
FORCE_HIDDEN_EXCHANGE_ITEMS = {"Regal Shard"}
LOW_VOLUME_HIDE_CATEGORIES = {"Currency"}

BAND_ORDER = ("1D以上", "100E-1D", "50E-99E", "10E-49E")
UNIQUE_BAND_ORDER = ("1D以上", "100E-1D", "50E-99E")

VISIBLE_STATES = {"single", "uncertain"}
FIXED_JACKPOT_SHARED_UNIQUE_BASES = {
    "Silk Robe",
    "Runemastered Silk Robe",
    "Shortsword",
    "Wide Belt",
    "Utility Belt",
    "Prismatic Ring",
    "Shrine Sceptre",
    "Two-Stone Ring",
    "Moulded Mitts",
}
PROTECTED_SHARED_UNIQUE_BASES = FIXED_JACKPOT_SHARED_UNIQUE_BASES | {
    "Heavy Belt",
}

NAMED_VAULT_KEY_STRONG_EXCEPTIONS = {
    "The Trialmaster's Reliquary Key",
    "Azmeri Reliquary Key",
    "Tangmazu's Reliquary Key",
    "Zarokh's Reliquary Key: Against the Darkness",
    "The Arbiter's Reliquary Key",
    "Xesht's Reliquary Key",
}

STRONG_EXCHANGE_ALERTS: tuple[dict[str, Any], ...] = (
    {
        "id": "mirror",
        "category": "Currency",
        "label": "卡兰德的魔镜",
        "classes": "Stackable Currency",
        "profile": "mirror",
        "names": ("Mirror of Kalandra",),
    },
    {
        "id": "hinekora_lock",
        "category": "Currency",
        "label": "辛格拉的发辫",
        "classes": "Stackable Currency",
        "profile": "hinekora_lock",
        "names": ("Hinekora's Lock",),
    },
    {
        "id": "vault_god",
        "category": "Fragments",
        "label": "宝库钥匙·神曼波",
        "classes": "Vault Keys",
        "profile": "vault_god",
        "names": ("The Trialmaster's Reliquary Key", "Azmeri Reliquary Key"),
    },
    {
        "id": "vault_tangmazu",
        "category": "Fragments",
        "label": "宝库钥匙·唐玛祖与无光",
        "classes": "Vault Keys",
        "profile": "vault_tangmazu",
        "names": (
            "Tangmazu's Reliquary Key",
            "Zarokh's Reliquary Key: Against the Darkness",
        ),
    },
    {
        "id": "vault_arbiter",
        "category": "Fragments",
        "label": "宝库钥匙·仲裁者",
        "classes": "Vault Keys",
        "profile": "vault_arbiter",
        "names": ("The Arbiter's Reliquary Key",),
    },
    {
        "id": "vault_xesht",
        "category": "Fragments",
        "label": "宝库钥匙·夏乌拉",
        "classes": "Vault Keys",
        "profile": "vault_xesht",
        "names": ("Xesht's Reliquary Key",),
    },
    {
        "id": "bloodline_super",
        "category": "LineageSupportGems",
        "label": "超级血脉辅助",
        "classes": ["Skill Gems", "Support Gems"],
        "profile": "bloodline_super",
        "names": ("Amanamu's Tithe", "Catha's Brilliance"),
    },
    {
        "id": "bloodline_cygg",
        "category": "LineageSupportGems",
        "label": "高价血脉辅助",
        "classes": ["Skill Gems", "Support Gems"],
        "profile": "bloodline_cygg",
        "names": (
            "Garukhan's Resolve",
            "Uul-Netol's Embrace",
            "Atziri's Communion",
            "Dialla's Desire",
            "Rakiata's Flow",
            "Rigwald's Ferocity",
            "Uhtred's Exodus",
            "Tul's Stillness",
            "Her Declaration",
            "Seraph's Heart",
            "Esh's Radiance",
            "Uhtred's Augury",
            "Vorana's Siege",
            "Xoph's Pyre",
            "Olroth's Conviction",
            "Uhtred's Omen",
            "Breachlord's Rift",
        ),
    },
    {
        "id": "super_omen",
        "category": "Ritual",
        "label": "超级预兆",
        "classes": "Omen",
        "profile": "super_omen",
        "names": (
            "Omen of Homogenising Exaltation",
            "Omen of Whittling",
            "Omen of Sinistral Erasure",
            "Omen of Dextral Erasure",
            "Omen of Sinistral Annulment",
            "Omen of Light",
            "Omen of Chance",
        ),
    },
    {
        "id": "kurgal_gaze",
        "category": "Abyss",
        "label": "库尔加之凝视",
        "classes": "Augment",
        "profile": "kurgal_gaze",
        "names": ("Kurgal's Gaze",),
    },
    {
        "id": "preserved_cranium",
        "category": "Abyss",
        "label": "保存完好的颅骨",
        "classes": "Stackable Currency",
        "profile": "preserved_cranium",
        "names": ("Preserved Cranium",),
    },
    {
        "id": "perfect_flux",
        "category": "Expedition",
        "label": "完美溶剂",
        "classes": "Stackable Currency",
        "profile": "perfect_flux",
        "names": ("Perfect Flux",),
    },
    {
        "id": "carved_majesty",
        "category": "Idols",
        "label": "雕刻威仪",
        "classes": "Augment",
        "profile": "red_circle_cygg",
        "names": ("Carved Majesty",),
    },
    {
        "id": "aldur_legacy",
        "category": "Runes",
        "label": "奥尔杜尔的遗产",
        "classes": "Augment",
        "profile": "red_circle_cygg",
        "names": ("Aldur's Legacy",),
    },
    {
        "id": "emergent_vigour",
        "category": "Runes",
        "label": "新兴活力",
        "classes": "Augment",
        "profile": "red_circle_hyl",
        "names": ("Emergent Vigour",),
    },
    {
        "id": "raven_touched_shard",
        "category": "SoulCores",
        "label": "渡鸦之触碎片",
        "classes": "Augment",
        "profile": "red_circle_cygg",
        "names": ("Raven-Touched Shard",),
    },
    {
        "id": "ancient_potent_liquid_contempt",
        "category": "Delirium",
        "label": "远古强效蔑视液化情感",
        "classes": "Stackable Currency",
        "profile": "red_triangle_cygg",
        "names": ("Ancient Potent Liquid Contempt",),
    },
)


def fetch_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = Request(
            url,
            headers={
                "User-Agent": "Codex POE2 Forbidden Rites loot filter updater/1.0",
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (URLError, TimeoutError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def fetch_json(url: str) -> dict[str, Any] | list[dict[str, Any]]:
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Unable to decode JSON from {url}: {error}") from error


def fetch_stack_size_catalog(previous_snapshot: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    pattern = re.compile(
        r'<a class="[^"]+"[^>]*>(?:<img[^>]+/>)?([^<>]+)</a>'
        r'<div><div class="property">Stack Size: '
        r"<span class='colourDefault'>1 / (\d+)</span>"
    )
    catalog: dict[str, int] = {}
    warnings: list[str] = []
    for page in STACK_SIZE_PAGES:
        url = f"{POE2DB_ROOT}/{page}"
        try:
            html = fetch_bytes(url).decode("utf-8", errors="replace")
        except RuntimeError as error:
            warnings.append(f"堆叠数据页面读取失败：{page}（{error}）")
            continue
        for raw_name, raw_size in pattern.findall(html):
            name = unescape(raw_name).strip()
            if name:
                catalog[name] = int(raw_size)

    previous_catalog = previous_snapshot.get("max_stack_size") or {}
    for name, size in previous_catalog.items():
        catalog.setdefault(name, int(size))
    if not catalog:
        raise RuntimeError("No maximum stack-size data available from PoE2DB or snapshot")
    return catalog, warnings


def exalted_factor(core: dict[str, Any], divine_price_e: float) -> float:
    rates = core.get("rates") or {}
    if "exalted" in rates:
        return float(rates["exalted"])
    primary = core.get("primary")
    if primary == "exalted":
        return 1.0
    if primary == "divine":
        return divine_price_e
    raise RuntimeError(f"Unsupported poe.ninja primary currency: {primary!r}")


def fetch_exchange_payload(category: str) -> dict[str, Any]:
    url = (
        f"{POE_NINJA_ROOT}/exchange/current/overview"
        f"?league={quote(LEAGUE)}&type={quote(category)}"
    )
    payload = fetch_json(url)
    if not isinstance(payload, dict) or not payload.get("lines"):
        raise RuntimeError(f"No exchange rows returned for {category}")
    return payload


def parse_exchange(
    payload: dict[str, Any], divine_price_e: float
) -> dict[str, dict[str, float]]:
    factor = exalted_factor(payload["core"], divine_price_e)
    names = {item["id"]: item["name"] for item in payload.get("items", [])}
    market: dict[str, dict[str, float]] = {}
    for line in payload.get("lines", []):
        name = names.get(line.get("id"))
        if not name:
            continue
        price_e = float(line.get("primaryValue") or 0) * factor
        if line.get("id") == "exalted":
            # Avoid a 0.999... cross-rate rounding artifact turning 10 Exalted into 11.
            price_e = 1.0
        market[name] = {
            "price_e": price_e,
            "volume_e": float(line.get("volumePrimaryValue") or 0) * factor,
        }
    if not market:
        raise RuntimeError("Exchange payload contained no named rows")
    return market


def fetch_stash_payload(category: str) -> dict[str, Any]:
    url = (
        f"{POE_NINJA_ROOT}/stash/current/item/overview"
        f"?league={quote(LEAGUE)}&type={quote(category)}"
    )
    payload = fetch_json(url)
    if not isinstance(payload, dict) or "lines" not in payload:
        raise RuntimeError(f"No stash rows returned for {category}")
    return payload


def parse_stash(
    payload: dict[str, Any], divine_price_e: float
) -> list[dict[str, Any]]:
    factor = exalted_factor(payload["core"], divine_price_e)
    result: list[dict[str, Any]] = []
    for line in payload.get("lines", []):
        base_type = line.get("baseType") or line.get("name")
        if not base_type:
            continue
        result.append(
            {
                "name": line.get("name") or base_type,
                "base_type": base_type,
                "variant": line.get("variant"),
                "price_e": float(line.get("primaryValue") or 0) * factor,
                "listing_count": int(line.get("listingCount") or 0),
                "corrupted": bool(line.get("corrupted")),
            }
        )
    return result


def header(block: str) -> str:
    return block.split("\r\n", 1)[0]


def hide_block(block: str, label_suffix: str = "") -> str:
    lines = block.split("\r\n")
    if lines[0].startswith("Show # "):
        lines[0] = "Hide # " + lines[0][7:]
    if label_suffix and label_suffix not in lines[0]:
        lines[0] += f" - {label_suffix}"
    for index, line in enumerate(lines[1:], 1):
        match = re.match(
            r"    (MinimapIcon|PlayEffect|PlayAlertSound|CustomAlertSound)(.*)", line
        )
        if match:
            lines[index] = f"#      {match.group(1)}{match.group(2)}"
    return "\r\n".join(lines)


def dedupe_exact_lines(block: str) -> str:
    lines = block.split("\r\n")
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line and line in seen and not line.lstrip().startswith("#"):
            continue
        result.append(line)
        if line:
            seen.add(line)
    return "\r\n".join(result)


def q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def class_line(item_classes: str | list[str] | None) -> str | None:
    if item_classes is None:
        return None
    if isinstance(item_classes, str):
        item_classes = [item_classes]
    return "    Class " + " ".join(q(item_class) for item_class in item_classes)


def price_band(price_e: float, divine_price_e: float) -> str:
    if price_e >= divine_price_e:
        return "1D以上"
    if price_e >= 100:
        return "100E-1D"
    if price_e >= 50:
        return "50E-99E"
    return "10E-49E"


def state_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        state = value.get("state")
        return str(state) if state else None
    return None


def classification_history(snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("classification_schema_version") not in SUPPORTED_CLASSIFICATION_SCHEMA_VERSIONS:
        return {}
    value = snapshot.get("classification_state")
    return value if isinstance(value, dict) else {}


def was_visible(value: Any) -> bool | None:
    state = state_name(value)
    if state is None:
        return None
    return state.split(":", 1)[0] in VISIBLE_STATES


def stable_value(
    price_e: float,
    previous_visible: bool | None,
    threshold_e: float,
    hide_below_e: float,
    show_at_or_above_e: float,
) -> bool:
    if price_e >= show_at_or_above_e:
        return True
    if price_e < hide_below_e:
        return False
    if previous_visible is not None:
        return previous_visible
    return price_e >= threshold_e


def stable_single(price_e: float, previous_visible: bool | None) -> bool:
    return stable_value(
        price_e,
        previous_visible,
        MIN_VALUE_E,
        HIDE_BELOW_E,
        SHOW_AT_OR_ABOVE_E,
    )


def stable_unique(price_e: float, previous_visible: bool | None) -> bool:
    return stable_value(
        price_e,
        previous_visible,
        UNIQUE_MIN_VALUE_E,
        UNIQUE_HIDE_BELOW_E,
        UNIQUE_SHOW_AT_OR_ABOVE_E,
    )


def exchange_is_trusted(name: str, price_e: float, volume_e: float) -> bool:
    return name in EVENT_SAFE_ITEMS or volume_e >= max(
        MIN_EXCHANGE_VOLUME_E, 5.0 * price_e
    )


def old_exchange_visible(
    previous_snapshot: dict[str, Any], category: str, name: str
) -> bool | None:
    saved = (
        classification_history(previous_snapshot)
        .get("exchange", {})
        .get(category, {})
        .get(name)
    )
    visible = was_visible(saved)
    if visible is not None:
        return visible
    old = previous_snapshot.get("exchange", {}).get(category, {}).get(name)
    if not old:
        return None
    # Seed the first hysteresis run from the exact behaviour of the old 10E filter.
    old_trusted = float(old.get("volume_e") or 0) >= 10.0 or name in EVENT_SAFE_ITEMS
    return float(old.get("price_e") or 0) >= MIN_VALUE_E and old_trusted


def old_unique_visible(
    previous_snapshot: dict[str, Any], section: str, base_type: str, rows: list[dict[str, Any]]
) -> bool | None:
    saved = (
        classification_history(previous_snapshot)
        .get("unique", {})
        .get(section, {})
        .get(base_type)
    )
    visible = was_visible(saved)
    if visible is not None:
        return visible
    if not rows:
        return None
    # Missing state is initialized from the exact 50E unique threshold and the
    # same three-listing trust gate used for current unique classifications.
    best = max(rows, key=lambda row: float(row.get("price_e") or 0))
    return (
        float(best.get("price_e") or 0) >= UNIQUE_MIN_VALUE_E
        and int(best.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
    )


def classification_record(
    state: str,
    price_e: float,
    trusted: bool,
    generated_at: str,
    previous_record: Any = None,
    hysteresis_low_e: float = HIDE_BELOW_E,
    hysteresis_high_e: float = SHOW_AT_OR_ABOVE_E,
    **extra: Any,
) -> dict[str, Any]:
    previous_name = state_name(previous_record)
    last_stable_state = state
    if hysteresis_low_e <= price_e < hysteresis_high_e and previous_name:
        last_stable_state = previous_name
    record: dict[str, Any] = {
        "state": state,
        "price_e": round(price_e, 6),
        "trusted": trusted,
        "last_stable_state": last_stable_state,
        "updated_at_utc": generated_at,
    }
    record.update(extra)
    return record


def market_style(band: str) -> list[str]:
    styles = {
        "10D以上": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 255 0 58",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Triangle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "1D以上": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 255 0 58",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Triangle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\HYL.mp3" 300',
        ],
        "100E-1D": [
            "    SetTextColor 0 47 167",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 0 47 167",
            "    SetFontSize 45",
            "    MinimapIcon 1 Blue Triangle",
            "    PlayEffect Blue",
            '    CustomAlertSound "音效\\HYL.mp3" 300',
        ],
        "50E-99E": [
            "    SetTextColor 138 43 226",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 138 43 226",
            "    SetFontSize 45",
            "    MinimapIcon 1 Purple Triangle",
            "    PlayEffect Purple",
            '    CustomAlertSound "音效\\GXFC.mp3" 300',
        ],
        "10E-49E": [
            "    SetTextColor 0 0 0",
            "    SetBackgroundColor 245 139 87 255",
            "    SetBorderColor 0 0 0",
            "    SetFontSize 40",
            "    MinimapIcon 2 Orange Triangle",
            "    PlayEffect Orange",
            '    CustomAlertSound "音效\\MBWDD.mp3" 300',
        ],
    }
    return styles[band]


def divine_orb_rule() -> str:
    """Keep Divine Orbs on their dedicated HYL sound, outside market tiers."""
    lines = [
        "Show # 0.5.5专属音效 - 神圣石",
        '    Class "Stackable Currency"',
        f"    BaseType == {q(DIVINE_ORB_NAME)}",
        "    SetTextColor 255 0 0",
        "    SetBackgroundColor 255 255 255",
        "    SetBorderColor 255 0 0",
        "    SetFontSize 45",
        "    MinimapIcon 0 Red Star",
        "    PlayEffect Red",
        '    CustomAlertSound "音效\\HYL.mp3" 300',
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def cautious_style() -> list[str]:
    return [
        "    SetTextColor 40 20 0",
        "    SetBackgroundColor 255 214 102 235",
        "    SetBorderColor 138 43 226",
        "    SetFontSize 38",
        "    MinimapIcon 2 Yellow Diamond",
        "    PlayEffect Yellow",
        '    CustomAlertSound "音效\\传奇装备.mp3" 260',
    ]


def strong_profile_style(profile: str) -> list[str]:
    profiles = {
        "mirror": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 205 0 0 230",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\神曼波.mp3" 300',
        ],
        "hinekora_lock": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 205 0 0 230",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\辛格拉的发辫.mp3" 300',
        ],
        "vault_god": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 205 0 0 230",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Diamond",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\神曼波.mp3" 300',
        ],
        "vault_tangmazu": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 155 28 57",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Diamond",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\heiheihei.mp3" 300',
        ],
        "vault_arbiter": [
            "    SetTextColor 255 0 0",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Diamond",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\HJMJH.mp3" 300',
        ],
        "vault_xesht": [
            "    SetTextColor 255 0 0",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Diamond",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\宝库钥匙.mp3" 300',
        ],
        "bloodline_cygg": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 205 0 0 230",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Kite",
            "    PlayEffect Red",
            "    PlayAlertSound 9 300",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "bloodline_super": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 255 40 0 230",
            "    SetBorderColor 255 40 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Kite",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\超级血脉宝石.mp3" 300',
        ],
        "super_omen": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 144 0 33",
            "    SetBorderColor 144 0 33",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Hexagon",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\超级预兆.mp3" 300',
        ],
        "kurgal_gaze": [
            "    SetTextColor 144 0 33",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 144 0 33",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\hjmld.mp3" 300',
        ],
        "preserved_cranium": [
            "    SetTextColor 144 0 33",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 144 0 33",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Triangle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\jyn.mp3" 300',
        ],
        "perfect_flux": [
            "    SetTextColor 144 0 33",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 144 0 33",
            "    SetFontSize 40",
            "    MinimapIcon 1 Red Circle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\溶剂.mp3" 300',
        ],
        "red_circle_cygg": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 255 0 58",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Circle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "red_circle_hyl": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 144 0 33",
            "    SetBorderColor 144 0 33",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Circle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\HYL.mp3" 300',
        ],
        "red_triangle_cygg": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 255 0 58",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Triangle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "legendary_jewel": [
            "    SetTextColor 180 96 0",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 42",
            "    MinimapIcon 2 Brown Cross",
            '    CustomAlertSound "音效\\传奇珠宝.mp3" 300',
        ],
        "runic_fork": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 255 40 0 230",
            "    SetBorderColor 255 40 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\顺风顺水.mp3" 300',
        ],
        "grand_spear": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 255 40 0 230",
            "    SetBorderColor 255 40 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "ornate_gauntlets": [
            "    SetTextColor 245 69 16",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\cpx.mp3" 300',
        ],
        "incense_relic": [
            "    SetTextColor 255 255 255",
            "    SetBackgroundColor 255 40 0 230",
            "    SetBorderColor 255 40 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 1 Brown Triangle",
            "    PlayEffect Brown",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
        ],
        "jackpot_shared": [
            "    SetTextColor 245 16 16",
            "    SetBackgroundColor 255 255 255",
            "    SetBorderColor 255 0 0",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Brown",
            '    CustomAlertSound "音效\\wyyp.mp3" 300',
        ],
    }
    return profiles[profile]


def strong_alert_rule(
    label: str,
    names: list[str],
    profile: str,
    item_classes: str | list[str] | None = None,
    rarity: str | None = None,
) -> str:
    lines = [f"Show # 0.5.5原版高价值强提醒 - {label} - 10D以上"]
    if rarity:
        lines.append(f"    Rarity {rarity}")
    classes = class_line(item_classes)
    if classes:
        lines.append(classes)
    lines.extend(
        [
            "    BaseType == " + " ".join(q(name) for name in sorted(names, key=str.casefold)),
            *strong_profile_style(profile),
            "    DisableDropSound",
            "",
            "",
        ]
    )
    return "\r\n".join(lines)


def build_exchange_strong_alerts(
    markets: dict[str, dict[str, dict[str, float]]],
    divine_price_e: float,
) -> tuple[str, dict[str, dict[str, Any]]]:
    cutoff_e = TEN_DIVINE_MULTIPLIER * divine_price_e
    blocks: list[str] = []
    active: dict[str, dict[str, Any]] = {}
    for spec in STRONG_EXCHANGE_ALERTS:
        category = str(spec["category"])
        enabled: list[str] = []
        for name in spec["names"]:
            values = markets.get(category, {}).get(name)
            if not values:
                continue
            price_e = float(values["price_e"])
            volume_e = float(values["volume_e"])
            trusted = exchange_is_trusted(name, price_e, volume_e)
            key_exception = (
                category == "Fragments"
                and name in NAMED_VAULT_KEY_STRONG_EXCEPTIONS
            )
            if price_e < cutoff_e or not (trusted or key_exception):
                continue
            enabled.append(name)
            reason = (
                "trusted_price_at_least_10d"
                if trusted
                else "named_vault_key_low_volume_exception"
            )
            alert_id = f"exchange/{category}/{name}"
            active[alert_id] = {
                "name": name,
                "category": category,
                "profile": spec["profile"],
                "sound": strong_profile_style(str(spec["profile"]))[-1].split("\\")[-1].split('"')[0],
                "price_e": round(price_e, 6),
                "price_divine": round(price_e / divine_price_e, 6),
                "trusted": trusted,
                "reason": reason,
            }
        if enabled:
            blocks.append(
                strong_alert_rule(
                    str(spec["label"]),
                    enabled,
                    str(spec["profile"]),
                    spec.get("classes"),
                )
            )
    return "".join(blocks), active


def credible_unique_base(
    rows: list[dict[str, Any]], base_type: str
) -> tuple[float, int, set[str], bool]:
    base_rows = [row for row in rows if row["base_type"] == base_type]
    credible = [
        row for row in base_rows
        if int(row.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
    ]
    top = max(
        credible,
        key=lambda row: float(row.get("price_e") or 0),
        default=None,
    )
    price_e = float((top or {}).get("price_e") or 0)
    count = int((top or {}).get("listing_count") or 0)
    names = {str(row.get("name") or base_type) for row in base_rows}
    shared = len(names) > 1 or len(base_rows) > 1
    return price_e, count, names, shared


def unique_priority_rule(label: str, base_types: list[str], profile: str) -> str:
    classes: str | None = None
    if profile == "legendary_jewel":
        classes = "Jewels"
    elif profile == "incense_relic":
        classes = "Relics"
    return strong_alert_rule(label, base_types, profile, classes, "Unique")


def active_unique_priority_alerts(
    section: str,
    rows: list[dict[str, Any]],
    candidates: tuple[tuple[str, str, str], ...],
    divine_price_e: float,
) -> tuple[str, dict[str, dict[str, Any]]]:
    cutoff_e = TEN_DIVINE_MULTIPLIER * divine_price_e
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    active: dict[str, dict[str, Any]] = {}
    for base_type, label, profile in candidates:
        price_e, listing_count, names, _shared = credible_unique_base(rows, base_type)
        if listing_count < MIN_UNIQUE_LISTINGS or price_e < cutoff_e:
            continue
        grouped[(label, profile)].append(base_type)
        active[f"unique/{section}/{base_type}"] = {
            "name": base_type,
            "section": section,
            "profile": profile,
            "sound": strong_profile_style(profile)[-1].split("\\")[-1].split('"')[0],
            "price_e": round(price_e, 6),
            "price_divine": round(price_e / divine_price_e, 6),
            "listing_count": listing_count,
            "unique_names": sorted(names),
            "trusted": True,
            "reason": "trusted_unique_price_at_least_10d",
        }
    blocks = [
        unique_priority_rule(label, base_types, profile)
        for (label, profile), base_types in grouped.items()
    ]
    return "".join(blocks), active


def build_jackpot_shared_alerts(
    rows: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    divine_price_e: float,
) -> tuple[str, dict[str, dict[str, Any]]]:
    cutoff_e = TEN_DIVINE_MULTIPLIER * divine_price_e
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_rows[row["base_type"]].append(row)

    dedicated = {"Heavy Belt", "Ring", "Ruby", "Diamond", "Sapphire"}
    dedicated.update({"Runic Fork", "Runemastered Runic Fork", "Grand Spear", "Ornate Gauntlets"})
    selected = set(FIXED_JACKPOT_SHARED_UNIQUE_BASES)
    reasons = {base: "fixed_jackpot_shared_base" for base in selected}
    for base_type, record in states.items():
        price_e = float(record.get("credible_max_price_e") or 0)
        listing_count = int(record.get("credible_listing_count") or 0)
        uncertainty = record.get("uncertainty") or []
        if isinstance(uncertainty, str):
            uncertainty = [uncertainty]
        is_shared = (
            "shared_base_type" in uncertainty
            or "variant_price_spread" in uncertainty
            or len(grouped_rows.get(base_type, [])) > 1
        )
        if (
            base_type not in dedicated
            and base_type not in selected
            and is_shared
            and listing_count >= MIN_UNIQUE_LISTINGS
            and price_e >= cutoff_e
        ):
            selected.add(base_type)
            reasons[base_type] = "dynamic_shared_base_trusted_max_at_least_10d"

    active: dict[str, dict[str, Any]] = {}
    for base_type in sorted(selected, key=str.casefold):
        price_e, listing_count, names, _shared = credible_unique_base(rows, base_type)
        active[f"unique/gear/jackpot/{base_type}"] = {
            "name": base_type,
            "section": "gear",
            "profile": "jackpot_shared",
            "sound": "wyyp.mp3",
            "price_e": round(price_e, 6),
            "price_divine": round(price_e / divine_price_e, 6) if price_e else 0.0,
            "listing_count": listing_count,
            "unique_names": sorted(names),
            "trusted": listing_count >= MIN_UNIQUE_LISTINGS,
            "reason": reasons[base_type],
        }
    return (
        unique_priority_rule("大奖共享传奇底材", sorted(selected, key=str.casefold), "jackpot_shared"),
        active,
    )


def market_rule(
    category_cn: str,
    band: str,
    names: list[str],
    item_classes: str | list[str] | None,
) -> str:
    lines = [
        f"Show # 0.5.5市场 - {category_cn} - Forbidden Rites {band}★",
    ]
    classes = class_line(item_classes)
    if classes:
        lines.append(classes)
    lines.extend(
        [
            "    BaseType == " + " ".join(q(name) for name in sorted(names, key=str.casefold)),
            *market_style(band),
            "    DisableDropSound",
            "",
            "",
        ]
    )
    return "\r\n".join(lines)


def cautious_market_rule(
    category_cn: str,
    names: list[str],
    item_classes: str | list[str] | None,
    reason: str = "低成交量，可能高价",
) -> str:
    lines = [f"Show # 0.5.5市场 - {category_cn} - 可能高价（{reason}）"]
    classes = class_line(item_classes)
    if classes:
        lines.append(classes)
    lines.extend(
        [
            "    BaseType == " + " ".join(q(name) for name in sorted(names, key=str.casefold)),
            *cautious_style(),
            "    DisableDropSound",
            "",
            "",
        ]
    )
    return "\r\n".join(lines)


def stack_rule(
    category_cn: str,
    minimum: int,
    names: list[str],
    item_classes: str | list[str] | None,
) -> str:
    lines = [
        f"Show # 0.5.5市场 - {category_cn} - 堆叠总价10E（{minimum}个以上）",
        f"    StackSize >= {minimum}",
    ]
    classes = class_line(item_classes)
    if classes:
        lines.append(classes)
    lines.extend(
        [
            "    BaseType == " + " ".join(q(name) for name in sorted(names, key=str.casefold)),
            *market_style("10E-49E"),
            "    DisableDropSound",
            "",
            "",
        ]
    )
    return "\r\n".join(lines)


def market_hide_rule(
    category_cn: str,
    names: list[str],
    item_classes: str | list[str] | None,
) -> str:
    lines = [f"Hide # 0.5.5市场 - {category_cn} - 单次掉落不足10E或低置信度"]
    classes = class_line(item_classes)
    if classes:
        lines.append(classes)
    lines.extend(
        [
            "    BaseType == " + " ".join(q(name) for name in sorted(names, key=str.casefold)),
            "    SetFontSize 30",
            "    DisableDropSound",
            "",
            "",
        ]
    )
    return "\r\n".join(lines)


def build_exchange_section(
    markets: dict[str, dict[str, dict[str, float]]],
    divine_price_e: float,
    previous_snapshot: dict[str, Any],
    max_stack_size: dict[str, int],
    generated_at: str,
) -> tuple[
    str,
    dict[str, dict[str, int]],
    dict[str, dict[str, dict[str, Any]]],
    list[str],
]:
    blocks: list[str] = [divine_orb_rule()]
    stats: dict[str, dict[str, int]] = {}
    states: dict[str, dict[str, dict[str, Any]]] = {}
    warnings: list[str] = []
    for category, category_cn, item_classes, stackable in EXCHANGE_SPECS:
        bands: dict[str, list[str]] = {band: [] for band in BAND_ORDER}
        ten_divine: list[str] = []
        stack_groups: dict[int, list[str]] = defaultdict(list)
        uncertain: list[str] = []
        hidden: list[str] = []
        final_hidden = 0
        category_states: dict[str, dict[str, Any]] = {}
        for name, values in markets[category].items():
            price_e = values["price_e"]
            volume_e = values["volume_e"]
            previous_record = (
                classification_history(previous_snapshot)
                .get("exchange", {})
                .get(category, {})
                .get(name)
            )
            previous_visible = old_exchange_visible(previous_snapshot, category, name)
            wants_single = stable_single(price_e, previous_visible)
            trusted = exchange_is_trusted(name, price_e, volume_e)
            state = "hidden"
            extra: dict[str, Any] = {
                "volume_e": round(volume_e, 6),
                "confidence_threshold_e": round(max(MIN_EXCHANGE_VOLUME_E, 5.0 * price_e), 6),
            }
            if name in FORCE_HIDDEN_EXCHANGE_ITEMS:
                extra["uncertainty"] = "forced_hidden"
            elif wants_single:
                if trusted:
                    bands[price_band(price_e, divine_price_e)].append(name)
                    if (
                        name != DIVINE_ORB_NAME
                        and price_e >= TEN_DIVINE_MULTIPLIER * divine_price_e
                    ):
                        ten_divine.append(name)
                    state = "single"
                elif category in LOW_VOLUME_HIDE_CATEGORIES:
                    # Sparse basic-currency quotes are too easy to manipulate.
                    # Keep them hidden while retaining cautious alerts for scarce
                    # keys, essences, runes and other potentially valuable drops.
                    extra["uncertainty"] = "low_exchange_volume"
                else:
                    uncertain.append(name)
                    state = "uncertain"
                    extra["uncertainty"] = "low_exchange_volume"
            elif stackable and trusted and price_e > 0:
                minimum = math.ceil(MIN_VALUE_E / price_e)
                maximum = max_stack_size.get(name)
                extra.update({"required_stack": minimum, "max_stack_size": maximum})
                if minimum >= 2 and maximum is not None and minimum <= maximum:
                    stack_groups[minimum].append(name)
                    state = f"stack:{minimum}"
                elif minimum >= 2 and maximum is None:
                    warnings.append(
                        f"[{category}] {name}: 缺少最大堆叠数，未生成 StackSize {minimum}"
                    )
                    extra["uncertainty"] = "missing_max_stack_size"
                elif minimum > (maximum or 0):
                    warnings.append(
                        f"[{category}] {name}: 需要堆叠 {minimum}，超过最大堆叠 {maximum}"
                    )
                    extra["uncertainty"] = "required_stack_exceeds_maximum"
                else:
                    # A 10-12E item seeded as hidden stays hidden until it reaches 12E.
                    extra["uncertainty"] = "hysteresis_hold_hidden"
            elif not trusted:
                extra["uncertainty"] = "low_exchange_volume"

            if state not in {"single", "uncertain"}:
                hidden.append(name)
            if state == "hidden":
                final_hidden += 1
            category_states[name] = classification_record(
                state,
                price_e,
                trusted,
                generated_at,
                previous_record,
                **extra,
            )

        if category == "Currency":
            for name in sorted(FORCE_HIDDEN_EXCHANGE_ITEMS - set(markets[category])):
                hidden.append(name)
                final_hidden += 1
                category_states[name] = classification_record(
                    "hidden",
                    0.0,
                    False,
                    generated_at,
                    uncertainty="forced_hidden_missing_market_row",
                )
                warnings.append(
                    f"[{category}] {name}: 行情缺行，仍按强制隐藏策略生成前置规则"
                )

        if ten_divine:
            blocks.append(
                market_rule(category_cn, "10D以上", ten_divine, item_classes)
            )
        for band in BAND_ORDER:
            if bands[band]:
                blocks.append(market_rule(category_cn, band, bands[band], item_classes))
        if uncertain:
            blocks.append(cautious_market_rule(category_cn, uncertain, item_classes))
        for minimum, names in sorted(stack_groups.items()):
            blocks.append(stack_rule(category_cn, minimum, names, item_classes))
        if hidden:
            blocks.append(market_hide_rule(category_cn, hidden, item_classes))
        states[category] = category_states
        stats[category] = {
            "rows": len(markets[category]),
            "shown_single": sum(len(names) for names in bands.values()),
            "shown_10d_override": len(ten_divine),
            "shown_stack": sum(len(names) for names in stack_groups.values()),
            "shown_uncertain": len(uncertain),
            "hidden": final_hidden,
            "fallback_hide_rows": len(hidden),
        }

    event_names = sorted(EVENT_SAFE_ITEMS - set().union(*(set(market) for market in markets.values())))
    if event_names:
        blocks.insert(0, cautious_market_rule("0.5.5新增物品（事件兼容）", event_names, None, "暂无可靠行情"))
        states.setdefault("event_fallback", {})
        for name in event_names:
            states["event_fallback"][name] = classification_record(
                "uncertain",
                0.0,
                False,
                generated_at,
                uncertainty="missing_market_row",
            )
            warnings.append(f"[event] {name}: 没有行情行，使用可能高价提醒")
    return "".join(blocks), stats, states, warnings


def unique_rule(category_cn: str, band: str, base_types: list[str]) -> str:
    sounds = {
        "1D以上": "CYGG.mp3",
        "100E-1D": "wyyp.mp3",
        "50E-99E": "cpx.mp3",
        "10E-49E": "传奇装备.mp3",
    }
    style = market_style(band)
    style[-1] = f'    CustomAlertSound "音效\\{sounds[band]}" 300'
    lines = [
        f"Show # 0.5.5传奇市场 - {category_cn} - Forbidden Rites {band}★",
        "    Rarity Unique",
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        *style,
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def unique_cautious_rule(category_cn: str, base_types: list[str]) -> str:
    lines = [
        f"Show # 0.5.5传奇市场 - {category_cn} - 可能高价（大奖同底材或价格分歧）",
        "    Rarity Unique",
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        *cautious_style(),
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def unique_hysteresis_rule(category_cn: str, base_types: list[str]) -> str:
    lines = [
        f"Show # 0.5.5传奇市场 - {category_cn} - 40E-49E迟滞保留",
        "    Rarity Unique",
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        *cautious_style(),
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def unique_hide_rule(category_cn: str, base_types: list[str]) -> str:
    lines = [
        f"Hide # 0.5.5传奇市场 - {category_cn} - 低于50E或低置信度",
        "    Rarity Unique",
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        "    SetFontSize 30",
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def build_unique_section(
    section_key: str,
    category_cn: str,
    rows: list[dict[str, Any]],
    divine_price_e: float,
    previous_snapshot: dict[str, Any],
    previous_rows: list[dict[str, Any]],
    generated_at: str,
    excluded_bases: set[str] | None = None,
) -> tuple[str, dict[str, int], dict[str, dict[str, Any]]]:
    excluded_bases = excluded_bases or set()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        base_type = row["base_type"]
        if base_type in excluded_bases:
            continue
        grouped[base_type].append(row)

    previous_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in previous_rows:
        previous_grouped[row["base_type"]].append(row)

    bands: dict[str, list[str]] = {band: [] for band in UNIQUE_BAND_ORDER}
    hysteresis_visible: list[str] = []
    uncertain: list[str] = []
    hidden: list[str] = []
    states: dict[str, dict[str, Any]] = {}
    for base_type, base_rows in grouped.items():
        prices = [float(row["price_e"]) for row in base_rows]
        highest_price = max(prices)
        lowest_price = min(prices)
        credible_rows = [
            row for row in base_rows
            if int(row.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
        ]
        all_trusted = len(credible_rows) == len(base_rows)
        credible_top = max(
            credible_rows,
            key=lambda row: float(row.get("price_e") or 0),
            default=None,
        )
        credible_max_price = float((credible_top or {}).get("price_e") or 0)
        names = {str(row.get("name") or base_type) for row in base_rows}
        previous_record = (
            classification_history(previous_snapshot)
            .get("unique", {})
            .get(section_key, {})
            .get(base_type)
        )
        previous_visible = old_unique_visible(
            previous_snapshot,
            section_key,
            base_type,
            previous_grouped.get(base_type, []),
        )
        candidate = bool(credible_rows) and stable_unique(
            credible_max_price, previous_visible
        )
        every_variant_visible = all(
            stable_unique(price, previous_visible) for price in prices
        )
        protected = base_type in PROTECTED_SHARED_UNIQUE_BASES
        regular = (
            candidate
            and all_trusted
            and len(names) == 1
            and every_variant_visible
            and not protected
        )
        state = "hidden"
        uncertainty: list[str] = []
        if candidate and regular:
            if lowest_price < UNIQUE_MIN_VALUE_E:
                hysteresis_visible.append(base_type)
                state = "single:hysteresis"
                uncertainty.append("hysteresis_hold_visible")
            else:
                bands[price_band(lowest_price, divine_price_e)].append(base_type)
                state = "single"
        elif protected or candidate:
            uncertain.append(base_type)
            state = "uncertain"
            if protected:
                uncertainty.append("protected_shared_base")
            if not credible_rows:
                uncertainty.append("insufficient_listings")
            elif candidate:
                uncertainty.append("shared_base_jackpot")
            if not all_trusted:
                uncertainty.append("untrusted_variants_present")
            if len(names) > 1:
                uncertainty.append("shared_base_type")
            if not every_variant_visible:
                uncertainty.append("variant_price_spread")
        else:
            hidden.append(base_type)
            if not credible_rows:
                uncertainty.append("insufficient_listings")
            else:
                uncertainty.append("below_unique_threshold")
        states[base_type] = classification_record(
            state,
            credible_max_price if credible_rows else highest_price,
            bool(credible_rows),
            generated_at,
            previous_record,
            hysteresis_low_e=UNIQUE_HIDE_BELOW_E,
            hysteresis_high_e=UNIQUE_SHOW_AT_OR_ABOVE_E,
            min_price_e=round(lowest_price, 6),
            max_price_e=round(highest_price, 6),
            credible_max_price_e=round(credible_max_price, 6),
            credible_listing_count=int((credible_top or {}).get("listing_count") or 0),
            all_rows_trusted=all_trusted,
            listing_count_min=min(int(row["listing_count"]) for row in base_rows),
            unique_names=sorted(names),
            uncertainty=uncertainty or None,
        )

    blocks = [
        unique_rule(category_cn, band, bands[band])
        for band in UNIQUE_BAND_ORDER
        if bands[band]
    ]
    if hysteresis_visible:
        blocks.append(unique_hysteresis_rule(category_cn, hysteresis_visible))
    if uncertain:
        blocks.append(unique_cautious_rule(category_cn, uncertain))
    if hidden:
        blocks.append(unique_hide_rule(category_cn, hidden))
    return "".join(blocks), {
        "rows": len(rows),
        "bases": len(grouped),
        "shown": sum(len(names) for names in bands.values()),
        "hysteresis_visible": len(hysteresis_visible),
        "uncertain": len(uncertain),
        "hidden": len(hidden),
    }, states


def headhunter_rule() -> str:
    lines = [
        "Show # 0.5.5传奇市场 - 可能猎首（重革腰带同底材）",
        "    Rarity Unique",
        '    BaseType == "Heavy Belt"',
        "    SetTextColor 245 16 16",
        "    SetBackgroundColor 255 255 255",
        "    SetBorderColor 255 0 0",
        "    SetFontSize 45",
        "    MinimapIcon 0 Red Star",
        "    PlayEffect Brown",
        '    CustomAlertSound "音效\\wyyp.mp3" 300',
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def voices_rule() -> str:
    """Preserve the original dedicated Voices alert ahead of Sapphire pricing rules."""
    lines = [
        "Show # 珠宝 - 0.5.5保留 - 天神之音（原版强提醒）",
        "    Corrupted True",
        "    Rarity Unique",
        '    Class "Jewels"',
        '    BaseType == "Sapphire"',
        "    SetTextColor 180 96 0",
        "    SetBackgroundColor 255 255 255",
        "    SetBorderColor 255 0 0",
        "    SetFontSize 42",
        "    MinimapIcon 2 Brown Cross",
        '    CustomAlertSound "音效\\天神之音.mp3" 300',
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def tablet_rule(band: str, rarity: str, base_types: list[str]) -> str:
    lines = [
        f"Show # 0.5.5石板市场 - 已鉴定{rarity} - {band}★",
        "    Identified True",
        f"    Rarity {rarity}",
        '    Class "Tablet"',
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        *market_style(band),
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def tablet_cautious_rule(rarity: str, base_types: list[str]) -> str:
    lines = [
        f"Show # 0.5.5石板市场 - 已鉴定{rarity} - 可能高价（低库存或同底材）",
        "    Identified True",
        f"    Rarity {rarity}",
        '    Class "Tablet"',
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        *cautious_style(),
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def tablet_hide_rule(rarity: str, base_types: list[str]) -> str:
    lines = [
        f"Hide # 0.5.5石板市场 - 已鉴定{rarity} - 低于10E或低置信度",
        "    Identified True",
        f"    Rarity {rarity}",
        '    Class "Tablet"',
        "    BaseType == " + " ".join(q(name) for name in sorted(base_types, key=str.casefold)),
        "    SetFontSize 30",
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def build_tablet_section(
    rows: list[dict[str, Any]],
    divine_price_e: float,
    previous_snapshot: dict[str, Any],
    previous_rows: list[dict[str, Any]],
    generated_at: str,
) -> tuple[str, dict[str, int], dict[str, dict[str, dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        rarity = row.get("variant")
        if rarity not in {"Normal", "Magic", "Rare"}:
            continue
        grouped[rarity][row["base_type"]].append(row)

    previous_grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in previous_rows:
        rarity = row.get("variant")
        if rarity in {"Normal", "Magic", "Rare"}:
            previous_grouped[rarity][row["base_type"]].append(row)

    blocks: list[str] = []
    shown = 0
    uncertain_count = 0
    hidden_count = 0
    states: dict[str, dict[str, dict[str, Any]]] = {}
    for rarity in ("Normal", "Magic", "Rare"):
        bands: dict[str, list[str]] = {band: [] for band in BAND_ORDER}
        uncertain: list[str] = []
        hidden: list[str] = []
        rarity_states: dict[str, dict[str, Any]] = {}
        for base_type, base_rows in grouped.get(rarity, {}).items():
            prices = [float(row["price_e"]) for row in base_rows]
            highest_price = max(prices)
            lowest_price = min(prices)
            all_trusted = all(
                int(row["listing_count"]) >= MIN_UNIQUE_LISTINGS
                for row in base_rows
            )
            previous_record = (
                classification_history(previous_snapshot)
                .get("precursor_tablets", {})
                .get(rarity, {})
                .get(base_type)
            )
            previous_visible = was_visible(previous_record)
            if previous_visible is None:
                old_rows = previous_grouped.get(rarity, {}).get(base_type, [])
                if old_rows:
                    best = max(old_rows, key=lambda row: float(row.get("price_e") or 0))
                    previous_visible = float(best.get("price_e") or 0) >= MIN_VALUE_E and (
                        int(best.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
                        or float(best.get("price_e") or 0) >= 50.0
                    )
            candidate = stable_single(highest_price, previous_visible)
            every_variant_visible = all(
                stable_single(price, previous_visible) for price in prices
            )
            state = "hidden"
            uncertainty: list[str] = []
            if candidate and all_trusted and every_variant_visible:
                bands[price_band(lowest_price, divine_price_e)].append(base_type)
                state = "single"
            elif candidate:
                uncertain.append(base_type)
                state = "uncertain"
                if not all_trusted:
                    uncertainty.append("low_listing_count")
                if not every_variant_visible:
                    uncertainty.append("variant_price_spread")
            else:
                hidden.append(base_type)
            rarity_states[base_type] = classification_record(
                state,
                highest_price,
                all_trusted,
                generated_at,
                previous_record,
                min_price_e=round(lowest_price, 6),
                max_price_e=round(highest_price, 6),
                uncertainty=uncertainty or None,
            )
        for band in BAND_ORDER:
            if bands[band]:
                blocks.append(tablet_rule(band, rarity, bands[band]))
                shown += len(bands[band])
        if uncertain:
            blocks.append(tablet_cautious_rule(rarity, uncertain))
            uncertain_count += len(uncertain)
        if hidden:
            blocks.append(tablet_hide_rule(rarity, hidden))
            hidden_count += len(hidden)
        states[rarity] = rarity_states
    return "".join(blocks), {
        "rows": len(rows),
        "shown": shown,
        "uncertain": uncertain_count,
        "hidden": hidden_count,
    }, states


def extra_socket_section() -> str:
    rules = [
        (
            "3孔大件（比正常多一孔）",
            "3",
            [
                "Body Armours",
                "Bows",
                "Crossbows",
                "Quarterstaves",
                "Staves",
                "Talismans",
                "Two Hand Maces",
            ],
            "29 255 149 225",
        ),
        (
            "2孔小件（比正常多一孔）",
            "2",
            [
                "Boots",
                "Bucklers",
                "Foci",
                "Gloves",
                "Helmets",
                "One Hand Maces",
                "Sceptres",
                "Shields",
                "Spears",
                "Wands",
            ],
            "124 197 214 225",
        ),
    ]
    blocks: list[str] = []
    for label, sockets, classes, background in rules:
        lines = [
            f"Show # 装备 - 0.5.5唯一保留 - {label}",
            f'    Sockets "{sockets}"',
            "    Rarity Normal Magic Rare",
            "    Class " + " ".join(q(item_class) for item_class in classes),
            "    SetTextColor 0 0 0",
            f"    SetBackgroundColor {background}",
            "    SetBorderColor 0 0 0",
            "    SetFontSize 40",
            "    MinimapIcon 1 Yellow UpsideDownHouse",
            '    CustomAlertSound "音效\\卓越装备.mp3" 300',
            "    DisableDropSound",
            "",
            "",
        ]
        blocks.append("\r\n".join(lines))
    return "".join(blocks)


def magic_sapphire_jewel_section() -> str:
    lines = [
        "Show # 珠宝 - 0.5.5保留 - 魔法蓝宝石",
        "    Rarity Magic",
        '    Class "Jewels"',
        '    BaseType == "Sapphire"',
        "    SetTextColor 109 224 249",
        "    SetBackgroundColor 31 65 72",
        "    SetBorderColor 50 230 100",
        "    SetFontSize 40",
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def active_unique_show(block: str) -> bool:
    return header(block).startswith("Show # ") and bool(
        re.search(r"(?m)^    Rarity Unique(?:\r?$| )", block)
    )


def flatten_states(node: Any, prefix: str = "") -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(node, dict) and "state" in node:
        result[prefix] = node
        return result
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}/{key}" if prefix else str(key)
            result.update(flatten_states(value, child))
    return result


def build_change_report(
    previous_snapshot: dict[str, Any],
    snapshot: dict[str, Any],
    warnings: list[str],
) -> str:
    lines = [
        "POE2 0.5.5 Forbidden Rites 10E 过滤器变更报告",
        f"生成时间（UTC）：{snapshot['generated_at_utc']}",
        f"非传奇稳定门槛：<{HIDE_BELOW_E:g}E 隐藏；{HIDE_BELOW_E:g}-{SHOW_AT_OR_ABOVE_E:g}E 保持；>={SHOW_AT_OR_ABOVE_E:g}E 显示",
        f"传奇稳定门槛：<{UNIQUE_HIDE_BELOW_E:g}E 隐藏；{UNIQUE_HIDE_BELOW_E:g}-{UNIQUE_SHOW_AT_OR_ABOVE_E:g}E 保持；>={UNIQUE_SHOW_AT_OR_ABOVE_E:g}E 显示；首次按{UNIQUE_MIN_VALUE_E:g}E初始化",
        f"原版高价值强提醒门槛：{TEN_DIVINE_MULTIPLIER:g}D（动态折算 {float((snapshot.get('priority_alerts') or {}).get('threshold_exalted') or 0):.3f}E）",
        "",
        "分类汇率（1 个主计价单位折合 E）：",
    ]
    for category, rate in sorted(snapshot.get("rate_by_category", {}).items()):
        lines.append(f"- {category}: {rate:.6f}E")

    old_states = flatten_states(classification_history(previous_snapshot))
    new_states = flatten_states(snapshot.get("classification_state", {}))
    changes: list[str] = []
    if old_states:
        for key, current in sorted(new_states.items()):
            old = old_states.get(key)
            old_name = state_name(old)
            new_name = state_name(current)
            if old_name != new_name:
                reason = current.get("uncertainty")
                if isinstance(reason, list):
                    reason = ",".join(str(item) for item in reason)
                changes.append(
                    f"- {key}: {old_name or '新增'} -> {new_name} "
                    f"({float(current.get('price_e') or 0):.3f}E；原因：{reason or 'market_threshold'})"
                )
    else:
        changes.append("- 首次写入分类状态；8-12E 区间由旧版精确 10E 规则初始化。")
    lines.extend(["", f"分类变化（{len(changes)}）：", *changes])

    old_priority = (previous_snapshot.get("priority_alerts") or {}).get("active") or {}
    new_priority = (snapshot.get("priority_alerts") or {}).get("active") or {}
    entered = sorted(set(new_priority) - set(old_priority))
    exited = sorted(set(old_priority) - set(new_priority))
    priority_changes: list[str] = []
    for key in entered:
        record = new_priority[key]
        priority_changes.append(
            f"- 进入强提醒：{key}（{float(record.get('price_divine') or 0):.3f}D；"
            f"{record.get('sound') or '无音效'}；原因：{record.get('reason') or 'threshold'}）"
        )
    for key in exited:
        record = old_priority[key]
        priority_changes.append(
            f"- 退出强提醒：{key}（上次 {float(record.get('price_divine') or 0):.3f}D；"
            f"原因：低于10D、失去可信报价或规则已移除）"
        )
    lines.extend(
        [
            "",
            f"原版高价值强提醒变化（{len(priority_changes)}）：",
            *(priority_changes or ["- 无"]),
        ]
    )

    price_changes: list[tuple[float, str]] = []
    old_exchange = previous_snapshot.get("exchange", {})
    for category, market in snapshot.get("exchange", {}).items():
        for name, current in market.items():
            old = old_exchange.get(category, {}).get(name)
            if not old:
                continue
            old_price = float(old.get("price_e") or 0)
            new_price = float(current.get("price_e") or 0)
            if old_price <= 0:
                continue
            relative = abs(new_price - old_price) / old_price
            if abs(new_price - old_price) >= 1.0 and relative >= 0.10:
                price_changes.append(
                    (
                        relative,
                        f"- exchange/{category}/{name}: {old_price:.3f}E -> {new_price:.3f}E ({(new_price / old_price - 1) * 100:+.1f}%)",
                    )
                )
    price_changes.sort(key=lambda entry: entry[0], reverse=True)
    lines.extend(
        [
            "",
            f"显著价格变化（显示前 {min(len(price_changes), 200)} 项）：",
            *(text for _relative, text in price_changes[:200]),
        ]
    )
    if not price_changes:
        lines.append("- 无")

    lines.extend(["", f"验证警告（{len(warnings)}）："])
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def sync_generator_and_tests() -> None:
    script_source = Path(__file__).resolve()
    script_bytes = script_source.read_bytes()
    for destination in (PROJECT_SCRIPT, DELIVERY_SCRIPT):
        if destination.resolve() != script_source:
            atomic_write(destination, script_bytes)

    test_source = script_source.with_name(TEST_NAME)
    if test_source.is_file():
        test_bytes = test_source.read_bytes()
        for destination in (PROJECT_TEST, DELIVERY_TEST):
            if destination.resolve() != test_source:
                atomic_write(destination, test_bytes)


def validate_filter(
    result: str,
    classification_state: dict[str, Any],
    max_stack_size: dict[str, int],
    priority_alerts: dict[str, Any],
) -> None:
    if "\n" in result.replace("\r\n", ""):
        raise RuntimeError("Transformation introduced non-CRLF newlines")
    for line_number, line in enumerate(result.split("\r\n"), 1):
        if line.lstrip().startswith("#"):
            continue
        if line.count('"') % 2:
            raise RuntimeError(f"Unbalanced quotes at line {line_number}: {line}")

    required = (
        "Show # 0.5.5传奇市场 - 可能猎首（重革腰带同底材）",
        "Show # 0.5.5原版高价值强提醒 - 大奖共享传奇底材 - 10D以上",
        "Show # 珠宝 - 0.5.5保留 - 天神之音（原版强提醒）",
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 双瓦传奇",
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 含有瓦尔传奇词缀",
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 瓦尔传奇装备",
        "Show # 传奇装备 - 卓越传奇 - 高品质",
        "Show # 传奇装备 - 卓越传奇 - 3孔",
        "Show # 传奇装备 - 卓越传奇 - 2孔",
        "Show # 传奇装备 - 唯一确定传奇 - 卡兰德之触",
        "Show # 装备 - 0.5.5唯一保留 - 3孔大件",
        "Show # 装备 - 0.5.5唯一保留 - 2孔小件",
        "Show # 珠宝 - 0.5.5保留 - 魔法蓝宝石",
        "Show # 地图 - 常规异界地图 - T16",
        "Show # 地图 - 常规异界地图 - T15",
        "Show # 地图 - 附魔地图 - T11-T16",
        "Show # 地图 - 异界地图* - 常规地图 - 7+词缀地图（0.5.5）",
        "Show # 杂项 - 先驱石板 - 普通先驱石板 - 未鉴定全部★",
        "Show # 杂项 - 任务物品",
        "Show # 全局设置 - 剩余未匹配物品",
    )
    for marker in required:
        if marker not in result:
            raise RuntimeError(f"Required rule missing: {marker}")
    if '"Sacred Bloom"' not in result:
        raise RuntimeError("0.5.5 event item Sacred Bloom is missing")

    if float(priority_alerts.get("threshold_divine") or 0) != TEN_DIVINE_MULTIPLIER:
        raise RuntimeError("Strong-alert metadata is missing its dynamic 10D threshold")
    all_blocks = re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
    strong_blocks = [
        block for block in all_blocks
        if header(block).startswith("Show # 0.5.5原版高价值强提醒 -")
    ]
    for block in strong_blocks:
        if not re.search(r"(?m)^    BaseType == ", block):
            raise RuntimeError(
                f"Strong alert does not use exact BaseType matching: {header(block)}"
            )
    for alert_id, record in (priority_alerts.get("active") or {}).items():
        name = str(record["name"])
        matching = [
            block for block in strong_blocks
            if re.search(rf'(?m)^    BaseType ==[^\r\n]*"{re.escape(name)}"', block)
        ]
        if not matching:
            raise RuntimeError(f"Active strong alert has no generated rule: {alert_id}")
        sound = str(record.get("sound") or "")
        if sound and not any(f'音效\\{sound}' in block for block in matching):
            raise RuntimeError(f"Active strong alert has the wrong sound: {alert_id}")

    jackpot_block = next(
        block for block in strong_blocks
        if header(block).startswith(
            "Show # 0.5.5原版高价值强提醒 - 大奖共享传奇底材"
        )
    )
    jackpot_markers = (
        "    Rarity Unique",
        "    SetFontSize 45",
        "    MinimapIcon 0 Red Star",
        "    PlayEffect Brown",
        '    CustomAlertSound "音效\\wyyp.mp3" 300',
    )
    if any(marker not in jackpot_block for marker in jackpot_markers):
        raise RuntimeError("Jackpot shared bases are missing the original wyyp red-star alert")
    for base_type in FIXED_JACKPOT_SHARED_UNIQUE_BASES:
        if not re.search(
            rf'(?m)^    BaseType ==[^\r\n]*"{re.escape(base_type)}"',
            jackpot_block,
        ):
            raise RuntimeError(f"Fixed jackpot shared base missing: {base_type}")

    regal_shard_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if re.search(r'(?m)^    BaseType[^\r\n]*"Regal Shard"', block)
    )
    if not header(regal_shard_block).startswith("Hide # 0.5.5市场 -"):
        raise RuntimeError("Regal Shard is shown before its forced market hide")

    headhunter_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith("Show # 0.5.5传奇市场 - 可能猎首")
    )
    headhunter_markers = (
        "    SetFontSize 45",
        "    MinimapIcon 0 Red Star",
        "    PlayEffect Brown",
        '    CustomAlertSound "音效\\wyyp.mp3" 300',
    )
    if any(marker not in headhunter_block for marker in headhunter_markers):
        raise RuntimeError("Headhunter shared-base safeguard is missing its strong alert style")

    voices_marker = "Show # 珠宝 - 0.5.5保留 - 天神之音（原版强提醒）"
    voices_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith(voices_marker)
    )
    voices_markers = (
        "    Corrupted True",
        "    Rarity Unique",
        '    Class "Jewels"',
        '    BaseType == "Sapphire"',
        "    SetTextColor 180 96 0",
        "    SetBackgroundColor 255 255 255",
        "    SetBorderColor 255 0 0",
        "    SetFontSize 42",
        "    MinimapIcon 2 Brown Cross",
        '    CustomAlertSound "音效\\天神之音.mp3" 300',
    )
    if any(marker not in voices_block for marker in voices_markers):
        raise RuntimeError("Voices is not assigned its original strong alert style")
    sapphire_market_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith("Show # 0.5.5传奇市场 - 传奇珠宝")
        and re.search(r'(?m)^    BaseType[^\r\n]*"Sapphire"', block)
    )
    if result.index(voices_block) > result.index(sapphire_market_block):
        raise RuntimeError("Voices dedicated rule is below the shared Sapphire market rule")

    active_unique_market_blocks = [
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith("Show # 0.5.5传奇市场 -")
    ]
    if any("10E-49E" in header(block) for block in active_unique_market_blocks):
        raise RuntimeError("A 10E-49E unique market show rule survived the 50E threshold")
    for protected_base in PROTECTED_SHARED_UNIQUE_BASES:
        first_matching = next(
            block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
            if re.search(
                rf'(?m)^    BaseType[^\r\n]*"{re.escape(protected_base)}"',
                block,
            )
            and re.search(r"(?m)^    Rarity Unique(?:\s|$)", block)
        )
        if not header(first_matching).startswith("Show #"):
            raise RuntimeError(f"Protected shared unique base is hidden: {protected_base}")

    unique_states = classification_state.get("unique", {})
    for section, entries in unique_states.items():
        for base_type, record in entries.items():
            state = state_name(record) or ""
            credible_listings = int(record.get("credible_listing_count") or 0)
            if state.startswith("single") and credible_listings < MIN_UNIQUE_LISTINGS:
                raise RuntimeError(
                    f"Untrusted unique classified as confirmed: {section}/{base_type}"
                )
            if (
                base_type in PROTECTED_SHARED_UNIQUE_BASES
                and state not in {"uncertain"}
            ):
                raise RuntimeError(
                    f"Protected unique state is not cautious: {section}/{base_type}={state}"
                )

    divine_marker = "Show # 0.5.5专属音效 - 神圣石"
    if divine_marker not in result:
        raise RuntimeError("Dedicated Divine Orb sound rule is missing")
    divine_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith(divine_marker)
    )
    if 'BaseType == "Divine Orb"' not in divine_block or '音效\\HYL.mp3' not in divine_block:
        raise RuntimeError("Divine Orb is not assigned to HYL.mp3")
    if result.index(divine_marker) > result.index('BaseType == "Divine Orb"'):
        raise RuntimeError("A broader market rule matches Divine Orb before its dedicated rule")

    for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result):
        first = header(block)
        if first.startswith("Show # 0.5.5市场 -") and "10D以上" in first:
            if '音效\\CYGG.mp3' not in block:
                raise RuntimeError(f"10D market rule is not assigned to CYGG.mp3: {first}")
        elif first.startswith("Show # 0.5.5市场 -") and "1D以上" in first:
            if '音效\\CYGG.mp3' in block or '音效\\HYL.mp3' not in block:
                raise RuntimeError(f"Sub-10D market tier has the wrong sound: {first}")

    if result.index("Show # 0.5.5传奇市场 - 可能猎首") > result.index(
        "Hide # 0.5.5传奇市场 - 普通传奇装备"
    ):
        raise RuntimeError("Headhunter rule is below the unique hide rules")
    if result.index("Show # 装备 - 0.5.5唯一保留") > result.index(
        "Hide # 装备 -"
    ):
        raise RuntimeError("Extra-socket rule is below ordinary equipment hides")
    if result.index("Show # 珠宝 - 0.5.5保留 - 魔法蓝宝石") > result.index(
        "Hide # 珠宝 - 常规珠宝* - 蓝宝石 - 魔法蓝宝石"
    ):
        raise RuntimeError("Magic Sapphire show rule is below its ordinary magic jewel hide")

    sounds = set(re.findall(r'(?m)^    CustomAlertSound "音效\\([^"\\]+)"', result))
    missing = sorted(name for name in sounds if not (PROJECT_DIR / "音效" / name).is_file())
    if missing:
        raise RuntimeError(f"Missing enabled sound files: {missing}")

    high_map_marker = "Show # 地图 - 异界地图* - 常规地图 - 7+词缀地图（0.5.5）"
    high_map_block = next(
        block for block in re.split(r"(?m)(?=^(?:Show|Hide) # )", result)
        if header(block).startswith(high_map_marker)
    )
    if 'HasExplicitMod >=7 "a" "e" "i" "o" "u" "y"' not in high_map_block:
        raise RuntimeError("T14+ high-mod waystone rule is not set to HasExplicitMod >=7")
    if result.index(high_map_marker) > result.index("Show # 地图 - 常规异界地图 - T16"):
        raise RuntimeError("T14+ high-mod waystone rule is below the generic T16 rule")

    exchange_states = classification_state.get("exchange", {})
    for category, entries in exchange_states.items():
        for name, record in entries.items():
            state = state_name(record) or ""
            if not state.startswith("stack:"):
                continue
            minimum = int(state.split(":", 1)[1])
            maximum = max_stack_size.get(name)
            if maximum is None or minimum > maximum:
                raise RuntimeError(
                    f"Invalid stack classification for {category}/{name}: {minimum}>{maximum}"
                )


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    raw = SOURCE.read_bytes()
    if b"\r\n" not in raw or b"\n" in raw.replace(b"\r\n", b""):
        raise RuntimeError("Source is not consistently CRLF encoded")
    source_text = raw.decode("utf-8")

    previous_snapshot: dict[str, Any] = {}
    previous_path = PROJECT_SNAPSHOT if PROJECT_SNAPSHOT.is_file() else DELIVERY_SNAPSHOT
    if previous_path.is_file():
        previous_snapshot = json.loads(previous_path.read_text(encoding="utf-8"))

    leagues = fetch_json(f"{POE_NINJA_ROOT}/leagues")
    if not isinstance(leagues, list) or not leagues:
        raise RuntimeError("No PoE2 economy leagues returned")
    league_ids = [entry.get("id") for entry in leagues]
    if LEAGUE not in league_ids:
        raise RuntimeError(f"League {LEAGUE!r} not found; available: {league_ids}")
    if league_ids[0] != LEAGUE:
        raise RuntimeError(f"{LEAGUE!r} is not the current temporary league: {league_ids[0]!r}")

    currency_payload = fetch_exchange_payload("Currency")
    currency_core = currency_payload["core"]
    if currency_core.get("primary") == "divine":
        divine_price_e = float(currency_core.get("rates", {}).get("exalted") or 0)
    else:
        divine_line = next(
            (line for line in currency_payload.get("lines", []) if line.get("id") == "divine"),
            None,
        )
        divine_price_e = float((divine_line or {}).get("primaryValue") or 0)
    if divine_price_e <= 0:
        raise RuntimeError("Could not determine Divine Orb price in Exalted Orbs")

    exchange_payloads: dict[str, dict[str, Any]] = {"Currency": currency_payload}
    for category, _cn, _classes, _stackable in EXCHANGE_SPECS:
        if category not in exchange_payloads:
            exchange_payloads[category] = fetch_exchange_payload(category)
    exchange_markets = {
        category: parse_exchange(payload, divine_price_e)
        for category, payload in exchange_payloads.items()
    }

    stash_payloads = {category: fetch_stash_payload(category) for category in UNIQUE_STASH_TYPES}
    stash_markets = {
        category: parse_stash(payload, divine_price_e)
        for category, payload in stash_payloads.items()
    }

    rate_by_category = {
        **{
            f"exchange/{category}": exalted_factor(payload["core"], divine_price_e)
            for category, payload in exchange_payloads.items()
        },
        **{
            f"stash/{category}": exalted_factor(payload["core"], divine_price_e)
            for category, payload in stash_payloads.items()
        },
    }
    max_stack_size, stack_warnings = fetch_stack_size_catalog(previous_snapshot)

    exchange_section, exchange_stats, exchange_states, exchange_warnings = build_exchange_section(
        exchange_markets,
        divine_price_e,
        previous_snapshot,
        max_stack_size,
        generated_at,
    )
    exchange_priority_section, priority_alerts = build_exchange_strong_alerts(
        exchange_markets, divine_price_e
    )
    exchange_section = exchange_priority_section + exchange_section
    unique_sections: dict[str, str] = {}
    unique_stats: dict[str, dict[str, int]] = {}
    unique_states: dict[str, dict[str, dict[str, Any]]] = {}
    previous_stash: dict[str, list[dict[str, Any]]] = {}
    raw_previous_stash = previous_snapshot.get("stash", {})
    old_rates = previous_snapshot.get("rate_by_category", {})
    old_global_rate = float(previous_snapshot.get("divine_price_exalted") or 0)
    for stash_key, old_rows in raw_previous_stash.items():
        scale = 1.0
        if not old_rates and old_global_rate > 0:
            # Old snapshots converted every stash category with the Currency rate.
            scale = rate_by_category.get(f"stash/{stash_key}", old_global_rate) / old_global_rate
        previous_stash[stash_key] = [
            {**row, "price_e": float(row.get("price_e") or 0) * scale}
            for row in old_rows
        ]
    for key, label, rows in (
        ("jewels", "传奇珠宝", stash_markets["UniqueJewels"]),
        ("flasks", "传奇药剂", stash_markets["UniqueFlasks"]),
        ("charms", "传奇咒符", stash_markets["UniqueCharms"]),
        ("relics", "传奇遗物", stash_markets["UniqueSanctumRelics"]),
        ("tablets", "传奇石板", stash_markets["UniqueTablets"]),
    ):
        stash_key = {
            "jewels": "UniqueJewels",
            "flasks": "UniqueFlasks",
            "charms": "UniqueCharms",
            "relics": "UniqueSanctumRelics",
            "tablets": "UniqueTablets",
        }[key]
        section, stats, states = build_unique_section(
            key,
            label,
            rows,
            divine_price_e,
            previous_snapshot,
            previous_stash.get(stash_key, []),
            generated_at,
        )
        priority_section = ""
        active_priority: dict[str, dict[str, Any]] = {}
        if key == "jewels":
            priority_section, active_priority = active_unique_priority_alerts(
                "jewels",
                rows,
                (
                    ("Ruby", "传奇红玉", "legendary_jewel"),
                    ("Diamond", "传奇宝钻", "legendary_jewel"),
                    ("Sapphire", "传奇蓝宝石", "legendary_jewel"),
                ),
                divine_price_e,
            )
            unique_sections[key] = voices_rule() + priority_section + section
        elif key == "relics":
            priority_section, active_priority = active_unique_priority_alerts(
                "relics",
                rows,
                (("Incense Relic", "焚香遗物", "incense_relic"),),
                divine_price_e,
            )
            unique_sections[key] = priority_section + section
        else:
            unique_sections[key] = section
        priority_alerts.update(active_priority)
        unique_stats[key] = stats
        unique_states[key] = states

    gear_rows = (
        stash_markets["UniqueWeapons"]
        + stash_markets["UniqueArmours"]
        + stash_markets["UniqueAccessories"]
    )
    previous_gear_rows = (
        previous_stash.get("UniqueWeapons", [])
        + previous_stash.get("UniqueArmours", [])
        + previous_stash.get("UniqueAccessories", [])
    )
    gear_section, gear_stats, gear_states = build_unique_section(
        "gear",
        "普通传奇装备",
        gear_rows,
        divine_price_e,
        previous_snapshot,
        previous_gear_rows,
        generated_at,
        excluded_bases={"Heavy Belt"},
    )
    heavy_rows = [row for row in gear_rows if row["base_type"] == "Heavy Belt"]
    heavy_prices = [float(row["price_e"]) for row in heavy_rows]
    credible_heavy_rows = [
        row for row in heavy_rows
        if int(row.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
    ]
    credible_heavy_top = max(
        credible_heavy_rows,
        key=lambda row: float(row.get("price_e") or 0),
        default=None,
    )
    credible_heavy_max = float((credible_heavy_top or {}).get("price_e") or 0)
    previous_heavy_record = (
        classification_history(previous_snapshot)
        .get("unique", {})
        .get("gear", {})
        .get("Heavy Belt")
    )
    gear_states["Heavy Belt"] = classification_record(
        "uncertain",
        credible_heavy_max if credible_heavy_rows else max(heavy_prices, default=0.0),
        bool(credible_heavy_rows),
        generated_at,
        previous_heavy_record,
        hysteresis_low_e=UNIQUE_HIDE_BELOW_E,
        hysteresis_high_e=UNIQUE_SHOW_AT_OR_ABOVE_E,
        min_price_e=round(min(heavy_prices, default=0.0), 6),
        max_price_e=round(max(heavy_prices, default=0.0), 6),
        credible_max_price_e=round(credible_heavy_max, 6),
        credible_listing_count=int((credible_heavy_top or {}).get("listing_count") or 0),
        unique_names=sorted({str(row.get("name") or "Heavy Belt") for row in heavy_rows}),
        uncertainty=["protected_shared_base", "headhunter_shared_base_safeguard"],
    )
    gear_stats["bases"] += 1
    gear_stats["uncertain"] += 1
    unique_stats["gear"] = gear_stats
    unique_states["gear"] = gear_states
    gear_priority_section, gear_priority_alerts = active_unique_priority_alerts(
        "gear",
        gear_rows,
        (
            ("Runic Fork", "符文叉", "runic_fork"),
            ("Runemastered Runic Fork", "符文大师符文叉", "runic_fork"),
            ("Grand Spear", "宏伟长矛", "grand_spear"),
            ("Ornate Gauntlets", "华丽护手", "ornate_gauntlets"),
        ),
        divine_price_e,
    )
    jackpot_section, jackpot_alerts = build_jackpot_shared_alerts(
        gear_rows, gear_states, divine_price_e
    )
    priority_alerts.update(gear_priority_alerts)
    priority_alerts.update(jackpot_alerts)
    unique_sections["gear"] = (
        headhunter_rule() + gear_priority_section + jackpot_section + gear_section
    )
    tablet_section, tablet_stats, tablet_states = build_tablet_section(
        stash_markets["PrecursorTablets"],
        divine_price_e,
        previous_snapshot,
        previous_stash.get("PrecursorTablets", []),
        generated_at,
    )

    parts = re.split(r"(?m)(?=^(?:Show|Hide) # )", source_text)
    banner = (
        "#===============================================================================================================\r\n"
        "# [08] POE2 0.5.5 Forbidden Rites 10E过滤器\r\n"
        f"# 生成时间（UTC）：{generated_at}；行情：poe.ninja Forbidden Rites\r\n"
        f"# 非传奇稳定10E：<{HIDE_BELOW_E:g}E隐藏，{HIDE_BELOW_E:g}-{SHOW_AT_OR_ABOVE_E:g}E保持，>={SHOW_AT_OR_ABOVE_E:g}E显示\r\n"
        f"# 传奇稳定50E：<{UNIQUE_HIDE_BELOW_E:g}E隐藏，{UNIQUE_HIDE_BELOW_E:g}-{UNIQUE_SHOW_AT_OR_ABOVE_E:g}E保持，>={UNIQUE_SHOW_AT_OR_ABOVE_E:g}E显示；首次按{UNIQUE_MIN_VALUE_E:g}E初始化\r\n"
        f"# 原版高价值强提醒：可信价值达到{TEN_DIVINE_MULTIPLIER:g}D时恢复专属视觉与音效；低于门槛自动退出\r\n"
        "# 低成交量基础通货直接隐藏；Regal Shard强制隐藏；Heavy Belt使用猎首强提醒\r\n"
        "# 天神之音保留原版显示与专属天神之音.mp3强提醒\r\n"
        "# 音效：10D以上市场通货使用CYGG.mp3；神圣石固定使用HYL.mp3\r\n"
        "# 普通/魔法/稀有装备仅显示额外一孔；保留T15/T16、附魔地图、T14+七词缀及未知物品提醒\r\n"
        "#===============================================================================================================\r\n\r\n"
    )
    parts[0] += banner

    inserted = {
        "exchange": False,
        "jewels": False,
        "flasks": False,
        "charms": False,
        "gear": False,
        "relics": False,
        "tablets": False,
        "precursor_tablets": False,
        "extra_sockets": False,
        "magic_basic_jewels": False,
    }
    converted_unique = 0
    converted_equipment = 0
    converted_tablets = 0
    preserved_unique_headers = {
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 双瓦传奇",
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 含有瓦尔传奇词缀",
        "Show # 传奇装备 - 赛季传奇 - 瓦尔传奇 - 瓦尔传奇装备",
        "Show # 传奇装备 - 卓越传奇 - 高品质",
        "Show # 传奇装备 - 卓越传奇 - 3孔",
        "Show # 传奇装备 - 卓越传奇 - 2孔",
        "Show # 传奇装备 - 唯一确定传奇 - 卡兰德之触",
    }

    output_parts: list[str] = []
    for block in parts:
        first = header(block)

        if first.startswith("Show # 地图 - 异界地图* - 常规地图 - 8词缀地图"):
            block = block.replace(
                "Show # 地图 - 异界地图* - 常规地图 - 8词缀地图",
                "Show # 地图 - 异界地图* - 常规地图 - 7+词缀地图（0.5.5）",
                1,
            ).replace('HasExplicitMod >=8 "a" "e" "i" "o" "u" "y"',
                       'HasExplicitMod >=7 "a" "e" "i" "o" "u" "y"', 1)
            first = header(block)

        if not inserted["exchange"] and first.startswith(("Show # 通货 -", "Hide # 通货 -")):
            output_parts.append(exchange_section)
            inserted["exchange"] = True
        if not inserted["jewels"] and first.startswith("Show # 珠宝 - 传奇珠宝 -"):
            output_parts.append(unique_sections["jewels"])
            inserted["jewels"] = True
        if not inserted["magic_basic_jewels"] and first.startswith(
            "Hide # 珠宝 - 常规珠宝* - 红玉 - 魔法红玉"
        ):
            output_parts.append(magic_sapphire_jewel_section())
            inserted["magic_basic_jewels"] = True
        if not inserted["flasks"] and first.startswith("Show # 药剂 - 生命传奇药剂"):
            output_parts.append(unique_sections["flasks"])
            inserted["flasks"] = True
        if not inserted["charms"] and first.startswith("Show # 药剂 - 传奇咒符 -"):
            output_parts.append(unique_sections["charms"])
            inserted["charms"] = True
        if not inserted["gear"] and first.startswith(
            "Show # 传奇装备 - 唯一确定传奇 - 40D以上"
        ):
            output_parts.append(unique_sections["gear"])
            inserted["gear"] = True
        if not inserted["relics"] and first.startswith("Show # 杂项 - 遗物 -"):
            output_parts.append(unique_sections["relics"])
            inserted["relics"] = True
        if not inserted["tablets"] and first.startswith(
            "Show # 杂项 - 先驱石板 - 传奇先驱石板 -"
        ):
            output_parts.append(unique_sections["tablets"])
            inserted["tablets"] = True
        if not inserted["precursor_tablets"] and first.startswith(
            "Show # 杂项 - 先驱石板 - 普通先驱石板 -"
        ):
            output_parts.append(tablet_section)
            inserted["precursor_tablets"] = True
        if not inserted["extra_sockets"] and first.startswith("Show # 装备 -"):
            output_parts.append(extra_socket_section())
            inserted["extra_sockets"] = True

        if first.startswith("Show # 装备 -"):
            block = hide_block(block, "仅保留额外孔普通装备")
            converted_equipment += 1
        elif (
            first.startswith("Show # 杂项 - 先驱石板 - 普通先驱石板 -")
            and "未鉴定全部" not in first
        ):
            block = hide_block(block, "由0.5.5石板市场规则接管")
            converted_tablets += 1
        elif active_unique_show(block) and first not in preserved_unique_headers:
            block = hide_block(block, "由0.5.5传奇市场规则接管")
            converted_unique += 1

        output_parts.append(dedupe_exact_lines(block))

    if not all(inserted.values()):
        missing = sorted(key for key, value in inserted.items() if not value)
        raise RuntimeError(f"Failed to insert generated sections: {missing}")

    result = "".join(output_parts).replace('""', '" "')
    classification_state = {
        "exchange": exchange_states,
        "unique": unique_states,
        "precursor_tablets": tablet_states,
    }
    priority_metadata = {
        "threshold_divine": TEN_DIVINE_MULTIPLIER,
        "threshold_exalted": round(TEN_DIVINE_MULTIPLIER * divine_price_e, 6),
        "active": dict(sorted(priority_alerts.items())),
    }
    validate_filter(result, classification_state, max_stack_size, priority_metadata)
    encoded = result.encode("utf-8")

    snapshot = {
        "generated_at_utc": generated_at,
        "league": LEAGUE,
        "patch": PATCH_VERSION,
        "classification_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "threshold_exalted": MIN_VALUE_E,
        "hysteresis": {
            "hide_below_exalted": HIDE_BELOW_E,
            "show_at_or_above_exalted": SHOW_AT_OR_ABOVE_E,
        },
        "unique_threshold_exalted": UNIQUE_MIN_VALUE_E,
        "unique_hysteresis": {
            "hide_below_exalted": UNIQUE_HIDE_BELOW_E,
            "show_at_or_above_exalted": UNIQUE_SHOW_AT_OR_ABOVE_E,
            "first_seen_threshold_exalted": UNIQUE_MIN_VALUE_E,
        },
        "priority_alerts": priority_metadata,
        "confidence_policy": {
            "exchange_minimum_volume_exalted": MIN_EXCHANGE_VOLUME_E,
            "exchange_minimum_volume_multiplier": 5.0,
            "unique_minimum_listings": MIN_UNIQUE_LISTINGS,
        },
        "divine_price_exalted": divine_price_e,
        "rate_by_category": rate_by_category,
        "max_stack_size": max_stack_size,
        "classification_state": classification_state,
        "exchange": exchange_markets,
        "stash": stash_markets,
        "validation_warnings": stack_warnings + exchange_warnings,
        "stats": {
            "exchange": exchange_stats,
            "unique": unique_stats,
            "precursor_tablets": tablet_stats,
            "converted_unique_rules": converted_unique,
            "converted_equipment_rules": converted_equipment,
            "converted_tablet_rules": converted_tablets,
        },
    }
    snapshot_bytes = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    report = build_change_report(
        previous_snapshot, snapshot, stack_warnings + exchange_warnings
    ).encode("utf-8")

    # All remote reads, transformations and validations complete before any destination is replaced.
    atomic_write(OUTPUT, encoded)
    atomic_write(DELIVERY_OUTPUT, encoded)
    atomic_write(PROJECT_SNAPSHOT, snapshot_bytes)
    atomic_write(DELIVERY_SNAPSHOT, snapshot_bytes)
    atomic_write(PROJECT_CHANGE_REPORT, report)
    atomic_write(DELIVERY_CHANGE_REPORT, report)
    sync_generator_and_tests()

    print(f"source_bytes={len(raw)}")
    print(f"output_bytes={len(encoded)}")
    print(f"league={LEAGUE}")
    print(f"patch={PATCH_VERSION}")
    print(f"threshold_e={MIN_VALUE_E}")
    print(f"hysteresis_e={HIDE_BELOW_E}-{SHOW_AT_OR_ABOVE_E}")
    print(f"unique_threshold_e={UNIQUE_MIN_VALUE_E}")
    print(f"unique_hysteresis_e={UNIQUE_HIDE_BELOW_E}-{UNIQUE_SHOW_AT_OR_ABOVE_E}")
    print(f"divine_price_e={divine_price_e}")
    print(f"converted_unique_rules={converted_unique}")
    print(f"converted_equipment_rules={converted_equipment}")
    print(f"converted_tablet_rules={converted_tablets}")
    for category, stats in exchange_stats.items():
        print(f"exchange_{category}={stats}")
    for category, stats in unique_stats.items():
        print(f"unique_{category}={stats}")
    print(f"precursor_tablets={tablet_stats}")
    print(f"output={OUTPUT}")
    print(f"delivery_output={DELIVERY_OUTPUT}")
    print(f"snapshot={PROJECT_SNAPSHOT}")
    print(f"change_report={PROJECT_CHANGE_REPORT}")


if __name__ == "__main__":
    main()
