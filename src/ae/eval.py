from __future__ import annotations

from typing import Dict, Any, List, Optional, Set, Tuple
from itertools import product

from src.ae.bv3 import BV3, Bit3
from src.ir.ir_types import ModuleIR


def _as_ir_dict(ir: dict | ModuleIR) -> dict:
    return ir.to_dict() if isinstance(ir, ModuleIR) else ir

def _read_bv3_from_bits(env: Dict[int, Bit3], bitrefs: List[dict], signed: bool = False) -> BV3:
    bits: List[Bit3] = []
    for br in bitrefs:
        if br.get("kind") == "const":
            v = br.get("val")
            if v == "0":
                bits.append(Bit3.Z0)
            elif v == "1":
                bits.append(Bit3.Z1)
            else:
                bits.append(Bit3.X)
        else:
            bid = int(br["id"])
            bits.append(env.get(bid, Bit3.X))
    return BV3.from_bits(bits, signed=signed)

def _write_bits(env: Dict[int, Bit3], out_bitrefs: List[dict], value: BV3) -> None:
    bits = value.to_bits()
    if len(bits) != len(out_bitrefs):
        return
    for br, bv in zip(out_bitrefs, bits):
        if br.get("kind") == "wire":
            env[int(br["id"])] = bv

# ----------按位逻辑运算----------
def _bit_and(a: Bit3, b: Bit3) -> Bit3:
    if a is Bit3.Z0 or b is Bit3.Z0:
        return Bit3.Z0
    if a is Bit3.Z1 and b is Bit3.Z1:
        return Bit3.Z1
    return Bit3.X

def _bit_or(a: Bit3, b: Bit3) -> Bit3:
    if a is Bit3.Z1 or b is Bit3.Z1:
        return Bit3.Z1
    if a is Bit3.Z0 and b is Bit3.Z0:
        return Bit3.Z0
    return Bit3.X

def _bit_xor(a: Bit3, b: Bit3) -> Bit3:
    if a is Bit3.X or b is Bit3.X:
        return Bit3.X
    return Bit3.Z1 if (a is not b) else Bit3.Z0

def _bit_not(a: Bit3) -> Bit3:
    if a is Bit3.Z0:
        return Bit3.Z1
    if a is Bit3.Z1:
        return Bit3.Z0
    return Bit3.X

def _join_bv3_values(cands: List[BV3]) -> BV3:
    if not cands:
        raise ValueError("join candidates must not be empty")
    acc = cands[0]
    for v in cands[1:]:
        acc = acc.join(v)
    return acc

# 若未知位数太多则返回 None；否则枚举所有可能的无符号值
def _possible_uvals_from_bits(bits_lsb: List[Bit3], max_enum: int = 64) -> Optional[List[int]]:
    unk = [i for i, b in enumerate(bits_lsb) if b is Bit3.X]
    # 没有未知位
    if len(unk) == 0:
        v = 0
        for i, b in enumerate(bits_lsb):
            if b is Bit3.Z1:
                v |= (1 << i)
        return [v]
    if len(unk) > 6:
        return None
    if (1 << len(unk)) > max_enum:
        return None
    base = 0
    for i, b in enumerate(bits_lsb):
        if b is Bit3.Z1:
            base |= (1 << i)
    vals: List[int] = []
    for assign in product([0, 1], repeat=len(unk)):
        v = base
        for idx, bit in zip(unk, assign):
            if bit == 1:
                v |= (1 << idx)
            else:
                v &= ~(1 << idx)
        vals.append(v)
    return vals

# 左移
def _shift_left(bits_lsb: List[Bit3], sh: int) -> List[Bit3]:
    w = len(bits_lsb)
    out = [Bit3.Z0] * w
    for i in range(w):
        src = i - sh
        if 0 <= src < w:
            out[i] = bits_lsb[src]
    return out

