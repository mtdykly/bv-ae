# 对一个组合电路IR做精确枚举
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.ae.assumptions import InputConstraint, parse_input_constraints
from src.ir.ir_types import ModuleIR

def _as_ir_dict(ir: dict | ModuleIR) -> dict:
    return ir.to_dict() if isinstance(ir, ModuleIR) else ir

def _mask(w: int) -> int:
    return (1 << w) - 1 if w > 0 else 0

def _as_signed(v: int, w: int) -> int:
    if w <= 0:
        return 0
    sign = 1 << (w - 1)
    v &= _mask(w)
    return v - (1 << w) if (v & sign) else v

def _resize(v: int, w_from: int, w_to: int, signed: bool) -> int:
    v &= _mask(w_from)
    if w_to <= w_from:
        return v & _mask(w_to)
    if not signed or w_from == 0:
        return v  # 零扩展
    signbit = (v >> (w_from - 1)) & 1
    if signbit == 0:
        return v
    ext_ones = _mask(w_to) ^ _mask(w_from)
    return v | ext_ones

def _build_bit_driver(ir: dict) -> Dict[int, Optional[str]]:
    out: Dict[int, Optional[str]] = {}
    wb = (ir.get("bit_index", {}) or {}).get("wire_bits", {}) or {}
    for bid_str, entry in wb.items():
        drv = (entry or {}).get("driver")
        if drv and drv.get("kind") == "node":
            out[int(bid_str)] = drv.get("nid")
        else:
            out[int(bid_str)] = None
    return out

def _topo_sort_nodes(nodes: List[dict], bit_driver: Dict[int, Optional[str]]) -> List[dict]:
    nid_to_node = {n["nid"]: n for n in nodes if isinstance(n, dict) and n.get("nid")}
    deps: Dict[str, Set[str]] = {nid: set() for nid in nid_to_node.keys()}
    for nid, n in nid_to_node.items():
        ports = n.get("ports", {}) or {}
        for pn, bits in ports.items():
            if pn == "Y":
                continue
            for br in (bits or []):
                if not isinstance(br, dict) or br.get("kind") != "wire":
                    continue
                dnid = bit_driver.get(int(br["id"]))
                if dnid and dnid != nid:
                    deps[nid].add(dnid)
    ready = [nid for nid, ds in deps.items() if not ds]
    order: List[str] = []
    while ready:
        x = ready.pop()
        order.append(x)
        for nid, ds in deps.items():
            if x in ds:
                ds.remove(x)
                if not ds:
                    ready.append(nid)

    if len(order) != len(nid_to_node):
        return nodes
    return [nid_to_node[nid] for nid in order]

# 把IR里的常量x z当额外变量位
def _scan_const_nondet_ids(ir: dict) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    next_id = -1

    def visit_bitrefs(bitrefs: List[dict]) -> None:
        nonlocal next_id
        for br in bitrefs or []:
            if not isinstance(br, dict) or br.get("kind") != "const":
                continue
            v = br.get("val")
            if isinstance(v, str) and v.lower() in ("x", "z"):
                oid = id(br)
                if oid not in mapping:
                    mapping[oid] = next_id
                    next_id -= 1

    for s in ir.get("signals", []) or []:
        if isinstance(s, dict):
            visit_bitrefs(s.get("bits", []) or [])

    for n in ir.get("nodes", []) or []:
        if not isinstance(n, dict):
            continue
        ports = n.get("ports", {}) or {}
        for _pn, bits in ports.items():
            visit_bitrefs(bits or [])
    return mapping

class _EnumDomain:
    def __init__(
        self,
        *,
        name: str,
        size: int,
        signal_bits: Optional[List[dict]] = None,
        constraint: Optional[InputConstraint] = None,
        const_vid: Optional[int] = None,
    ) -> None:
        self.name = name
        self.size = int(size)
        self.signal_bits = signal_bits
        self.constraint = constraint
        self.const_vid = const_vid

    def iter_values(self):
        if self.constraint is not None:
            yield from self.constraint.iter_unsigned_values()
            return
        if self.const_vid is not None:
            yield 0
            yield 1
            return
        raise ValueError(f"invalid enum domain: {self.name}")

    def assign(self, env: Dict[int, int], value: int) -> None:
        if self.constraint is not None:
            for i, br in enumerate(self.signal_bits or []):
                if not isinstance(br, dict) or br.get("kind") != "wire":
                    continue
                env[int(br["id"])] = (value >> i) & 1
            return
        if self.const_vid is not None:
            env[self.const_vid] = int(value) & 1
            return
        raise ValueError(f"invalid enum domain: {self.name}")


