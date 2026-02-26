import json
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ae.eval import eval_ir_bv3

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def _run_case(case: str) -> Path:
    bat = ROOT / "tools" / "run_yosys.bat"
    # env = os.environ.copy()
    # env["PYTHON_EXE"] = sys.executable
    p = subprocess.run([str(bat), case], cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(f"run_yosys failed for {case}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")

    yosys_json = ROOT / "out" / case / "yosys.json"
    ir_json = ROOT / "out" / case / "ir.json"
    if not yosys_json.exists():
        raise AssertionError(f"yosys.json not generated: {yosys_json}")

    p2 = subprocess.run(
        [sys.executable, "-m", "src.cli", "--yosys_json", str(yosys_json), "--out_ir", str(ir_json)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if p2.returncode != 0:
        raise AssertionError(f"IR conversion failed for {case}\nSTDOUT:\n{p2.stdout}\nSTDERR:\n{p2.stderr}")

    if not ir_json.exists():
        p2 = subprocess.run(
            [sys.executable, "-m", "src.cli", "--yosys_json", str(yosys_json), "--out_ir", str(ir_json)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if p2.returncode != 0:
            raise AssertionError(...)

    return ir_json

class TestPrecision(unittest.TestCase):
    def test_det_is_precise(self):
        case = "case1_ops_s_det"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        for name in ("y_add", "y_sub", "y_shr", "y_ashr", "y_concat"):
            self.assertEqual(ev["signals"][name]["unknown_count"], 0, f"{name} should be fully known")

        for name in ("y_eq", "y_lt", "y_ge"):
            self.assertEqual(ev["signals"][name]["unknown_count"], 0, f"{name} should be fully known")

    def test_partial_shrinks_some_outputs(self):
        case = "case2_ops_s_partial"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        # signed 比较在这个输入构造下应当出现确定值（必真必假）
        self.assertEqual(ev["signals"]["y_lt"]["unknown_count"], 0)
        self.assertEqual(ev["signals"]["y_ge"]["unknown_count"], 0)

        # 至少有一些输出不是全 X（unknown_count < width）
        self.assertLess(ev["signals"]["y_ashr"]["unknown_count"], ev["signals"]["y_ashr"]["width"])

if __name__ == "__main__":
    unittest.main()