# 逻辑右移
def _shift_right(bits_lsb: List[Bit3], sh: int) -> List[Bit3]:
    w = len(bits_lsb)
    out = [Bit3.Z0] * w
    for i in range(w):
        src = i + sh
        if 0 <= src < w:
            out[i] = bits_lsb[src]
    return out

def _ext_to(v: BV3, w: int) -> BV3:
    return v.sext(w) if getattr(v, "signed", False) else v.zext(w)

def _align_mixed(a: BV3, b: BV3, out_w: int) -> Tuple[BV3, BV3]:
    w = max(a.width, b.width, out_w)
    return _ext_to(a, w), _ext_to(b, w)

# 算术右移
def _shift_arith_right(bits_lsb: List[Bit3], sh: int) -> List[Bit3]:
    w = len(bits_lsb)
    sign = bits_lsb[w - 1] if w > 0 else Bit3.X
    out = [Bit3.X] * w
    for i in range(w):
        src = i + sh
        if 0 <= src < w:
            out[i] = bits_lsb[src]
        else:
            out[i] = sign
    return out

def _bit3_to_vals(b: Bit3) -> Set[int]:
    if b is Bit3.Z0:
        return {0}
    if b is Bit3.Z1:
        return {1}
    return {0, 1}

def _vals_to_bit3(vals: Set[int]) -> Bit3:
    if vals == {0}:
        return Bit3.Z0
    if vals == {1}:
        return Bit3.Z1
    return Bit3.X

def _collect_src_vals(bits_lsb: List[Bit3], j_lo: int, j_hi: int) -> Set[int]:
    vals: Set[int] = set()
    if j_lo > j_hi:
        return vals
    for j in range(j_lo, j_hi + 1):
        vals |= _bit3_to_vals(bits_lsb[j])
    return vals

def _shift_left_interval(bits_lsb: List[Bit3], sh_lo: int, sh_hi: int) -> List[Bit3]:
    w = len(bits_lsb)
    out: List[Bit3] = []
    for i in range(w):
        vals: Set[int] = set()
        valid_lo = i - (w - 1)
        valid_hi = i
        j_lo = max(0, i - sh_hi)
        j_hi = min(w - 1, i - sh_lo)
        vals |= _collect_src_vals(bits_lsb, j_lo, j_hi)
        # 若区间包含无效移位，逻辑左移该位可能被0填充。
        if sh_lo < valid_lo or sh_hi > valid_hi:
            vals.add(0)
        if not vals:
            vals.add(0)
        out.append(_vals_to_bit3(vals))
    return out

def _shift_right_interval(bits_lsb: List[Bit3], sh_lo: int, sh_hi: int) -> List[Bit3]:
    w = len(bits_lsb)
    out: List[Bit3] = []
    for i in range(w):
        vals: Set[int] = set()
        valid_hi = w - 1 - i
        j_lo = i + sh_lo
        j_hi = min(w - 1, i + sh_hi)
        vals |= _collect_src_vals(bits_lsb, j_lo, j_hi)
        # 若区间包含超过可取源位的移位量，逻辑右移该位会被0填充。
        if sh_hi > valid_hi:
            vals.add(0)
        if not vals:
            vals.add(0)
        out.append(_vals_to_bit3(vals))
    return out

def _shift_arith_right_interval(bits_lsb: List[Bit3], sh_lo: int, sh_hi: int) -> List[Bit3]:
    w = len(bits_lsb)
    sign = bits_lsb[w - 1] if w > 0 else Bit3.X
    out: List[Bit3] = []
    for i in range(w):
        vals: Set[int] = set()
        valid_hi = w - 1 - i
        j_lo = i + sh_lo
        j_hi = min(w - 1, i + sh_hi)
        vals |= _collect_src_vals(bits_lsb, j_lo, j_hi)
        # 若区间包含超过可取源位的移位量，算术右移该位会用符号位填充。
        if sh_hi > valid_hi:
            vals |= _bit3_to_vals(sign)
        if not vals:
            vals |= _bit3_to_vals(sign)
        out.append(_vals_to_bit3(vals))
    return out

