import json
import os
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from src.ae.eval import eval_ir_bv3
from src.ae.exact_eval import eval_ir_exact_enum, compare_exact_vs_abstract
from _cases import CASES

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def _run_yosys(case: str) -> Path:
    bat = ROOT / "tools" / "run_yosys.bat"
    if not bat.exists():
        raise FileNotFoundError(f"missing: {bat}")

    p = subprocess.run([str(bat), case], cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(
            f"run_yosys failed for {case}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    ir_path = ROOT / "out" / case / "ir.json"
    if not ir_path.exists():
        raise AssertionError(f"ir.json not found after yosys run: {ir_path}")
    return ir_path

@unittest.skipUnless(os.name == "nt", "requires Windows .bat runner (tools/run_yosys.bat)")
class TestExactVsAbstract(unittest.TestCase):
    def test_soundness_for_10_cases(self):
        for case in CASES:
            with self.subTest(case=case):
                ir_path = _run_yosys(case)
                ir = _read_json(ir_path)
                assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")

                abstract = eval_ir_bv3(ir, assume)
                exact = eval_ir_exact_enum(ir, assume, max_enum=1_000_000, signals_mode="outputs")

                rep = compare_exact_vs_abstract(exact, abstract)
                if not rep["ok"]:
                    preview = rep["issues"][:5]
                    self.fail(f"{case}: soundness check failed. issues={preview}")