def _build_enum_domains(
    ir: dict, assume: Optional[dict], const_oid_to_vid: Dict[int, int]
) -> Tuple[Dict[int, int], List[_EnumDomain], int, str]:
    fixed_env: Dict[int, int] = {}
    domains: List[_EnumDomain] = []
    enum_var_bits = 0
    enum_mode = "bit_product"

    constraints = parse_input_constraints(ir, assume)

    for s in (ir.get("signals", []) or []):
        if not isinstance(s, dict) or s.get("kind") != "input":
            continue
        name = s.get("name")
        if not isinstance(name, str) or name not in constraints:
            continue
        bits = s.get("bits", []) or []
        if not isinstance(bits, list):
            continue
        constraint = constraints[name]
        size = constraint.domain_size()
        if size <= 0:
            raise ValueError(f"assume.{name} has empty value domain")
        if constraint.has_exact_bit_cube():
            enum_var_bits += constraint.bit_unknown_count()
        else:
            enum_mode = "value_domains"
        if size == 1:
            fixed_val = next(constraint.iter_unsigned_values())
            for i, br in enumerate(bits):
                if not isinstance(br, dict) or br.get("kind") != "wire":
                    continue
                fixed_env[int(br["id"])] = (fixed_val >> i) & 1
        else:
            domains.append(
                _EnumDomain(
                    name=name,
                    size=size,
                    signal_bits=bits,
                    constraint=constraint,
                )
            )

    for vid in sorted(const_oid_to_vid.values()):
        domains.append(_EnumDomain(name=f"const_{vid}", size=2, const_vid=vid))
        enum_var_bits += 1

    return fixed_env, domains, enum_var_bits, enum_mode

def _collect_unsupported_output_bits(ir: dict) -> List[int]:
    var_set: Set[int] = set()
    for n in ir.get("nodes", []) or []:
        if not isinstance(n, dict) or n.get("op") != "UNSUPPORTED":
            continue
        for br in (n.get("ports", {}) or {}).get("Y", []) or []:
            if isinstance(br, dict) and br.get("kind") == "wire":
                var_set.add(int(br["id"]))
    return sorted(var_set)

def _read_vec_int(env: Dict[int, int], bitrefs: List[dict], const_oid_to_vid: Dict[int, int]) -> Tuple[int, int]:
    w = len(bitrefs or [])
    v = 0
    for i, br in enumerate(bitrefs or []):
        if not isinstance(br, dict):
            continue
        if br.get("kind") == "wire":
            bid = int(br["id"])
            bit = env.get(bid, 0)
        else:
            c = br.get("val")
            if c == "0":
                bit = 0
            elif c == "1":
                bit = 1
            else:
                vid = const_oid_to_vid.get(id(br))
                bit = env.get(vid, 0) if vid is not None else 0
        v |= (bit & 1) << i
    return v, w

def _write_vec_int(env: Dict[int, int], out_bitrefs: List[dict], value: int) -> None:
    for i, br in enumerate(out_bitrefs or []):
        if not isinstance(br, dict) or br.get("kind") != "wire":
            continue
        bid = int(br["id"])
        env[bid] = (value >> i) & 1