# 单bit全加器：枚举a,b,cin的可能取值集合，得到sum和cout的可能集合
def _fa(a: Bit3, b: Bit3, cin: Bit3) -> Tuple[Bit3, Bit3]:
    def vals(x: Bit3) -> List[int]:
        if x is Bit3.Z0:
            return [0]
        if x is Bit3.Z1:
            return [1]
        return [0, 1]
    sums: Set[int] = set()
    couts: Set[int] = set()
    for aa in vals(a):
        for bb in vals(b):
            for cc in vals(cin):
                s = aa ^ bb ^ cc
                c = (aa & bb) | (aa & cc) | (bb & cc)
                sums.add(s)
                couts.add(c)
    sum_bit = Bit3.Z0 if sums == {0} else (Bit3.Z1 if sums == {1} else Bit3.X)
    cout_bit = Bit3.Z0 if couts == {0} else (Bit3.Z1 if couts == {1} else Bit3.X)
    return sum_bit, cout_bit


def _add_bv3(a: BV3, b: BV3, out_w: int) -> BV3:
    a2 = a.sext(out_w) if getattr(a, "signed", False) else a.zext(out_w)
    b2 = b.sext(out_w) if getattr(b, "signed", False) else b.zext(out_w)
    abits = a2.to_bits()
    bbits = b2.to_bits()

    cin = Bit3.Z0
    out: List[Bit3] = []
    for i in range(out_w):
        s, cin = _fa(abits[i], bbits[i], cin)
        out.append(s)
    res_signed = bool(getattr(a, "signed", False) or getattr(b, "signed", False))
    return BV3.from_bits(out, signed=res_signed).trunc(out_w)

# a + (~b + 1)
def _sub_bv3(a: BV3, b: BV3, out_w: int) -> BV3:
    b_signed = bool(getattr(b, "signed", False))
    b2 = b.sext(out_w) if b_signed else b.zext(out_w)
    inv = [_bit_not(x) for x in b2.to_bits()]
    inv_b = BV3.from_bits(inv, signed=b_signed).trunc(out_w)
    one = BV3.const(out_w, 1, signed=b_signed)
    tmp = _add_bv3(inv_b, one, out_w)
    return _add_bv3(a, tmp, out_w)

def _resize_to_out(v: BV3, out_w: int) -> BV3:
    return v.sext(out_w) if getattr(v, "signed", False) else v.zext(out_w)

def _interval_prefix_bv3(lo: int, hi: int, width: int, signed: bool) -> BV3:
    if width <= 0:
        return BV3(width=0, signed=signed, known_mask=0, known_value=0)
    m = (1 << width) - 1
    lo &= m
    hi &= m
    diff = lo ^ hi
    if diff == 0:
        return BV3(width=width, signed=signed, known_mask=m, known_value=lo)
    highest_diff = diff.bit_length() - 1
    unknown_low_mask = (1 << (highest_diff + 1)) - 1
    known_mask = m & ~unknown_low_mask
    known_value = lo & known_mask
    return BV3(width=width, signed=signed, known_mask=known_mask, known_value=known_value)

def _meet_known_bits(base: BV3, extra: BV3) -> BV3:
    if base.width != extra.width:
        return base
    conflict = ((base.known_value ^ extra.known_value) & (base.known_mask & extra.known_mask)) != 0
    if conflict:
        return base
    km = base.known_mask | extra.known_mask
    kv = ((base.known_value & base.known_mask) | (extra.known_value & extra.known_mask)) & km
    return BV3(width=base.width, signed=base.signed, known_mask=km, known_value=kv)

def _tighten_add_no_split(base: BV3, a: BV3, b: BV3) -> BV3:
    w = base.width
    if w <= 0:
        return base
    mod = 1 << w
    alo, ahi = a.range_unsigned()
    blo, bhi = b.range_unsigned()
    s_lo = alo + blo
    s_hi = ahi + bhi
    # 只在模2^w后仍为单段区间时收紧
    if s_hi < mod:
        lo, hi = s_lo, s_hi
    elif s_lo >= mod:
        lo, hi = s_lo - mod, s_hi - mod
    else:
        return base
    return _meet_known_bits(base, _interval_prefix_bv3(lo, hi, w, base.signed))

