import json
import subprocess
import unittest
from pathlib import Path
import sys
import os

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

def _bits_msb(x: int, w: int) -> str:
    return format(x & ((1 << w) - 1), f"0{w}b")

def _to_signed(x: int, w: int) -> int:
    mask = (1 << w) - 1
    x &= mask
    sign = 1 << (w - 1)
    return x - (1 << w) if (x & sign) else x

class TestEval(unittest.TestCase):
    def test_case1_ops_s_det(self):
        case = "case1_ops_s_det"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        a = int(assume["signals"]["a"]["bits_msb"], 2)
        b = int(assume["signals"]["b"]["bits_msb"], 2)
        sh = int(assume["signals"]["shamt"]["bits_msb"], 2)
        sel = int(assume["signals"]["sel"]["bits_msb"], 2)

        # 位运算
        self.assertEqual(ev["signals"]["y_and"]["bits_msb"], _bits_msb(a & b, 8))
        self.assertEqual(ev["signals"]["y_or"]["bits_msb"], _bits_msb(a | b, 8))
        self.assertEqual(ev["signals"]["y_xor"]["bits_msb"], _bits_msb(a ^ b, 8))
        self.assertEqual(ev["signals"]["y_not"]["bits_msb"], _bits_msb((~a) & 0xFF, 8))

        # mux
        mux = b if sel == 1 else a
        self.assertEqual(ev["signals"]["y_mux"]["bits_msb"], _bits_msb(mux, 8))

        # add sub
        self.assertEqual(ev["signals"]["y_add"]["bits_msb"], _bits_msb(a + b, 8))
        self.assertEqual(ev["signals"]["y_sub"]["bits_msb"], _bits_msb(a - b, 8))

        # slice a[5:2]
        sl = (a >> 2) & 0xF
        self.assertEqual(ev["signals"]["y_slice"]["bits_msb"], _bits_msb(sl, 4))

        # concat {a,b}
        cc = ((a & 0xFF) << 8) | (b & 0xFF)
        self.assertEqual(ev["signals"]["y_concat"]["bits_msb"], _bits_msb(cc, 16))

        # shifts
        self.assertEqual(ev["signals"]["y_shl"]["bits_msb"], _bits_msb(a << sh, 8))
        self.assertEqual(ev["signals"]["y_shr"]["bits_msb"], _bits_msb(a >> sh, 8))

        a_s = _to_signed(a, 8)
        ashr = (a_s >> sh) & 0xFF
        self.assertEqual(ev["signals"]["y_ashr"]["bits_msb"], _bits_msb(ashr, 8))

        b_s = _to_signed(b, 8)
        self.assertEqual(ev["signals"]["y_eq"]["bits_msb"], "1" if a == b else "0")
        self.assertEqual(ev["signals"]["y_lt"]["bits_msb"], "1" if a_s < b_s else "0")
        self.assertEqual(ev["signals"]["y_le"]["bits_msb"], "1" if a_s <= b_s else "0")
        self.assertEqual(ev["signals"]["y_gt"]["bits_msb"], "1" if a_s > b_s else "0")
        self.assertEqual(ev["signals"]["y_ge"]["bits_msb"], "1" if a_s >= b_s else "0")

    def test_case4_ops_u_det(self):
        case = "case4_ops_u_det"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        a = int(assume["signals"]["a"]["bits_msb"], 2)
        b = int(assume["signals"]["b"]["bits_msb"], 2)
        sh = int(assume["signals"]["shamt"]["bits_msb"], 2)
        sel = int(assume["signals"]["sel"]["bits_msb"], 2)

        self.assertEqual(ev["signals"]["y_shr"]["bits_msb"], _bits_msb(a >> sh, 8))
        self.assertEqual(ev["signals"]["y_eq"]["bits_msb"], "1" if a == b else "0")
        self.assertEqual(ev["signals"]["y_lt"]["bits_msb"], "1" if a < b else "0")
        self.assertEqual(ev["signals"]["y_ge"]["bits_msb"], "1" if a >= b else "0")

        mux = b if sel == 1 else a
        self.assertEqual(ev["signals"]["y_mux"]["bits_msb"], _bits_msb(mux, 8))

    def test_case5_cmp_must(self):
        case = "case5_cmp_must"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")

        self.assertEqual(ev["signals"]["y_s_lt"]["bits_msb"], "1")
        self.assertEqual(ev["signals"]["y_s_ge"]["bits_msb"], "0")
        self.assertEqual(ev["signals"]["y_u_lt"]["bits_msb"], "0")
        self.assertEqual(ev["signals"]["y_u_ge"]["bits_msb"], "1")


if __name__ == "__main__":
    unittest.main()