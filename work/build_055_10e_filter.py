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
SNAPSHOT_NAME = "forbidden_rites_0.5.5_10e_market_snapshot.json"
PROJECT_SNAPSHOT = PROJECT_DIR / "work" / SNAPSHOT_NAME
DELIVERY_SNAPSHOT = Path("/Users/christina/Documents/Codex/2026-08-17/dan/work") / SNAPSHOT_NAME

LEAGUE = "Forbidden Rites"
PATCH_VERSION = "0.5.5"
MIN_VALUE_E = 10.0
HIDE_BELOW_E = 8.0
SHOW_AT_OR_ABOVE_E = 12.0
MIN_EXCHANGE_VOLUME_E = 100.0
MIN_UNIQUE_LISTINGS = 3
TEN_DIVINE_MULTIPLIER = 10.0
DIVINE_ORB_NAME = "Divine Orb"
POE_NINJA_ROOT = "https://poe.ninja/poe2/api/economy"
POE2DB_ROOT = "https://poe2db.tw/us"
CHANGE_REPORT_NAME = "forbidden_rites_0.5.5_10e_change_report.txt"
CLASSIFICATION_SCHEMA_VERSION = 2
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

BAND_ORDER = ("1D以上", "100E-1D", "50E-99E", "10E-49E")

VISIBLE_STATES = {"single", "uncertain"}


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
    if snapshot.get("classification_schema_version") != CLASSIFICATION_SCHEMA_VERSION:
        return {}
    value = snapshot.get("classification_state")
    return value if isinstance(value, dict) else {}


def was_visible(value: Any) -> bool | None:
    state = state_name(value)
    if state is None:
        return None
    return state.split(":", 1)[0] in VISIBLE_STATES


def stable_single(price_e: float, previous_visible: bool | None) -> bool:
    if price_e >= SHOW_AT_OR_ABOVE_E:
        return True
    if price_e < HIDE_BELOW_E:
        return False
    if previous_visible is not None:
        return previous_visible
    return price_e >= MIN_VALUE_E


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
    # The original generator used the highest row per base and allowed >=50E through.
    best = max(rows, key=lambda row: float(row.get("price_e") or 0))
    return float(best.get("price_e") or 0) >= MIN_VALUE_E and (
        int(best.get("listing_count") or 0) >= MIN_UNIQUE_LISTINGS
        or float(best.get("price_e") or 0) >= 50.0
    )