def _eval_node_concrete(op: str, ports: dict, params: dict, env: Dict[int, int], const_oid_to_vid: Dict[int, int]) -> int:
    y_bits = ports.get("Y", []) or []
    y_w = len(y_bits)

    def p_signed(pn: str) -> bool:
        if pn == "A":
            return bool(params.get("A_SIGNED", 0) == 1)
        if pn == "B":
            return bool(params.get("B_SIGNED", 0) == 1)
        return False

    def read(pn: str) -> Tuple[int, int, bool]:
        v, w = _read_vec_int(env, ports.get(pn, []) or [], const_oid_to_vid)
        return v, w, p_signed(pn)
    
    if op == "ZEXT":
        a, aw, _ = read("A")
        if aw > y_w:
            raise ValueError(f"ZEXT requires |A| <= |Y|, got A={aw}, Y={y_w}")
        return _resize(a, aw, y_w, signed=False) & _mask(y_w)

    if op == "SEXT":
        a, aw, _ = read("A")
        if aw > y_w:
            raise ValueError(f"SEXT requires |A| <= |Y|, got A={aw}, Y={y_w}")
        return _resize(a, aw, y_w, signed=True) & _mask(y_w)

    if op == "TRUNC":
        a, aw, _ = read("A")
        if aw < y_w:
            raise ValueError(f"TRUNC requires |A| >= |Y|, got A={aw}, Y={y_w}")
        return _resize(a, aw, y_w, signed=False) & _mask(y_w)
    
    if op in ("AND", "OR", "XOR"):
        a, aw, _ = read("A")
        b, bw, _ = read("B")
        if aw != bw or aw != y_w:
            raise ValueError(f"{op} expects canonical widths, got A={aw}, B={bw}, Y={y_w}")

        if op == "AND":
            out = a & b
        elif op == "OR":
            out = a | b
        else:
            out = a ^ b
        return out & _mask(y_w)

    if op == "NOT":
        a, aw, _ = read("A")
        if aw != y_w:
            raise ValueError(f"NOT expects canonical widths, got A={aw}, Y={y_w}")
        return (~a) & _mask(y_w)

    if op == "MUX":
        a, aw, _ = read("A")
        b, bw, _ = read("B")
        s, _ = _read_vec_int(env, ports.get("S", []) or [], const_oid_to_vid)
        if aw != bw or aw != y_w:
            raise ValueError(f"MUX expects canonical widths, got A={aw}, B={bw}, Y={y_w}")
        sel = s & 1
        out = a if sel == 0 else b
        return out & _mask(y_w)

    if op in ("ADD", "SUB"):
        a, aw, _ = read("A")
        b, bw, _ = read("B")
        if aw != bw or aw != y_w:
            raise ValueError(f"{op} expects canonical widths, got A={aw}, B={bw}, Y={y_w}")
        out = (a + b) if op == "ADD" else (a - b)
        return out & _mask(y_w)

    if op == "EXTRACT":
        a, aw, _ = read("A")
        offset = params.get("OFFSET")
        width = params.get("Y_WIDTH", y_w)
        if not isinstance(offset, int) or not isinstance(width, int):
            raise ValueError("EXTRACT missing OFFSET or Y_WIDTH")
        out = (a >> offset) & _mask(width)
        return out & _mask(y_w)

    if op == "CONCAT":
        low, lw, _ = read("A")
        high, hw, _ = read("B")
        out = (low & _mask(lw)) | ((high & _mask(hw)) << lw)
        return out & _mask(y_w)

    if op in ("SHL", "SHR", "ASHR"):
        a, aw, asg = read("A")
        b, bw, _ = read("B")
        if aw != y_w:
            raise ValueError(f"{op} expects canonical widths, got A={aw}, Y={y_w}")
        if bw <= 0:
            raise ValueError(f"{op} shift amount is empty")
        sh = b & _mask(bw)
        if op == "SHL":
            return (a << sh) & _mask(y_w)
        if op == "SHR":
            return (a >> sh) & _mask(y_w)
        return ((_as_signed(a, y_w) >> sh) & _mask(y_w)) if asg else ((a >> sh) & _mask(y_w))

    if op in ("EQ", "LT", "LE", "GT", "GE"):
        a, aw, asg = read("A")
        b, bw, bsg = read("B")
        if aw != bw:
            raise ValueError(f"{op} expects canonical widths, got A={aw}, B={bw}")
        if y_w != 1:
            raise ValueError(f"{op} output width must be 1, got Y={y_w}")
        if op == "EQ":
            r = 1 if a == b else 0
        else:
            signed_cmp = asg and bsg
            av = _as_signed(a, aw) if signed_cmp else a
            bv = _as_signed(b, bw) if signed_cmp else b
            if op == "LT":
                r = 1 if av < bv else 0
            elif op == "LE":
                r = 1 if av <= bv else 0
            elif op == "GT":
                r = 1 if av > bv else 0
            else:
                r = 1 if av >= bv else 0
        return r & 1

    if op == "LOGIC_NOT":
        a, aw, _ = read("A")
        if y_w != 1:
            raise ValueError(f"LOGIC_NOT expects canonical width Y=1, got Y={y_w}")
        r = 1 if (a & _mask(aw)) == 0 else 0
        return r & 1

    if op == "PMUX":
        a, aw, _ = read("A")
        b, bw, _ = read("B")
        s, sw = _read_vec_int(env, ports.get("S", []) or [], const_oid_to_vid)

        if aw != y_w:
            raise ValueError(f"PMUX expects canonical widths, got A={aw}, Y={y_w}")
        if bw != sw * y_w:
            raise ValueError(f"PMUX expects |B| = |S| * |Y|, got B={bw}, S={sw}, Y={y_w}")

        selected = [i for i in range(sw) if ((s >> i) & 1) == 1]

        if len(selected) == 0:
            return a & _mask(y_w)

        if len(selected) > 1:
            raise ValueError(f"PMUX multi-hot select in concrete eval: S={bin(s)}, width={sw}")

        i = selected[0]
        out = (b >> (i * y_w)) & _mask(y_w)
        return out & _mask(y_w)