def _tighten_sub_no_split(base: BV3, a: BV3, b: BV3) -> BV3:
    w = base.width
    if w <= 0:
        return base
    mod = 1 << w
    alo, ahi = a.range_unsigned()
    blo, bhi = b.range_unsigned()
    d_lo = alo - bhi
    d_hi = ahi - blo
    # 只在模2^w后仍为单段区间时收紧
    if d_lo >= 0:
        lo, hi = d_lo, d_hi
    elif d_hi < 0:
        lo, hi = d_lo + mod, d_hi + mod
    else:
        return base
    return _meet_known_bits(base, _interval_prefix_bv3(lo, hi, w, base.signed))

def _apply_assumptions(ir: dict, env: Dict[int, Bit3], assume: Optional[dict]) -> None:
    if not assume:
        return
    sigs = assume.get("signals", {})
    if not isinstance(sigs, dict):
        raise ValueError("assume.signals must be an object")
    sig_map = {s.get("name"): s for s in ir.get("signals", []) if isinstance(s, dict) and s.get("name")}
    for name, spec in sigs.items():
        if name not in sig_map:
            raise ValueError(f"assume signal not found in IR: {name}")
        s = sig_map[name]
        if s.get("kind") != "input":
            raise ValueError(f"assume only supports input signals currently: {name}")
        bits = s.get("bits", [])
        if not isinstance(bits, list):
            raise ValueError(f"IR signal bits malformed: {name}")
        if isinstance(spec, str):
            bits_msb = spec
        elif isinstance(spec, dict):
            bits_msb = spec.get("bits_msb")
        else:
            raise ValueError(f"assume spec must be string or object: {name}")
        if not isinstance(bits_msb, str):
            raise ValueError(f"assume.{name}.bits_msb must be string")
        if len(bits_msb) != len(bits):
            raise ValueError(
                f"assume width mismatch for {name}: bits_msb len={len(bits_msb)} IR width={len(bits)}"
            )
        bits_lsb = list(reversed(bits_msb))
        for i, ch in enumerate(bits_lsb):
            br = bits[i]
            if br.get("kind") != "wire":
                continue
            bid = int(br["id"])
            if ch == "0":
                env[bid] = Bit3.Z0
            elif ch == "1":
                env[bid] = Bit3.Z1
            elif ch in ("X", "x"):
                env[bid] = Bit3.X
            else:
                raise ValueError(f"invalid char in assume bits_msb for {name}: {ch}")

