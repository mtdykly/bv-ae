import json
import subprocess
import unittest
from pathlib import Path
import sys
from itertools import product

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

def _bits_msb_to_lsb_list(bits_msb: str):
    return list(reversed(bits_msb))

def _signed_int_from_bits(bits_lsb, signed: bool) -> int:
    w = len(bits_lsb)
    val = 0
    for i, b in enumerate(bits_lsb):
        if b:
            val |= (1 << i)
    if not signed:
        return val
    sign = 1 << (w - 1)
    return val - (1 << w) if (val & sign) else val

def _ext_bits(bits_lsb, new_w: int, signed: bool):
    w = len(bits_lsb)
    if w >= new_w:
        return bits_lsb[:new_w]
    pad = bits_lsb[-1] if (signed and w > 0) else 0
    return bits_lsb + [pad] * (new_w - w)

def _eval_concrete(ir: dict, in_env: dict) -> dict:
    nodes = ir.get("nodes", [])
    signals = ir.get("signals", [])
    node_map = {n["nid"]: n for n in nodes if not n.get("is_view", False)}

    driver_of = {}
    for n in node_map.values():
        for br in (n.get("ports", {}) or {}).get("Y", []) or []:
            if br.get("kind") == "wire":
                driver_of[int(br["id"])] = n["nid"]

    deps = {nid: set() for nid in node_map.keys()}
    for n in node_map.values():
        nid = n["nid"]
        ports = n.get("ports", {}) or {}
        for pn, bl in ports.items():
            if pn == "Y":
                continue
            for br in bl or []:
                if br.get("kind") != "wire":
                    continue
                dn = driver_of.get(int(br["id"]))
                if dn and dn != nid:
                    deps[nid].add(dn)

    ready = [nid for nid, ds in deps.items() if not ds]
    order = []
    while ready:
        x = ready.pop()
        order.append(x)
        for nid, ds in deps.items():
            if x in ds:
                ds.remove(x)
                if not ds:
                    ready.append(nid)

    env = dict(in_env)

    def read_bits(bitrefs):
        out = []
        for br in bitrefs:
            if br.get("kind") == "const":
                out.append(1 if br.get("val") == "1" else 0)
            else:
                out.append(env.get(int(br["id"]), 0))
        return out

    def write_bits(bitrefs, bits_lsb):
        for br, bv in zip(bitrefs, bits_lsb):
            if br.get("kind") == "wire":
                env[int(br["id"])] = int(bv)

    for nid in order:
        n = node_map[nid]
        op = n.get("op")
        ports = n.get("ports", {}) or {}
        p = n.get("params", {}) or {}
        y = ports.get("Y", []) or []
        y_w = len(y)

        def sA(): return bool(p.get("A_SIGNED", 0) == 1)
        def sB(): return bool(p.get("B_SIGNED", 0) == 1)

        if op in ("AND", "OR", "XOR", "ADD", "SUB", "EQ", "LT", "LE", "GT", "GE", "SHL", "SHR", "ASHR"):
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
        if op == "NOT":
            A = read_bits(ports.get("A", []) or [])

        if op == "AND":
            w = max(len(A), len(B), y_w)
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            out = [(A2[i] & B2[i]) for i in range(y_w)]
            write_bits(y, out)
        elif op == "OR":
            w = max(len(A), len(B), y_w)
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            out = [(A2[i] | B2[i]) for i in range(y_w)]
            write_bits(y, out)
        elif op == "XOR":
            w = max(len(A), len(B), y_w)
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            out = [(A2[i] ^ B2[i]) for i in range(y_w)]
            write_bits(y, out)
        elif op == "NOT":
            out = [1 - A[i] for i in range(y_w)]
            write_bits(y, out)
        elif op == "MUX":
            S = read_bits(ports.get("S", []) or [])
            sel = S[0] if S else 0
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            w = max(len(A), len(B), y_w)
            A2 = _ext_bits(A, w, False)
            B2 = _ext_bits(B, w, False)
            out = [ (B2[i] if sel else A2[i]) for i in range(y_w) ]
            write_bits(y, out)
        elif op == "EXTRACT":
            A = read_bits(ports.get("A", []) or [])
            off = int(p.get("OFFSET", 0))
            out = A[off: off + y_w]
            out = out + [0] * (y_w - len(out))
            write_bits(y, out[:y_w])
        elif op == "CONCAT":
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            out = (A + B)[:y_w]
            out = out + [0] * (y_w - len(out))
            write_bits(y, out[:y_w])
        elif op in ("SHL", "SHR", "ASHR"):
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            sh = 0
            for i, b in enumerate(B):
                sh |= (b << i)
            A2 = _ext_bits(A, y_w, sA())
            if op == "SHL":
                out = [0] * y_w
                for i in range(y_w):
                    src = i - sh
                    out[i] = A2[src] if 0 <= src < y_w else 0
            elif op == "SHR":
                out = [0] * y_w
                for i in range(y_w):
                    src = i + sh
                    out[i] = A2[src] if 0 <= src < y_w else 0
            else:
                # ASHR: A_SIGNED==1 才补符号位，否则补 0
                fill = A2[-1] if sA() and y_w > 0 else 0
                out = [0] * y_w
                for i in range(y_w):
                    src = i + sh
                    out[i] = A2[src] if 0 <= src < y_w else fill
            write_bits(y, out)
        elif op in ("ADD", "SUB"):
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            w = max(len(A), len(B), y_w)
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            aval = _signed_int_from_bits(A2, False)  # 用无符号做模运算
            bval = _signed_int_from_bits(B2, False)
            mask = (1 << y_w) - 1 if y_w > 0 else 0
            res = (aval + bval) if op == "ADD" else (aval - bval)
            res &= mask
            out = [(res >> i) & 1 for i in range(y_w)]
            write_bits(y, out)
        elif op == "EQ":
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            w = max(len(A), len(B))
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            out = [1 if A2 == B2 else 0]
            write_bits(y, out)
        elif op in ("LT", "LE", "GT", "GE"):
            A = read_bits(ports.get("A", []) or [])
            B = read_bits(ports.get("B", []) or [])
            w = max(len(A), len(B))
            A2 = _ext_bits(A, w, sA())
            B2 = _ext_bits(B, w, sB())
            signed_cmp = sA() and sB()
            aval = _signed_int_from_bits(A2, signed_cmp)
            bval = _signed_int_from_bits(B2, signed_cmp)
            if op == "LT": outv = int(aval < bval)
            elif op == "LE": outv = int(aval <= bval)
            elif op == "GT": outv = int(aval > bval)
            else: outv = int(aval >= bval)
            write_bits(y, [outv])

    outs = {}
    for s in signals:
        if s.get("kind") != "output":
            continue
        bits = s.get("bits", []) or []
        outs[s["name"]] = [env.get(int(br["id"]), 0) for br in bits if br.get("kind") == "wire"]
    return outs