def eval_ir_exact_enum(
    ir: dict | ModuleIR,
    assume: Optional[dict] = None,
    *,
    max_enum: int = 1_000_000,
    signals_mode: str = "outputs",  # 仅输出信号或全部信号
) -> dict:
    ir = _as_ir_dict(ir)
    signals = ir.get("signals", []) or []
    nodes = ir.get("nodes", []) or []

    const_oid_to_vid = _scan_const_nondet_ids(ir)
    fixed_env, domains, enum_var_bits, enum_mode = _build_enum_domains(ir, assume, const_oid_to_vid)
    unsupported_var_bits = _collect_unsupported_output_bits(ir)
    for vid in unsupported_var_bits:
        domains.append(_EnumDomain(name=f"unsupported_{vid}", size=2, const_vid=vid))
        enum_var_bits += 1

    enum_count = 1
    for dom in domains:
        enum_count *= dom.size
        if enum_count > max_enum:
            raise ValueError(f"too many enumerations: count={enum_count} > max_enum={max_enum}")

    bit_driver = _build_bit_driver(ir)
    ordered_nodes = _topo_sort_nodes(nodes, bit_driver)

    # 选哪些信号做真实集合统计
    if signals_mode == "all":
        tracked = [s for s in signals if isinstance(s, dict) and s.get("name") and isinstance(s.get("bits"), list)]
    else:
        tracked = [s for s in signals if isinstance(s, dict) and s.get("kind") == "output"]

    acc: Dict[str, dict] = {}
    for s in tracked:
        name = s["name"]
        w = len(s.get("bits", []) or [])
        acc[name] = {
            "width": w,
            "signed": bool(s.get("signed", False)),
            "and": _mask(w),  # 位与聚合
            "or": 0,          # 位或聚合
            "umin": None,
            "umax": None,
            "smin": None,
            "smax": None,
        }

    t0 = time.perf_counter()

    def _run_one_env(env: Dict[int, int]) -> None:
        for n in ordered_nodes:
            if not isinstance(n, dict):
                continue
            ports = n.get("ports", {}) or {}
            if "Y" not in ports:
                continue
            op = n.get("op")
            if op == "UNSUPPORTED":
                continue
            params = n.get("params", {}) or {}
            y = _eval_node_concrete(op, ports, params, env, const_oid_to_vid)
            _write_vec_int(env, ports["Y"], y)

        for s in tracked:
            name = s["name"]
            v, w = _read_vec_int(env, s.get("bits", []) or [], const_oid_to_vid)
            v &= _mask(w)

            a = acc[name]
            a["and"] &= v
            a["or"] |= v
            a["umin"] = v if a["umin"] is None else min(a["umin"], v)
            a["umax"] = v if a["umax"] is None else max(a["umax"], v)

            sv = _as_signed(v, w)
            a["smin"] = sv if a["smin"] is None else min(a["smin"], sv)
            a["smax"] = sv if a["smax"] is None else max(a["smax"], sv)

    def _enum_domains(idx: int, env: Dict[int, int]) -> None:
        if idx >= len(domains):
            _run_one_env(env)
            return
        dom = domains[idx]
        for value in dom.iter_values():
            next_env = dict(env)
            dom.assign(next_env, int(value))
            _enum_domains(idx + 1, next_env)

    _enum_domains(0, dict(fixed_env))

    t1 = time.perf_counter()
    sig_out: Dict[str, dict] = {}
    for name, a in acc.items():
        w = a["width"]
        m = _mask(w)
        acc_and = int(a["and"]) & m
        acc_or = int(a["or"]) & m
        known1 = acc_and
        known0 = (~acc_or) & m
        known_mask = known1 | known0
        known_value = known1
        bits_msb = "".join(
            ("1" if ((known_value >> i) & 1) else "0") if ((known_mask >> i) & 1) else "X"
            for i in range(w - 1, -1, -1)
        )
        sig_out[name] = {
            "width": w,
            "signed": bool(a["signed"]),
            "bits_msb": bits_msb,
            "known_mask_hex": hex(known_mask),
            "known_value_hex": hex(known_value),
            "unknown_count": w - int(known_mask).bit_count(),
            "range_unsigned": [int(a["umin"]), int(a["umax"])],
            "range_signed": [int(a["smin"]), int(a["smax"])],
        }
    return {
        "domain": "exact_enum",
        "top_module": ir.get("top_module"),
        "assume": assume or {},
        "enum_var_bits": enum_var_bits,
        "enum_mode": enum_mode,
        "enum_domain_sizes": [dom.size for dom in domains],
        "enum_count": enum_count,
        "time_seconds": (t1 - t0),
        "signals": sig_out,
    }