def _eval_node(op: str, ports: dict, params: dict, env: Dict[int, Bit3]) -> BV3:
    y_bits = ports.get("Y", [])
    y_w = len(y_bits)

    def _p_signed(pn: str) -> bool:
        if pn == "A":
            return bool(params.get("A_SIGNED", 0) == 1)
        if pn == "B":
            return bool(params.get("B_SIGNED", 0) == 1)
        return False

    def vec(pn: str) -> BV3:
        return _read_bv3_from_bits(env, ports.get(pn, []), signed=_p_signed(pn))

    if op == "AND":
        a, b = _align_mixed(vec("A"), vec("B"), y_w)
        out_bits = [_bit_and(x, y) for x, y in zip(a.to_bits(), b.to_bits())]
        return BV3.from_bits(out_bits).trunc(y_w)

    if op == "OR":
        a, b = _align_mixed(vec("A"), vec("B"), y_w)
        out_bits = [_bit_or(x, y) for x, y in zip(a.to_bits(), b.to_bits())]
        return BV3.from_bits(out_bits).trunc(y_w)

    if op == "XOR":
        a, b = _align_mixed(vec("A"), vec("B"), y_w)
        out_bits = [_bit_xor(x, y) for x, y in zip(a.to_bits(), b.to_bits())]
        return BV3.from_bits(out_bits).trunc(y_w)

    if op == "NOT":
        a = vec("A")
        out_bits = [_bit_not(x) for x in a.to_bits()]
        return BV3.from_bits(out_bits).trunc(y_w)

    if op == "MUX":
        s = vec("S")
        a = vec("A")
        b = vec("B")
        sel = s.bit(0) if s.width >= 1 else Bit3.X
        a, b = BV3.align_pair(a, b, policy="zext")
        a_t = a.trunc(y_w)
        b_t = b.trunc(y_w)
        if sel is Bit3.Z0:
            return a_t
        if sel is Bit3.Z1:
            return b_t
        return a_t.join(b_t)

    if op == "EXTRACT":
        a = vec("A")
        offset = params.get("OFFSET")
        width = params.get("Y_WIDTH", y_w)
        if not isinstance(offset, int) or not isinstance(width, int):
            return BV3.top(y_w)
        out_bits = a.to_bits()[offset: offset + width]
        if len(out_bits) < y_w:
            out_bits = out_bits + [Bit3.X] * (y_w - len(out_bits))
        return BV3.from_bits(out_bits[:y_w])

    if op == "CONCAT":
        low = vec("A")
        high = vec("B")
        out_bits = low.to_bits() + high.to_bits()
        if len(out_bits) < y_w:
            out_bits = out_bits + [Bit3.X] * (y_w - len(out_bits))
        return BV3.from_bits(out_bits[:y_w])

    if op == "EQ":
        a, b = _align_mixed(vec("A"), vec("B"), 1)
        conflict = ((a.known_value ^ b.known_value) & (a.known_mask & b.known_mask)) != 0
        if conflict:
            return BV3.from_bits([Bit3.Z0]).trunc(y_w)
        all_known = (a.known_mask == ((1 << a.width) - 1)) and (b.known_mask == ((1 << b.width) - 1))
        if all_known and (a.known_value == b.known_value):
            return BV3.from_bits([Bit3.Z1]).trunc(y_w)
        return BV3.from_bits([Bit3.X]).trunc(y_w)

    if op == "SHL":
        a = vec("A").trunc(y_w)
        shv = vec("B")
        a_bits = a.to_bits()
        sh_bits = shv.to_bits()
        cands = _possible_uvals_from_bits(sh_bits)
        if cands is None:
            sh_lo, sh_hi = shv.range_unsigned()
            out_bits = _shift_left_interval(a_bits, int(sh_lo), int(sh_hi))
            return BV3.from_bits(out_bits).trunc(y_w)
        outs = [BV3.from_bits(_shift_left(a_bits, int(s))).trunc(y_w) for s in cands]
        return _join_bv3_values(outs)

    if op == "SHR":
        a = vec("A").trunc(y_w)
        shv = vec("B")
        a_bits = a.to_bits()
        sh_bits = shv.to_bits()
        cands = _possible_uvals_from_bits(sh_bits)
        if cands is None:
            sh_lo, sh_hi = shv.range_unsigned()
            out_bits = _shift_right_interval(a_bits, int(sh_lo), int(sh_hi))
            return BV3.from_bits(out_bits).trunc(y_w)
        outs = [BV3.from_bits(_shift_right(a_bits, int(s))).trunc(y_w) for s in cands]
        return _join_bv3_values(outs)

    if op == "ADD":
        a, b = _align_mixed(vec("A"), vec("B"), y_w)
        out = _add_bv3(a, b, y_w)
        a2 = _resize_to_out(a, y_w)
        b2 = _resize_to_out(b, y_w)
        return _tighten_add_no_split(out, a2, b2)

    if op == "SUB":
        a, b = _align_mixed(vec("A"), vec("B"), y_w)
        out = _sub_bv3(a, b, y_w)
        a2 = _resize_to_out(a, y_w)
        b2 = _resize_to_out(b, y_w)
        return _tighten_sub_no_split(out, a2, b2)
    
    if op == "ASHR":
        a = vec("A").trunc(y_w)
        shv = vec("B")
        a_bits = a.to_bits()
        cands = _possible_uvals_from_bits(shv.to_bits())
        if cands is None:
            sh_lo, sh_hi = shv.range_unsigned()
            out_bits = _shift_arith_right_interval(a_bits, int(sh_lo), int(sh_hi))
            return BV3.from_bits(out_bits).trunc(y_w)
        outs = [BV3.from_bits(_shift_arith_right(a_bits, int(s))).trunc(y_w) for s in cands]
        return _join_bv3_values(outs)
    
    if op in ("LT", "LE", "GT", "GE"):
        a, b = _align_mixed(vec("A"), vec("B"), max(1, y_w))
        signed_cmp = bool(params.get("A_SIGNED", 0) == 1) and bool(params.get("B_SIGNED", 0) == 1)
        if signed_cmp and hasattr(a, "range_signed") and hasattr(b, "range_signed"):
            alo, ahi = a.range_signed()
            blo, bhi = b.range_signed()
        else:
            alo, ahi = a.range_unsigned()
            blo, bhi = b.range_unsigned()
        def definitely_true() -> bool:
            if op == "LT": return ahi < blo
            if op == "LE": return ahi <= blo
            if op == "GT": return alo > bhi
            if op == "GE": return alo >= bhi
            return False
        
        def definitely_false() -> bool:
            if op == "LT": return alo >= bhi
            if op == "LE": return alo >  bhi
            if op == "GT": return ahi <= blo
            if op == "GE": return ahi <  blo
            return False
        if definitely_true():
            return BV3.from_bits([Bit3.Z1]).trunc(y_w)
        if definitely_false():
            return BV3.from_bits([Bit3.Z0]).trunc(y_w)
        return BV3.from_bits([Bit3.X]).trunc(y_w)
    return BV3.top(y_w)

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

