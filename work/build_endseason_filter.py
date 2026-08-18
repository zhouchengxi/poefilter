#!/usr/bin/env python3
from __future__ import annotations

import html as html_lib
import math
import re
import shutil
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


PROJECT_DIR = Path("/Users/christina/self/poe")
SOURCE = PROJECT_DIR / "[06]打宝82物等-T17+ 天枢过滤器-POE2-曼波语音.filter"
OUTPUT_NAME = "[07]赛季末20E-T15+ 天枢过滤器-POE2-曼波语音.filter"
OUTPUT = PROJECT_DIR / OUTPUT_NAME
DELIVERY_DIR = Path("/Users/christina/Documents/Codex/2026-08-17/dan/outputs")
DELIVERY_OUTPUT = DELIVERY_DIR / OUTPUT_NAME

MARKET_ROOT = "https://www.poe2pricecheck.com/poe2/runes-of-aldur"
OUT_OF_GAMES_ROOT = "https://outof.games/realms/poe2/economy"
DIVINE_PRICE_E_FALLBACK = 333.0
MIN_VALUE_E = 20.0
MIN_LISTED_QUANTITY = 10
MIN_EXTERNAL_VOLUME = 10.0


def fetch_page(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 Codex filter updater",
                "Connection": "close",
            },
        )
        try:
            return urlopen(request, timeout=30).read().decode("utf-8")
        except (URLError, TimeoutError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def fetch_market(category: str) -> dict[str, tuple[float, int, int]]:
    page = fetch_page(f"{MARKET_ROOT}/{category}/")
    result: dict[str, tuple[float, int, int]] = {}
    for row in re.findall(r'<tr data-name="[^"]+">(.*?)</tr>', page, re.S):
        name_match = re.search(r"<div><a [^>]+>([^<]+)</a>", row)
        price_match = re.search(r'<td class="price-cell"><strong>([^<]+)', row)
        quantity_match = re.search(r'data-listed-quantity="([^"]+)"', row)
        stack_match = re.search(r'data-stack-size="([^"]+)"', row)
        if not (name_match and price_match and quantity_match and stack_match):
            continue
        name = html_lib.unescape(name_match.group(1))
        price = float(price_match.group(1).replace(",", ""))
        quantity = int(quantity_match.group(1).replace(",", ""))
        stack_size = int(stack_match.group(1).replace(",", ""))
        result[name] = (price, quantity, stack_size)
    if not result:
        raise RuntimeError(f"No market rows parsed for {category}")
    return result


def fetch_divine_market(
    category: str, divine_price_e: float
) -> dict[str, tuple[float, float, int]]:
    """Fetch poe.ninja-derived prices quoted in Divine and convert them to Exalted."""
    page = fetch_page(f"{OUT_OF_GAMES_ROOT}/{category}/")
    result: dict[str, tuple[float, float, int]] = {}
    for row in re.findall(r'<tr data-name="[^"]+"(.*?)</tr>', page, re.S):
        name_match = re.search(r"<span>([^<]+)</span>", row)
        value_match = re.search(r'data-value="([^"]+)"', row)
        volume_match = re.search(r'data-volume="([^"]*)"', row)
        if not (name_match and value_match and volume_match):
            continue
        name = html_lib.unescape(name_match.group(1))
        value_e = float(value_match.group(1).replace(",", "")) * divine_price_e
        volume = float(volume_match.group(1).replace(",", "") or 0)
        result[name] = (value_e, volume, 0)
    if not result:
        raise RuntimeError(f"No external market rows parsed for {category}")
    return result


def header(block: str) -> str:
    return block.split("\r\n", 1)[0]


def extract_base_types(block: str) -> list[str]:
    names: list[str] = []
    for line in block.split("\r\n"):
        if line.startswith("    BaseType"):
            names.extend(re.findall(r'"([^"]+)"', line))
    return names


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


def show_block(block: str, new_header: str | None = None) -> str:
    lines = block.split("\r\n")
    if new_header:
        lines[0] = new_header
    elif lines[0].startswith("Hide # "):
        lines[0] = "Show # " + lines[0][7:]
    for index, line in enumerate(lines[1:], 1):
        match = re.match(
            r"#\s+(MinimapIcon|PlayEffect|PlayAlertSound|CustomAlertSound)(.*)", line
        )
        if match:
            lines[index] = f"    {match.group(1)}{match.group(2)}"
    return "\r\n".join(lines)


def set_rarity(block: str, rarity: str) -> str:
    lines = block.split("\r\n")
    for index, line in enumerate(lines):
        if line.startswith("    Rarity "):
            lines[index] = f"    Rarity {rarity}"
            break
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


def set_stack_size(block: str, minimum: int, label: str) -> str:
    lines = block.split("\r\n")
    lines[0] = re.sub(r" - [^-]+$", f" - {label}", lines[0])
    for index, line in enumerate(lines):
        if line.startswith("    StackSize "):
            lines[index] = f"    StackSize >= {minimum}"
            break
    else:
        lines.insert(1, f"    StackSize >= {minimum}")
    return "\r\n".join(lines)


def currency_stack_clone(block: str, name: str, minimum: int) -> str:
    clone = show_block(
        block,
        f"Show # 通货 - 基础通货* - 20E堆叠 - {name}（{minimum}个以上）",
    )
    return set_stack_size(clone, minimum, f"{name}（{minimum}个以上）")


def show_spirit_gems_17_18(block: str) -> str:
    lines = block.split("\r\n")
    lines[0] = "Show # 技能石 - 精神宝石 - 17至18级（20E以上）"
    for index, line in enumerate(lines):
        if line.startswith("    BaseType "):
            lines[index] = (
                '    BaseType "Uncut Spirit Gem (Level 17)" '
                '"Uncut Spirit Gem (Level 18)"'
            )
        elif line.startswith("#      MinimapIcon "):
            lines[index] = "    MinimapIcon 2 Orange Kite"
        elif line.startswith("#      CustomAlertSound "):
            lines[index] = '    CustomAlertSound "音效\\精神宝石.mp3" 300'
    return "\r\n".join(lines)


def q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def class_line(item_classes: str | list[str]) -> str:
    if isinstance(item_classes, str):
        item_classes = [item_classes]
    return "    Class " + " ".join(q(item_class) for item_class in item_classes)


def market_rule(
    category_cn: str,
    band: str,
    names: list[str],
    item_classes: str | list[str],
    header_prefix: str = "通货 - 赛季通货*",
) -> str:
    styles = {
        "1D以上": [
            "    SetTextColor 245 245 245",
            "    SetBackgroundColor 255 0 58",
            "    SetBorderColor 156 2 2",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Triangle",
            "    PlayEffect Red",
            '    CustomAlertSound "音效\\CYGG.mp3" 300',
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
        "20E-49E": [
            "    SetTextColor 0 0 0",
            "    SetBackgroundColor 245 139 87 255",
            "    SetBorderColor 0 0 0",
            "    SetFontSize 40",
            "    MinimapIcon 2 Orange Triangle",
            "    PlayEffect Orange",
            '    CustomAlertSound "音效\\MBWDD.mp3" 300',
        ],
    }
    base_types = " ".join(q(name) for name in sorted(names, key=str.casefold))
    lines = [
        f"Show # {header_prefix} - {category_cn} - 国际服赛季末市场 {band}★",
        class_line(item_classes),
        f"    BaseType == {base_types}",
        *styles[band],
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def market_hide_rule(
    category_cn: str,
    names: list[str],
    item_classes: str | list[str],
    header_prefix: str = "通货 - 赛季通货*",
) -> str:
    base_types = " ".join(q(name) for name in sorted(names, key=str.casefold))
    lines = [
        f"Hide # {header_prefix} - {category_cn} - 国际服赛季末市场 20E以下或低置信度",
        class_line(item_classes),
        f"    BaseType == {base_types}",
        "    SetFontSize 30",
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


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
        class_values = " ".join(q(item_class) for item_class in classes)
        lines = [
            f"Show # 装备 - 赛季末唯一保留 - {label}",
            f'    Sockets "{sockets}"',
            "    Rarity Normal Magic Rare",
            f"    Class {class_values}",
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


def split_market_rules(
    market: dict[str, tuple[float, float, int]],
    current_shown: set[str],
    missing_bands: dict[str, set[str]],
    divine_price_e: float,
    corroborated: set[str] | None = None,
    minimum_liquidity: float = MIN_LISTED_QUANTITY,
) -> tuple[dict[str, list[str]], list[str]]:
    corroborated = corroborated or set()
    bands: dict[str, set[str]] = {
        "1D以上": set(),
        "100E-1D": set(),
        "50E-99E": set(),
        "20E-49E": set(),
    }
    hidden: set[str] = set()

    for name, (price, quantity, _stack_size) in market.items():
        trusted_show = (
            quantity >= minimum_liquidity
            or name in current_shown
            or name in corroborated
        )
        if price < MIN_VALUE_E or not trusted_show:
            hidden.add(name)
            continue
        if price >= divine_price_e:
            bands["1D以上"].add(name)
        elif price >= 100:
            bands["100E-1D"].add(name)
        elif price >= 50:
            bands["50E-99E"].add(name)
        else:
            bands["20E-49E"].add(name)

    for band, names in missing_bands.items():
        for name in names:
            if name not in market:
                bands[band].add(name)

    return ({key: sorted(value) for key, value in bands.items()}, sorted(hidden))


def build_market_section(
    category_cn: str,
    item_classes: str | list[str],
    bands: dict[str, list[str]],
    hidden: list[str],
    header_prefix: str = "通货 - 赛季通货*",
) -> str:
    blocks = [
        market_rule(
            category_cn,
            band,
            bands[band],
            item_classes,
            header_prefix=header_prefix,
        )
        for band in ("1D以上", "100E-1D", "50E-99E", "20E-49E")
        if bands[band]
    ]
    if hidden:
        blocks.append(
            market_hide_rule(
                category_cn,
                hidden,
                item_classes,
                header_prefix=header_prefix,
            )
        )
    return "".join(blocks)


def gem_market_rule(
    category_cn: str, band: str, names: list[str], sound: str
) -> str:
    styles = {
        "1D以上": ("255 255 255", "205 0 0 230", "255 0 0", "0 Red Kite", "Red"),
        "100E-1D": ("245 16 16", "255 255 255", "255 0 0", "1 Red Kite", "Red"),
        "50E-99E": ("0 47 167", "255 255 255", "0 47 167", "1 Blue Kite", "Blue"),
        "20E-49E": ("20 240 240", "0 79 75 255", "20 240 240", "2 Orange Kite", "Orange"),
    }
    text_color, background, border, icon, effect = styles[band]
    base_types = " ".join(q(name) for name in sorted(names, key=str.casefold))
    lines = [
        f"Show # 技能石 - {category_cn} - 国际服赛季末市场 {band}★",
        class_line(["Skill Gems", "Support Gems"]),
        f"    BaseType == {base_types}",
        f"    SetTextColor {text_color}",
        f"    SetBackgroundColor {background}",
        f"    SetBorderColor {border}",
        "    SetFontSize 45",
        f"    MinimapIcon {icon}",
        f"    PlayEffect {effect}",
        f'    CustomAlertSound "音效\\{sound}" 300',
        "    DisableDropSound",
        "",
        "",
    ]
    return "\r\n".join(lines)


def build_gem_market_section(
    category_cn: str,
    bands: dict[str, list[str]],
    hidden: list[str],
    sounds: dict[str, str],
) -> str:
    blocks = [
        gem_market_rule(category_cn, band, bands[band], sounds[band])
        for band in ("1D以上", "100E-1D", "50E-99E", "20E-49E")
        if bands[band]
    ]
    if hidden:
        blocks.append(
            market_hide_rule(
                category_cn,
                hidden,
                ["Skill Gems", "Support Gems"],
                header_prefix="技能石",
            )
        )
    return "".join(blocks)


def main() -> None:
    raw = SOURCE.read_bytes()
    if b"\r\n" not in raw or b"\n" in raw.replace(b"\r\n", b""):
        raise RuntimeError("Source is not consistently CRLF encoded")
    text = raw.decode("utf-8")
    parts = re.split(r"(?m)(?=^(?:Show|Hide) # )", text)

    currency_market = fetch_market("currency")
    divine_price_e = currency_market.get(
        "Divine Orb", (DIVINE_PRICE_E_FALLBACK, 0, 0)
    )[0]
    rune_market = fetch_market("runes")
    essence_market = fetch_market("essences")
    uncut_gem_market = fetch_market("uncut-gems")
    catalyst_market = {
        name: value
        for name, value in fetch_divine_market(
            "catalysts", divine_price_e
        ).items()
        if name.endswith("Catalyst")
    }
    soul_core_market = {
        name: value
        for name, value in fetch_divine_market(
            "soul-cores", divine_price_e
        ).items()
        if "Soul Core" in name
    }
    lineage_market = fetch_divine_market("lineage-gems", divine_price_e)

    rune_show_headers = {
        "通用超高价值符文": "1D以上",
        "通用高价值符文": "100E-1D",
        "通用中价值符文": "50E-99E",
        "通用中低价值符文": "20E-49E",
    }
    essence_show_headers = {
        "50E精华": "50E-99E",
        "四个特殊精华": "100E-1D",
        "完美精华有价值": "20E-49E",
    }

    rune_current: set[str] = set()
    rune_missing: dict[str, set[str]] = {key: set() for key in rune_show_headers.values()}
    essence_current: set[str] = set()
    catalyst_current: set[str] = set()
    soul_core_current: set[str] = set()
    lineage_current: set[str] = set()
    essence_missing: dict[str, set[str]] = {
        "1D以上": set(),
        "100E-1D": set(),
        "50E-99E": set(),
        "20E-49E": set(),
    }

    for block in parts:
        first = header(block)
        if first.startswith("Show # 通货 - 赛季通货* - 符文 - "):
            for marker, band in rune_show_headers.items():
                if marker in first:
                    names = set(extract_base_types(block))
                    rune_current.update(names)
                    rune_missing[band].update(names)
        if first.startswith("Show # 通货 - 赛季通货* - 精华 - "):
            if "10E以上" in first:
                # Explicitly below the chosen threshold: market data may still promote a name.
                essence_current.update(extract_base_types(block))
                continue
            for marker, band in essence_show_headers.items():
                if marker in first:
                    names = set(extract_base_types(block))
                    essence_current.update(names)
                    essence_missing[band].update(names)
        if first.startswith("Show # 通货 - 赛季通货* - 催化剂 - "):
            catalyst_current.update(extract_base_types(block))
        if first.startswith("Show # 通货 - 赛季通货* - 灵核 - "):
            soul_core_current.update(extract_base_types(block))
        if (
            first.startswith("Show # 技能石 - 血脉辅助宝石 - ")
            and " - 全部" not in first
        ):
            lineage_current.update(extract_base_types(block))

    rune_bands, rune_hidden = split_market_rules(
        rune_market, rune_current, rune_missing, divine_price_e
    )
    essence_bands, essence_hidden = split_market_rules(
        essence_market,
        essence_current,
        essence_missing,
        divine_price_e,
        corroborated={"Essence of Abrasion"},
    )
    catalyst_bands, catalyst_hidden = split_market_rules(
        catalyst_market,
        catalyst_current,
        {},
        divine_price_e,
        corroborated={"Refined Sibilant Catalyst", "Refined Tul's Catalyst"},
        minimum_liquidity=MIN_EXTERNAL_VOLUME,
    )
    soul_core_bands, soul_core_hidden = split_market_rules(
        soul_core_market,
        soul_core_current,
        {},
        divine_price_e,
        corroborated={
            "Guatelitzi's Soul Core of Endurance",
            "Opiloti's Soul Core of Assault",
            "Soul Core of Jiquani",
            "Soul Core of Zalatl",
            "Tzamoto's Soul Core of Ferocity",
        },
        minimum_liquidity=MIN_EXTERNAL_VOLUME,
    )
    lineage_bands, lineage_hidden = split_market_rules(
        lineage_market,
        lineage_current,
        {},
        divine_price_e,
        minimum_liquidity=MIN_EXTERNAL_VOLUME,
    )
    uncut_gem_bands, uncut_gem_hidden = split_market_rules(
        uncut_gem_market,
        {
            "Uncut Skill Gem (Level 20)",
            "Uncut Spirit Gem (Level 17)",
            "Uncut Spirit Gem (Level 18)",
            "Uncut Spirit Gem (Level 19)",
            "Uncut Spirit Gem (Level 20)",
        },
        {},
        divine_price_e,
        corroborated={
            "Uncut Skill Gem (Level 1)",
            "Uncut Skill Gem (Level 7)",
            "Uncut Spirit Gem (Level 14)",
            "Uncut Spirit Gem (Level 15)",
        },
        minimum_liquidity=MIN_LISTED_QUANTITY,
    )
    rune_section = build_market_section("符文", "Augment", rune_bands, rune_hidden)
    essence_section = build_market_section(
        "精华", "Stackable Currency", essence_bands, essence_hidden
    )
    catalyst_section = build_market_section(
        "催化剂", "Stackable Currency", catalyst_bands, catalyst_hidden
    )
    soul_core_section = build_market_section(
        "灵核", "Augment", soul_core_bands, soul_core_hidden
    )
    lineage_section = build_gem_market_section(
        "血脉辅助宝石",
        lineage_bands,
        lineage_hidden,
        {
            "1D以上": "CYGG.mp3",
            "100E-1D": "heiheihei.mp3",
            "50E-99E": "hjmld.mp3",
            "20E-49E": "MBWDD.mp3",
        },
    )
    uncut_gem_section = build_gem_market_section(
        "未切割宝石",
        uncut_gem_bands,
        uncut_gem_hidden,
        {
            "1D以上": "CYGG.mp3",
            "100E-1D": "hjmld2.mp3",
            "50E-99E": "精神宝石.mp3",
            "20E-49E": "技能宝石.mp3",
        },
    )

    currency_stack_minimums: dict[str, int] = {}
    currency_below_threshold: set[str] = set()
    for name, (price, _quantity, stack_size) in currency_market.items():
        if name == "Exalted Orb" or price >= MIN_VALUE_E:
            continue
        currency_below_threshold.add(name)
        if price > 0 and stack_size > 0:
            minimum = math.ceil(MIN_VALUE_E / price)
            if minimum <= stack_size:
                currency_stack_minimums[name] = minimum

    exact_hide_headers = {
        "Show # 通货 - 赛季通货* - 合金 - 低价值合金★",
        "Show # 通货 - 赛季通货* - 液化情感 - 10E以上",
        "Show # 通货 - 赛季通货* - 液化情感 - 1E以上★",
        "Show # 通货 - 赛季通货* - 催化剂 - 10E★",
        "Show # 通货 - 赛季通货* - 催化剂 - 10E以上★",
        "Show # 通货 - 赛季通货* - 雕像 - 10E价值雕像",
        "Show # 通货 - 赛季通货* - 灵核 - 10E★",
        "Show # 通货 - 赛季通货* - 0.5新增幅 - 全部",
        "Show # 通货 - 基础通货* - 常规通货 - 机会石",
        "Show # 通货 - 基础通货* - 常规通货 - 高级崇高石",
        "Show # 通货 - 基础通货* - 常规通货 - 完美蜕变石",
        "Show # 地图碎片 - 剧情碎片 - 低价值1",
        "Show # 地图碎片 - 宝库钥匙 - 10E★",
        "Show # 地图碎片 - 宝库钥匙 - 1E-5E的",
        "Show # 技能石 - 血脉辅助宝石 - 全部",
        "Show # 传奇装备 - 唯一确定传奇 - 10E以上",
        "Show # 传奇装备 - 有价值基底(排序分类) - 一般凸显的暗金装备",
        "Show # 传奇装备 - 基础设置 - 已经腐化的传奇★",
        "Show # 装备 - 卓越装备 - 高品质 - 自定义品质二级基底",
        "Show # 装备 - 卓越装备 - 高品质 - 全部基底",
        "Show # 装备 - 卓越装备 - 多孔 - 3孔二级基底",
        "Show # 装备 - 卓越装备 - 多孔 - 3孔全部基底",
        "Show # 装备 - 卓越装备 - 多孔 - 2孔一级基底",
        "Show # 装备 - 卓越装备 - 多孔 - 2孔二级基底",
        "Show # 装备 - 卓越装备 - 多孔 - 2孔全部基底",
        "Show # 装备 - 带孔装备 - 3孔",
    }

    output_parts: list[str] = []
    inserted_runes = False
    inserted_essences = False
    inserted_catalysts = False
    inserted_soul_cores = False
    inserted_lineage = False
    inserted_uncut_gems = False
    inserted_extra_sockets = False
    inserted_currency_stacks: set[str] = set()
    converted = 0
    for block in parts:
        first = header(block)
        if (
            not inserted_essences
            and first.startswith("Show # 通货 - 赛季通货* - 精华 - ")
        ):
            output_parts.append(essence_section)
            inserted_essences = True
        if (
            not inserted_runes
            and first.startswith("Show # 通货 - 赛季通货* - 符文 - ")
        ):
            output_parts.append(rune_section)
            inserted_runes = True
        if (
            not inserted_catalysts
            and first.startswith("Show # 通货 - 赛季通货* - 催化剂 - ")
        ):
            output_parts.append(catalyst_section)
            inserted_catalysts = True
        if (
            not inserted_soul_cores
            and first.startswith("Show # 通货 - 赛季通货* - 灵核 - ")
        ):
            output_parts.append(soul_core_section)
            inserted_soul_cores = True
        if (
            not inserted_lineage
            and first.startswith("Show # 技能石 - 血脉辅助宝石 - ")
        ):
            output_parts.append(lineage_section)
            inserted_lineage = True
        if (
            not inserted_uncut_gems
            and first.startswith(
                (
                    "Show # 技能石 - 技能宝石 - ",
                    "Show # 技能石 - 辅助宝石 - ",
                    "Show # 技能石 - 精神宝石 - ",
                )
            )
        ):
            output_parts.append(uncut_gem_section)
            inserted_uncut_gems = True
        if not inserted_extra_sockets and first.startswith("Show # 装备 - "):
            output_parts.append(extra_socket_section())
            inserted_extra_sockets = True

        base_types = extract_base_types(block)
        currency_name = base_types[0] if len(base_types) == 1 else None
        currency_forced_hide = False
        if (
            currency_name
            and "# 通货 - 基础通货* - " in first
            and currency_name in currency_below_threshold
        ):
            minimum = currency_stack_minimums.get(currency_name)
            if minimum and currency_name not in inserted_currency_stacks:
                output_parts.append(currency_stack_clone(block, currency_name, minimum))
                inserted_currency_stacks.add(currency_name)
            currency_forced_hide = first.startswith("Show # ")

        if currency_forced_hide:
            block = hide_block(block, "单次掉落低于20E")
            converted += 1
        elif first == "Show # 通货 - 赛季通货* - 惊悸迷雾 - 拟像裂片多堆叠":
            block = set_stack_size(block, math.ceil(20 / 3.25), "价值达到20E（7个以上）")
        elif first == "Show # 通货 - 赛季通货* - 惊悸迷雾 - 拟像裂片":
            block = hide_block(block, "不足20E")
            converted += 1
        elif first == "Show # 通货 - 赛季通货* - 裂隙 - 裂隙碎片多堆叠":
            block = set_stack_size(block, math.ceil(20 / 0.3909), "价值达到20E（52个以上）")
        elif first == "Show # 通货 - 赛季通货* - 裂隙 - 裂隙碎片":
            block = hide_block(block, "不足20E")
            converted += 1
        elif first == "Show # 通货 - 基础通货* - 常规通货 - 崇高石*2★":
            block = set_stack_size(block, 20, "崇高石20个以上★")
        elif first.startswith("Show # 通货 - 赛季通货* - 精华 - "):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif (
            first.startswith("Show # 通货 - 赛季通货* - 符文 - ")
            and "遗产符文" not in first
        ):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif first.startswith("Show # 通货 - 赛季通货* - 催化剂 - "):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif first.startswith("Show # 通货 - 赛季通货* - 灵核 - "):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif first.startswith("Show # 技能石 - 血脉辅助宝石 - "):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif first.startswith(
            (
                "Show # 技能石 - 技能宝石 - ",
                "Show # 技能石 - 辅助宝石 - ",
                "Show # 技能石 - 精神宝石 - ",
            )
        ):
            block = hide_block(block, "由前置20E市场分档接管")
            converted += 1
        elif first in {
            "Show # 珠宝 - 失落珠宝* - 腐化失落珠宝 - 纯腐化魔法",
            "Show # 珠宝 - 常规珠宝* - 腐化常规珠宝 - 纯腐化魔法",
        }:
            block = set_rarity(block, "Magic")
        elif first in exact_hide_headers:
            block = hide_block(block, "赛季末低于20E")
            converted += 1
        elif first.startswith("Show # 装备 - "):
            block = hide_block(block, "非额外孔普通装备")
            converted += 1

        output_parts.append(dedupe_exact_lines(block))

    if not all(
        (
            inserted_runes,
            inserted_essences,
            inserted_catalysts,
            inserted_soul_cores,
            inserted_lineage,
            inserted_uncut_gems,
            inserted_extra_sockets,
        )
    ):
        raise RuntimeError("Failed to insert generated market or socket sections")

    result = "".join(output_parts).replace('""', '" "')
    if "\n" in result.replace("\r\n", ""):
        raise RuntimeError("Transformation introduced non-CRLF newlines")
    encoded = result.encode("utf-8")

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(encoded)
    shutil.copyfile(OUTPUT, DELIVERY_OUTPUT)

    print(f"source_bytes={len(raw)}")
    print(f"output_bytes={len(encoded)}")
    print(f"converted_show_to_hide={converted}")
    print(f"divine_price_e={divine_price_e}")
    print(f"currency_stack_rules={len(inserted_currency_stacks)}")
    print(f"rune_market_rows={len(rune_market)}")
    print(f"essence_market_rows={len(essence_market)}")
    for band, names in rune_bands.items():
        print(f"runes_{band}={len(names)}")
    print(f"runes_hidden={len(rune_hidden)}")
    for band, names in essence_bands.items():
        print(f"essences_{band}={len(names)}")
    print(f"essences_hidden={len(essence_hidden)}")
    for label, bands, hidden in (
        ("catalysts", catalyst_bands, catalyst_hidden),
        ("soul_cores", soul_core_bands, soul_core_hidden),
        ("lineage", lineage_bands, lineage_hidden),
        ("uncut_gems", uncut_gem_bands, uncut_gem_hidden),
    ):
        for band, names in bands.items():
            print(f"{label}_{band}={len(names)}")
        print(f"{label}_hidden={len(hidden)}")
    print(f"output={OUTPUT}")
    print(f"delivery_output={DELIVERY_OUTPUT}")


if __name__ == "__main__":
    main()