def compare_exact_vs_abstract(exact: dict, abstract: dict) -> dict:
    ex_sigs = (exact or {}).get("signals", {}) or {}
    ab_sigs = (abstract or {}).get("signals", {}) or {}
    ok = True
    issues: List[dict] = []
    for name, ab in ab_sigs.items():
        if name not in ex_sigs:
            continue
        ex = ex_sigs[name]
        w = int(ab.get("width", 0))
        ab_km = int(ab.get("known_mask_hex", "0"), 16)
        ab_kv = int(ab.get("known_value_hex", "0"), 16)
        ex_km = int(ex.get("known_mask_hex", "0"), 16)
        ex_kv = int(ex.get("known_value_hex", "0"), 16)

        bad_bits: List[int] = []
        for i in range(w):
            if (ab_km >> i) & 1:
                ab_bit = (ab_kv >> i) & 1
                if ((ex_km >> i) & 1) == 0:
                    bad_bits.append(i)
                else:
                    ex_bit = (ex_kv >> i) & 1
                    if ex_bit != ab_bit:
                        bad_bits.append(i)
        if bad_bits:
            ok = False
            issues.append({"signal": name, "bad_bit_positions_lsb": bad_bits})
        # 简单区间包含检查（无符号）
        alo, ahi = ab.get("range_unsigned", [0, (1 << w) - 1])
        exlo, exhi = ex.get("range_unsigned", [0, 0])
        if not (alo <= exlo and exhi <= ahi):
            issues.append({"signal": name, "range_mismatch": {"abstract": [alo, ahi], "exact": [exlo, exhi]}})

    return {"ok": ok, "issues": issues}

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True, help="path to ir.json")
    ap.add_argument("--inputs", required=True, help="path to inputs.json")
    ap.add_argument("--out", required=True, help="path to write exact.json")
    ap.add_argument("--max-enum", type=int, default=1_000_000)
    ap.add_argument("--signals-mode", choices=["outputs", "all"], default="outputs")
    ap.add_argument("--compare", default=None, help="optional path to abstract eval.json")
    ap.add_argument("--compare-out", default=None, help="optional path to write compare_report.json")
    args = ap.parse_args()

    ir = _read_json(Path(args.ir))
    assume = _read_json(Path(args.inputs))

    exact = eval_ir_exact_enum(ir, assume, max_enum=args.max_enum, signals_mode=args.signals_mode)
    _write_json(Path(args.out), exact)

    if args.compare:
        abstract = _read_json(Path(args.compare))
        rep = compare_exact_vs_abstract(exact, abstract)
        if args.compare_out:
            _write_json(Path(args.compare_out), rep)
        print("compare ok" if rep["ok"] else "compare FAILED")
        if not rep["ok"]:
            print("issues:", len(rep["issues"]))

    if exact.get("enum_mode") == "bit_product":
        print(
            f"exact enum done: vars={exact['enum_var_bits']} count={exact['enum_count']} "
            f"time={exact['time_seconds']:.6f}s"
        )
    else:
        print(
            f"exact enum done: mode={exact.get('enum_mode')} count={exact['enum_count']} "
            f"time={exact['time_seconds']:.6f}s"
        )

if __name__ == "__main__":
    main()