# 按依赖关系给nodes拓扑排序
def _topo_sort_nodes(nodes: List[dict], bit_driver: Dict[int, Optional[str]]) -> List[dict]:
    nid_to_node = {n["nid"]: n for n in nodes}
    deps: Dict[str, Set[str]] = {n["nid"]: set() for n in nodes}
    for n in nodes:
        nid = n["nid"]
        ports = n.get("ports", {}) or {}
        for pn, bits in ports.items():
            if pn == "Y":
                continue
            for br in bits:
                if br.get("kind") != "wire":
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
    if len(order) != len(nodes):
        return nodes
    return [nid_to_node[nid] for nid in order]

def eval_ir_bv3(ir: dict | ModuleIR, assume: Optional[dict] = None) -> dict:
    ir = _as_ir_dict(ir)
    signals = ir.get("signals", [])
    nodes = ir.get("nodes", [])
    env: Dict[int, Bit3] = {}
    for s in signals:
        if s.get("kind") == "input":
            for br in s.get("bits", []):
                if br.get("kind") == "wire":
                    env[int(br["id"])] = Bit3.X

    _apply_assumptions(ir, env, assume)

    bit_driver = _build_bit_driver(ir)
    ordered_nodes = _topo_sort_nodes(nodes, bit_driver)

    node_out: Dict[str, dict] = {}
    for n in ordered_nodes:
        op = n.get("op")
        ports = n.get("ports", {}) or {}
        params = n.get("params", {}) or {}
        if "Y" not in ports:
            continue
        outv = _eval_node(op, ports, params, env)
        _write_bits(env, ports["Y"], outv)
        node_out[n["nid"]] = {"op": op, "out": outv.to_dict()}

    sig_out: Dict[str, dict] = {}
    for s in signals:
        name = s.get("name")
        signed = bool(s.get("signed", False))
        v = _read_bv3_from_bits(env, s.get("bits", []), signed=signed)
        sig_out[name] = v.to_dict()

    return {
        "domain": "bv3",
        "top_module": ir.get("top_module"),
        "assume": assume or {},
        "signals": sig_out,
        "nodes": node_out,
    }
