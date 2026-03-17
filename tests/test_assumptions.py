import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ae.eval import eval_ir_bv3
from src.ae.exact_eval import compare_exact_vs_abstract, eval_ir_exact_enum


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


class TestAssumptionFormats(unittest.TestCase):
    def test_unsigned_range_matches_equivalent_bits_cube(self):
        ir = _read_json(ROOT / "out" / "case03_ext_trunc" / "ir.json")

        assume_bits = {
            "signals": {
                "u": {"bits_msb": "10XX"},
                "s": {"bits_msb": "1001"},
            }
        }
        assume_range = {
            "signals": {
                "u": {"range": [8, 11]},
                "s": {"bits_msb": "1001"},
            }
        }

        abs_bits = eval_ir_bv3(ir, assume_bits)
        abs_range = eval_ir_bv3(ir, assume_range)
        exact_bits = eval_ir_exact_enum(ir, assume_bits, max_enum=64, signals_mode="outputs")
        exact_range = eval_ir_exact_enum(ir, assume_range, max_enum=64, signals_mode="outputs")

        self.assertEqual(abs_bits["signals"]["y"], abs_range["signals"]["y"])
        self.assertEqual(exact_bits["signals"]["y"], exact_range["signals"]["y"])

    def test_signed_generic_range_uses_signal_signedness(self):
        ir = _read_json(ROOT / "out" / "case03_ext_trunc" / "ir.json")

        assume_bits = {
            "signals": {
                "u": {"bits_msb": "0010"},
                "s": {"bits_msb": "11XX"},
            }
        }
        assume_range = {
            "signals": {
                "u": {"bits_msb": "0010"},
                "s": {"range": [-4, -1]},
            }
        }

        abs_bits = eval_ir_bv3(ir, assume_bits)
        abs_range = eval_ir_bv3(ir, assume_range)
        exact_bits = eval_ir_exact_enum(ir, assume_bits, max_enum=64, signals_mode="outputs")
        exact_range = eval_ir_exact_enum(ir, assume_range, max_enum=64, signals_mode="outputs")

        self.assertEqual(abs_bits["signals"]["y"], abs_range["signals"]["y"])
        self.assertEqual(exact_bits["signals"]["y"], exact_range["signals"]["y"])

    def test_non_power_of_two_range_enumerates_exact_domain(self):
        ir = _read_json(ROOT / "out" / "case03_ext_trunc" / "ir.json")
        assume = {
            "signals": {
                "u": {"range": [1, 3]},
                "s": {"bits_msb": "0000"},
            }
        }

        abstract = eval_ir_bv3(ir, assume)
        exact = eval_ir_exact_enum(ir, assume, max_enum=64, signals_mode="outputs")
        rep = compare_exact_vs_abstract(exact, abstract)

        self.assertEqual(exact["enum_mode"], "value_domains")
        self.assertEqual(exact["enum_count"], 3)
        self.assertTrue(rep["ok"], rep["issues"])
        self.assertEqual(exact["signals"]["y"]["range_unsigned"], [1, 3])


if __name__ == "__main__":
    unittest.main()
