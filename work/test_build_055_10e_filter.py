#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "work" / "build_055_10e_filter.py"
OUTPUT = ROOT / "outputs" / "[08]0.5.5赛季10E-T15+ 天枢过滤器-POE2-曼波语音.filter"
SNAPSHOT = ROOT / "work" / "forbidden_rites_0.5.5_10e_market_snapshot.json"
PROJECT = Path("/Users/christina/self/poe")

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
        self.assertEqual(
            self.snapshot["rate_by_category"]["stash/UniqueArmours"], 194.2
        )
        self.assertEqual(self.snapshot["max_stack_size"]["Exalted Orb"], 20)
        exalted = self.snapshot["classification_state"]["exchange"]["Currency"][
            "Exalted Orb"
        ]
        self.assertEqual(exalted["state"], "stack:10")

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

    def test_bad_armour_cross_rates_are_not_definite_value(self) -> None:
        states = self.snapshot["classification_state"]["unique"]["gear"]
        for base in (
            "Runemastered Riveted Mitts",
            "Runemastered Velvet Cap",
            "Runemastered Heraldric Tower Shield",
            "Runemastered Trimmed Greaves",
            "Runemastered Felt Cap",
        ):
            self.assertEqual(states[base]["state"], "hidden", base)

    def test_shared_bases_and_low_inventory_use_cautious_tier(self) -> None:
        states = self.snapshot["classification_state"]["unique"]["gear"]
        for base in ("Silk Robe", "Utility Belt", "Heavy Belt", "Prismatic Ring"):
            self.assertEqual(states[base]["state"], "uncertain", base)
        self.assertIn("Show # 0.5.5传奇市场 - 可能猎首（重革腰带同底材）", self.text)
        self.assertIn("可能高价（同底材或低库存）", self.text)

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