class TestSoundness(unittest.TestCase):
    def test_case_soundness(self):
        case = "case_ops_s_sound"
        ir = _read_json(_run_case(case))
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")
        ev = eval_ir_bv3(ir, assume=assume)
        (out_dir := (ROOT / "out" / case)).mkdir(parents=True, exist_ok=True)
        (ROOT / "out" / case / "eval.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
        sig_map = {s["name"]: s for s in ir.get("signals", []) if s.get("kind") == "input"}
        base_env = {}
        unknown_bids = []

        for name, spec in assume["signals"].items():
            bits_msb = spec["bits_msb"]
            bits_lsb = _bits_msb_to_lsb_list(bits_msb)
            s = sig_map[name]
            for i, ch in enumerate(bits_lsb):
                br = s["bits"][i]
                bid = int(br["id"])
                if ch == "0":
                    base_env[bid] = 0
                elif ch == "1":
                    base_env[bid] = 1
                else:
                    unknown_bids.append(bid)

        abs_bits = {}
        for s in ir.get("signals", []):
            if s.get("kind") != "output":
                continue
            name = s["name"]
            abs_bits[name] = _bits_msb_to_lsb_list(ev["signals"][name]["bits_msb"])

        k = len(unknown_bids)
        self.assertLessEqual(k, 12, f"too many X bits for exhaustive soundness: {k}")

        for assign in product([0, 1], repeat=k):
            env = dict(base_env)
            for bid, val in zip(unknown_bids, assign):
                env[bid] = val

            conc_out = _eval_concrete(ir, env)

            for oname, bits_lsb in conc_out.items():
                ab = abs_bits[oname]
                for i, bv in enumerate(bits_lsb):
                    if i >= len(ab):
                        continue
                    if ab[i] == "0":
                        self.assertEqual(bv, 0, f"unsound at {oname}[{i}] expected 0")
                    elif ab[i] == "1":
                        self.assertEqual(bv, 1, f"unsound at {oname}[{i}] expected 1")
                    else:
                        pass


if __name__ == "__main__":
    unittest.main()