def classification_record(
    state: str,
    price_e: float,
    trusted: bool,
    generated_at: str,
    previous_record: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    previous_name = state_name(previous_record)
    last_stable_state = state
    if HIDE_BELOW_E <= price_e < SHOW_AT_OR_ABOVE_E and previous_name:
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
            if wants_single:
                if trusted:
                    bands[price_band(price_e, divine_price_e)].append(name)
                    if (
                        name != DIVINE_ORB_NAME
                        and price_e >= TEN_DIVINE_MULTIPLIER * divine_price_e
                    ):
                        ten_divine.append(name)
                    state = "single"
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
        f"Show # 0.5.5传奇市场 - {category_cn} - 可能高价（同底材或低库存）",
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
        f"Hide # 0.5.5传奇市场 - {category_cn} - 低于10E或低置信度",
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

    bands: dict[str, list[str]] = {band: [] for band in BAND_ORDER}
    uncertain: list[str] = []
    hidden: list[str] = []
    states: dict[str, dict[str, Any]] = {}
    for base_type, base_rows in grouped.items():
        prices = [float(row["price_e"]) for row in base_rows]
        highest_price = max(prices)
        lowest_price = min(prices)
        trusted_rows = [
            int(row["listing_count"]) >= MIN_UNIQUE_LISTINGS for row in base_rows
        ]
        all_trusted = all(trusted_rows)
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
        candidate = stable_single(highest_price, previous_visible)
        every_variant_visible = all(
            stable_single(price, previous_visible) for price in prices
        )
        regular = candidate and all_trusted and len(names) == 1 and every_variant_visible
        state = "hidden"
        uncertainty: list[str] = []
        if candidate and regular:
            bands[price_band(lowest_price, divine_price_e)].append(base_type)
            state = "single"
        elif candidate:
            uncertain.append(base_type)
            state = "uncertain"
            if not all_trusted:
                uncertainty.append("low_listing_count")
            if len(names) > 1:
                uncertainty.append("shared_base_type")
            if not every_variant_visible:
                uncertainty.append("variant_price_spread")
        else:
            hidden.append(base_type)
        states[base_type] = classification_record(
            state,
            highest_price,
            all_trusted,
            generated_at,
            previous_record,
            min_price_e=round(lowest_price, 6),
            max_price_e=round(highest_price, 6),
            listing_count_min=min(int(row["listing_count"]) for row in base_rows),
            unique_names=sorted(names),
            uncertainty=uncertainty or None,
        )

    blocks = [
        unique_rule(category_cn, band, bands[band])
        for band in BAND_ORDER
        if bands[band]
    ]
    if uncertain:
        blocks.append(unique_cautious_rule(category_cn, uncertain))
    if hidden:
        blocks.append(unique_hide_rule(category_cn, hidden))
    return "".join(blocks), {
        "rows": len(rows),
        "bases": len(grouped),
        "shown": sum(len(names) for names in bands.values()),
        "uncertain": len(uncertain),
        "hidden": len(hidden),
    }, states


def headhunter_rule() -> str:
    lines = [
        "Show # 0.5.5传奇市场 - 可能猎首（重革腰带同底材）",
        "    Rarity Unique",
        '    BaseType == "Heavy Belt"',
        *cautious_style(),
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
        f"稳定门槛：<{HIDE_BELOW_E:g}E 隐藏；{HIDE_BELOW_E:g}-{SHOW_AT_OR_ABOVE_E:g}E 保持；>={SHOW_AT_OR_ABOVE_E:g}E 显示",
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
                changes.append(
                    f"- {key}: {old_name or '新增'} -> {new_name} "
                    f"({float(current.get('price_e') or 0):.3f}E)"
                )
    else:
        changes.append("- 首次写入分类状态；8-12E 区间由旧版精确 10E 规则初始化。")
    lines.extend(["", f"分类变化（{len(changes)}）：", *changes])

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


def validate_filter(
    result: str,
    classification_state: dict[str, Any],
    max_stack_size: dict[str, int],
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
        unique_sections[key] = section
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
    unique_sections["gear"] = headhunter_rule() + gear_section
    heavy_rows = [row for row in gear_rows if row["base_type"] == "Heavy Belt"]
    heavy_prices = [float(row["price_e"]) for row in heavy_rows]
    previous_heavy_record = (
        classification_history(previous_snapshot)
        .get("unique", {})
        .get("gear", {})
        .get("Heavy Belt")
    )
    gear_states["Heavy Belt"] = classification_record(
        "uncertain",
        max(heavy_prices, default=0.0),
        all(int(row["listing_count"]) >= MIN_UNIQUE_LISTINGS for row in heavy_rows),
        generated_at,
        previous_heavy_record,
        min_price_e=round(min(heavy_prices, default=0.0), 6),
        max_price_e=round(max(heavy_prices, default=0.0), 6),
        unique_names=sorted({str(row.get("name") or "Heavy Belt") for row in heavy_rows}),
        uncertainty=["headhunter_shared_base_safeguard"],
    )
    gear_stats["bases"] += 1
    gear_stats["uncertain"] += 1
    unique_stats["gear"] = gear_stats
    unique_states["gear"] = gear_states
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
        f"# 稳定10E：<{HIDE_BELOW_E:g}E隐藏，{HIDE_BELOW_E:g}-{SHOW_AT_OR_ABOVE_E:g}E保持上次分类，>={SHOW_AT_OR_ABOVE_E:g}E显示；低置信度单独提醒\r\n"
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
    validate_filter(result, classification_state, max_stack_size)
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

    print(f"source_bytes={len(raw)}")
    print(f"output_bytes={len(encoded)}")
    print(f"league={LEAGUE}")
    print(f"patch={PATCH_VERSION}")
    print(f"threshold_e={MIN_VALUE_E}")
    print(f"hysteresis_e={HIDE_BELOW_E}-{SHOW_AT_OR_ABOVE_E}")
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
