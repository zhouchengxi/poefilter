#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path("/Users/christina/self/poe")
SCRIPT = ROOT / "work" / "build_055_10e_filter.py"
OUTPUT_NAME = "[08]0.5.5赛季10E-T15+ 天枢过滤器-POE2-曼波语音.filter"
OUTPUT = (PROJECT if ROOT == PROJECT else ROOT / "outputs") / OUTPUT_NAME
SNAPSHOT = ROOT / "work" / "forbidden_rites_0.5.5_10e_market_snapshot.json"

spec = importlib.util.spec_from_file_location("build_055_10e_filter", SCRIPT)
assert spec and spec.loader
filter_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filter_builder)


class PricingPolicyTests(unittest.TestCase):
    def test_category_specific_exalted_rate_wins(self) -> None:
        self.assertEqual(
            filter_builder.exalted_factor(
                {"primary": "divine", "rates": {"exalted": 194.2}}, 265.9
            ),
            194.2,
        )

    def test_hysteresis_boundaries(self) -> None:
        self.assertFalse(filter_builder.stable_single(7.9, True))
        self.assertTrue(filter_builder.stable_single(12.1, False))
        self.assertTrue(filter_builder.stable_single(10.0, True))
        self.assertFalse(filter_builder.stable_single(10.0, False))
        self.assertTrue(filter_builder.stable_single(10.0, None))

    def test_exchange_confidence_formula(self) -> None:
        self.assertFalse(filter_builder.exchange_is_trusted("Example", 30.0, 149.9))
        self.assertTrue(filter_builder.exchange_is_trusted("Example", 30.0, 150.0))
        self.assertTrue(filter_builder.exchange_is_trusted("Example", 2.0, 100.0))


class GeneratedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = OUTPUT.read_bytes()
        cls.text = cls.raw.decode("utf-8")
        cls.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.blocks = re.split(r"(?m)(?=^(?:Show|Hide) # )", cls.text)

    def blocks_containing(self, needle: str) -> list[str]:
        return [block for block in self.blocks if needle in block]

    def test_encoding_and_synced_output(self) -> None:
        self.assertIn(b"\r\n", self.raw)
        self.assertNotIn(b"\n", self.raw.replace(b"\r\n", b""))
        self.assertEqual(self.raw, (PROJECT / OUTPUT.name).read_bytes())

    def test_rate_and_stack_metadata(self) -> None:
        self.assertGreater(
            self.snapshot["rate_by_category"]["stash/UniqueArmours"], 0
        )
        self.assertIn("exchange/Currency", self.snapshot["rate_by_category"])
        self.assertEqual(self.snapshot["max_stack_size"]["Exalted Orb"], 20)
        exalted = self.snapshot["classification_state"]["exchange"]["Currency"][
            "Exalted Orb"
        ]
        self.assertEqual(exalted["state"], "stack:10")
        self.assertEqual(self.snapshot["classification_schema_version"], 4)
        self.assertEqual(
            self.snapshot["priority_alerts"]["threshold_divine"],
            filter_builder.TEN_DIVINE_MULTIPLIER,
        )
        self.assertAlmostEqual(
            self.snapshot["priority_alerts"]["threshold_exalted"],
            self.snapshot["divine_price_exalted"]
            * filter_builder.TEN_DIVINE_MULTIPLIER,
            places=5,
        )

    def test_no_impossible_generated_stack_rule(self) -> None:
        states = self.snapshot["classification_state"]["exchange"]
        for category in states.values():
            for name, record in category.items():
                state = record["state"]
                if not state.startswith("stack:"):
                    continue
                required = int(state.split(":", 1)[1])
                self.assertLessEqual(
                    required, self.snapshot["max_stack_size"][name], name
                )
        self.assertNotIn("StackSize >= 803", self.text)
        self.assertNotIn("StackSize >= 905", self.text)

    def test_armour_regressions_follow_current_category_price(self) -> None:
        states = self.snapshot["classification_state"]["unique"]["gear"]
        for base in (
            "Runemastered Riveted Mitts",
            "Runemastered Velvet Cap",
            "Runemastered Heraldric Tower Shield",
            "Runemastered Trimmed Greaves",
            "Runemastered Felt Cap",
        ):
            record = states[base]
            if record["price_e"] < filter_builder.UNIQUE_HIDE_BELOW_E:
                self.assertEqual(record["state"], "hidden", base)
            elif (
                record["price_e"] >= filter_builder.UNIQUE_SHOW_AT_OR_ABOVE_E
                and record["trusted"]
                and len(record["unique_names"]) == 1
            ):
                self.assertEqual(record["state"], "single", base)
            else:
                expected = (
                    "single:hysteresis"
                    if record["last_stable_state"].split(":", 1)[0] == "single"
                    else "hidden"
                )
                self.assertEqual(record["state"], expected, base)

    def test_shared_bases_and_low_inventory_use_cautious_tier(self) -> None:
        states = self.snapshot["classification_state"]["unique"]["gear"]
        for base in ("Silk Robe", "Utility Belt", "Heavy Belt", "Prismatic Ring"):
            self.assertEqual(states[base]["state"], "uncertain", base)
        self.assertIn("Show # 0.5.5传奇市场 - 可能猎首（重革腰带同底材）", self.text)
        self.assertIn("可能高价（大奖同底材或价格分歧）", self.text)

    def test_original_high_value_alerts_are_restored(self) -> None:
        active = self.snapshot["priority_alerts"]["active"]
        representatives = {
            "exchange/Currency/Mirror of Kalandra": "神曼波.mp3",
            "exchange/Currency/Hinekora's Lock": "辛格拉的发辫.mp3",
            "exchange/Abyss/Kurgal's Gaze": "hjmld.mp3",
            "exchange/Expedition/Perfect Flux": "溶剂.mp3",
        }
        for alert_id, sound in representatives.items():
            self.assertIn(alert_id, active)
            self.assertEqual(active[alert_id]["sound"], sound)
            base_type = active[alert_id]["name"]
            matches = [
                block
                for block in self.blocks
                if block.startswith("Show # 0.5.5原版高价值强提醒 -")
                and re.search(
                    rf'(?m)^    BaseType ==[^\r\n]*"{re.escape(base_type)}"',
                    block,
                )
            ]
            self.assertTrue(matches, alert_id)
            self.assertTrue(any(f"音效\\{sound}" in block for block in matches))

    def test_jackpot_shared_bases_use_original_red_star(self) -> None:
        marker = "Show # 0.5.5原版高价值强提醒 - 大奖共享传奇底材"
        block = next(item for item in self.blocks if item.startswith(marker))
        for base_type in filter_builder.FIXED_JACKPOT_SHARED_UNIQUE_BASES:
            self.assertRegex(
                block,
                rf'(?m)^    BaseType ==[^\r\n]*"{re.escape(base_type)}"',
            )
        for expected in (
            "    Rarity Unique",
            "    SetFontSize 45",
            "    MinimapIcon 0 Red Star",
            "    PlayEffect Brown",
            '    CustomAlertSound "音效\\wyyp.mp3" 300',
        ):
            self.assertIn(expected, block)
        self.assertLess(
            self.text.index("Show # 0.5.5传奇市场 - 可能猎首"),
            self.text.index(marker),
        )
        self.assertLess(
            self.text.index("Show # 传奇装备 - 唯一确定传奇 - 卡兰德之触"),
            self.text.index(marker),
        )

    def test_sparse_nonprotected_uniques_stay_hidden(self) -> None:
        states = self.snapshot["classification_state"]["unique"]["gear"]
        for base_type in (
            "Glass Shank",
            "Runemastered Oak Greathammer",
            "Runemastered Knight Armour",
        ):
            if base_type not in states:
                continue
            record = states[base_type]
            if record["credible_listing_count"] < filter_builder.MIN_UNIQUE_LISTINGS:
                self.assertEqual(record["state"], "hidden", base_type)
                first = next(
                    block
                    for block in self.blocks
                    if re.search(
                        rf'(?m)^    BaseType[^\r\n]*"{re.escape(base_type)}"',
                        block,
                    )
                    and "    Rarity Unique" in block
                )
                self.assertTrue(first.startswith("Hide #"), base_type)

    def test_voices_keeps_original_dedicated_alert(self) -> None:
        marker = "Show # 珠宝 - 0.5.5保留 - 天神之音（原版强提醒）"
        block = next(item for item in self.blocks if item.startswith(marker))
        for expected in (
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
        ):
            self.assertIn(expected, block)
        shared_sapphire = next(
            item
            for item in self.blocks
            if item.startswith("Show # 0.5.5传奇市场 - 传奇珠宝")
            and '"Sapphire"' in item
        )
        self.assertLess(self.text.index(block), self.text.index(shared_sapphire))

    def test_only_magic_sapphire_is_shown_before_its_hide(self) -> None:
        marker = "Show # 珠宝 - 0.5.5保留 - 魔法蓝宝石"
        block = next(item for item in self.blocks if item.startswith(marker))
        self.assertIn("    Rarity Magic", block)
        self.assertIn('    Class "Jewels"', block)
        self.assertIn('    BaseType == "Sapphire"', block)
        self.assertNotIn('"Ruby"', block)
        self.assertNotIn('"Emerald"', block)
        self.assertNotIn("CustomAlertSound", block)
        self.assertIn("    DisableDropSound", block)
        self.assertLess(
            self.text.index(marker),
            self.text.index("Hide # 珠宝 - 常规珠宝* - 蓝宝石 - 魔法蓝宝石"),
        )
        self.assertIn("Hide # 珠宝 - 常规珠宝* - 红玉 - 魔法红玉", self.text)
        self.assertIn("Hide # 珠宝 - 常规珠宝* - 翡翠 - 魔法翡翠", self.text)

    def test_map_and_equipment_exceptions_remain(self) -> None:
        self.assertIn(
            'Show # 地图 - 异界地图* - 常规地图 - 7+词缀地图（0.5.5）\r\n'
            '    Corrupted True\r\n'
            '    WaystoneTier >= 14',
            self.text,
        )
        self.assertIn('HasExplicitMod >=7 "a" "e" "i" "o" "u" "y"', self.text)
        self.assertIn("Show # 地图 - 常规异界地图 - T16", self.text)
        self.assertIn("Show # 地图 - 常规异界地图 - T15", self.text)
        self.assertIn("Show # 装备 - 0.5.5唯一保留 - 3孔大件", self.text)
        self.assertIn("Show # 装备 - 0.5.5唯一保留 - 2孔小件", self.text)
        self.assertIn("Show # 全局设置 - 剩余未匹配物品", self.text)

    def test_first_match_order_and_equipment_scope(self) -> None:
        self.assertLess(
            self.text.index("Show # 0.5.5传奇市场 - 可能猎首"),
            self.text.index("Hide # 0.5.5传奇市场 - 普通传奇装备"),
        )
        self.assertLess(
            self.text.index("Show # 装备 - 0.5.5唯一保留"),
            self.text.index("Hide # 装备 -"),
        )
        self.assertLess(
            self.text.index("7+词缀地图（0.5.5）"),
            self.text.index("Show # 地图 - 常规异界地图 - T16"),
        )
        active_equipment = [
            block for block in self.blocks if block.startswith("Show # 装备 -")
        ]
        self.assertEqual(len(active_equipment), 2)

        t15 = next(
            block
            for block in self.blocks
            if block.startswith("Show # 地图 - 常规异界地图 - T15")
        )
        self.assertNotIn("    Rarity ", t15)

    def test_new_event_items_remain_covered(self) -> None:
        self.assertIn('"Sacred Bloom"', self.text)
        self.assertIn('"Expedition Tablet"', self.text)
        self.assertGreaterEqual(len(self.snapshot["exchange"]["SoulCores"]), 17)

    def test_enabled_custom_sounds_exist(self) -> None:
        sounds = set(
            re.findall(r'(?m)^    CustomAlertSound "音效\\([^"\\]+)"', self.text)
        )
        missing = sorted(name for name in sounds if not (PROJECT / "音效" / name).is_file())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
