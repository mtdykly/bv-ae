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

def _possible_uvals_from_bv3(v: BV3, max_enum: int = 64) -> Optional[List[int]]:
    unk = [i for i in range(v.width) if ((v.unknown_mask >> i) & 1) != 0]
    if len(unk) == 0:
        m = (1 << v.width) - 1 if v.width > 0 else 0
        return [v.known_value & m]
    if len(unk) > 6:
        return None
    if (1 << len(unk)) > max_enum:
        return None
    m = (1 << v.width) - 1 if v.width > 0 else 0
    base = v.known_value & m
    vals: List[int] = []
    for assign in product([0, 1], repeat=len(unk)):
        x = base
        for idx, bit in zip(unk, assign):
            if bit == 1:
                x |= (1 << idx)
            else:
                x &= ~(1 << idx)
        vals.append(x & m)
    return vals

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

# 提取区间公共二进制前缀
def _interval_prefix_bv3(lo: int, hi: int, width: int, signed: bool) -> BV3:
    if width <= 0:
        return BV3(width=0, signed=signed, known_mask=0, known_value=0)
    m = (1 << width) - 1
    lo &= m
    hi &= m
    diff = lo ^ hi
    # 完全相同，区间只有一个值
    if diff == 0:
        return BV3(width=width, signed=signed, known_mask=m, known_value=lo)
    # 最高的不同位
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

def _eval_node(
    op: str,
    ports: dict,
    params: dict,
    env: Dict[int, Bit3],
    out_signed: bool = False,
) -> BV3:
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

    def _as_out(v: BV3) -> BV3:
        return BV3(
            width=v.width,
            signed=out_signed,
            known_mask=v.known_mask,
            known_value=v.known_value,
        )
    
    if op == "ZEXT":
        a = vec("A")
        z = a.zext(y_w)
        return BV3(
            width=y_w,
            signed=False,
            known_mask=z.known_mask,
            known_value=z.known_value,
        )

    if op == "SEXT":
        a = vec("A")
        z = a.sext(y_w)
        return BV3(
            width=y_w,
            signed=True,
            known_mask=z.known_mask,
            known_value=z.known_value,
        )

    if op == "TRUNC":
        a = vec("A")
        z = a.trunc(y_w)
        return BV3(
            width=y_w,
            signed=out_signed,
            known_mask=z.known_mask,
            known_value=z.known_value,
        )
    
    if op == "AND":
        a = vec("A")
        b = vec("B")
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"AND expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")
        wm = (1 << y_w) - 1 if y_w > 0 else 0
        a_k1 = a.known_mask & a.known_value
        a_k0 = a.known_mask & ((~a.known_value) & wm)
        b_k1 = b.known_mask & b.known_value
        b_k0 = b.known_mask & ((~b.known_value) & wm)
        known1 = a_k1 & b_k1
        known0 = a_k0 | b_k0
        km = (known0 | known1) & wm
        kv = known1 & wm
        return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))

    if op == "OR":
        a = vec("A")
        b = vec("B")
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"OR expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")
        wm = (1 << y_w) - 1 if y_w > 0 else 0
        a_k1 = a.known_mask & a.known_value
        a_k0 = a.known_mask & ((~a.known_value) & wm)
        b_k1 = b.known_mask & b.known_value
        b_k0 = b.known_mask & ((~b.known_value) & wm)
        known1 = a_k1 | b_k1
        known0 = a_k0 & b_k0
        km = (known0 | known1) & wm
        kv = known1 & wm
        return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))

    if op == "XOR":
        a = vec("A")
        b = vec("B")
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"XOR expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")
        wm = (1 << y_w) - 1 if y_w > 0 else 0
        known = a.known_mask & b.known_mask
        value = (a.known_value ^ b.known_value) & known & wm
        return _as_out(BV3(width=y_w, signed=False, known_mask=known & wm, known_value=value))

    if op == "NOT":
        a = vec("A")
        if a.width != y_w:
            raise ValueError(f"NOT expects canonical widths, got A={a.width}, Y={y_w}")
        wm = (1 << y_w) - 1 if y_w > 0 else 0
        km = a.known_mask & wm
        kv = ((~a.known_value) & wm) & km
        return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))

    if op == "LOGIC_NOT":
        a = vec("A")
        if y_w != 1:
            raise ValueError(f"LOGIC_NOT expects canonical width Y=1, got Y={y_w}")
        alo, ahi = a.range_unsigned()
        if alo == 0 and ahi == 0:
            return _as_out(BV3.const(1, 1, signed=False))
        if alo > 0:
            return _as_out(BV3.const(1, 0, signed=False))
        return _as_out(BV3.top(1, signed=False))

    if op == "MUX":
        s = vec("S")
        a = vec("A")
        b = vec("B")
        sel = s.bit(0) if s.width >= 1 else Bit3.X
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"MUX expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")
        if sel is Bit3.Z0:
            return _as_out(a)
        if sel is Bit3.Z1:
            return _as_out(b)
        return _as_out(a.join(b))

    if op == "PMUX":
        a = vec("A")
        b = vec("B")
        s = vec("S")
        if a.width != y_w:
            raise ValueError(f"PMUX expects canonical widths, got A={a.width}, Y={y_w}")
        if b.width != s.width * y_w:
            raise ValueError(
                f"PMUX expects |B| = |S| * |Y|, got B={b.width}, S={s.width}, Y={y_w}"
            )
        if s.width == 0:
            return _as_out(a)
        cases: List[BV3] = []
        for i in range(s.width):
            offset = i * y_w
            m = (1 << y_w) - 1 if y_w > 0 else 0
            km = (b.known_mask >> offset) & m
            kv = (b.known_value >> offset) & m
            case_i = BV3(width=y_w, signed=False, known_mask=km, known_value=kv)
            cases.append(case_i)

        ones: List[int] = []
        xs: List[int] = []
        for i in range(s.width):
            sb = s.bit(i)
            if sb is Bit3.Z1:
                ones.append(i)
            elif sb is Bit3.X:
                xs.append(i)

        if len(ones) == 0 and len(xs) == 0:
            return _as_out(a)
        if len(ones) == 1 and len(xs) == 0:
            return _as_out(cases[ones[0]])

        cands = [a]
        for i in range(s.width):
            sb = s.bit(i)
            if sb is not Bit3.Z0:
                cands.append(cases[i])

        out = cands[0]
        for c in cands[1:]:
            out = out.join(c)
        return _as_out(out)

    if op == "EXTRACT":
        a = vec("A")
        offset = params.get("OFFSET")
        if not isinstance(offset, int) or offset < 0:
            return _as_out(BV3.top(y_w))
        avail = max(0, min(y_w, a.width - offset))
        if avail == 0:
            return _as_out(BV3.top(y_w))
        m = (1 << avail) - 1
        km = (a.known_mask >> offset) & m
        kv = (a.known_value >> offset) & m
        return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))

    if op == "CONCAT":
        low = vec("A")
        high = vec("B")
        total_w = low.width + high.width
        km = low.known_mask | (high.known_mask << low.width)
        kv = low.known_value | (high.known_value << low.width)
        if total_w >= y_w:
            m = (1 << y_w) - 1 if y_w > 0 else 0
            return _as_out(
                BV3(
                    width=y_w,
                    signed=False,
                    known_mask=km & m,
                    known_value=kv & m,
                )
            )
        return _as_out(
            BV3(
                width=y_w,
                signed=False,
                known_mask=km,
                known_value=kv,
            )
        )

    if op == "EQ":
        a = vec("A")
        b = vec("B")
        if a.width != b.width:
            raise ValueError(f"EQ expects canonical widths, got A={a.width}, B={b.width}")
        # 肯定不等
        conflict = ((a.known_value ^ b.known_value) & (a.known_mask & b.known_mask)) != 0
        if conflict:
            return _as_out(BV3.from_bits([Bit3.Z0]).trunc(y_w))
        # 肯定相等
        full = (1 << a.width) - 1 if a.width > 0 else 0
        all_known = (a.known_mask == full) and (b.known_mask == full)
        if all_known and (a.known_value == b.known_value):
            return _as_out(BV3.from_bits([Bit3.Z1]).trunc(y_w))
        # 未知
        return _as_out(BV3.from_bits([Bit3.X]).trunc(y_w))

    if op == "SHL":
        a = vec("A")
        if a.width != y_w:
            raise ValueError(...)
        shv = vec("B")
        sh_lo, sh_hi = shv.range_unsigned()
        # 移位量确定时
        if sh_lo == sh_hi:
            sh = int(sh_lo)
            if y_w <= 0:
                return _as_out(BV3(width=0, signed=False, known_mask=0, known_value=0))
            m = (1 << y_w) - 1
            fill = min(sh, y_w)
            low_zero_mask = (1 << fill) - 1 if fill > 0 else 0
            km = ((a.known_mask << sh) & m) | low_zero_mask
            kv = (a.known_value << sh) & m
            return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))
        # 移位量可以小规模枚举时
        cands = _possible_uvals_from_bv3(shv)
        if cands is not None:
            m = (1 << y_w) - 1 if y_w > 0 else 0
            outs: List[BV3] = []
            for sh in cands:
                fill = min(int(sh), y_w)
                low_zero_mask = (1 << fill) - 1 if fill > 0 else 0
                km = ((a.known_mask << int(sh)) & m) | low_zero_mask
                kv = (a.known_value << int(sh)) & m
                outs.append(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))
            return _as_out(_join_bv3_values(outs))
        # 枚举不了时
        out_bits: List[Bit3] = []
        for i in range(y_w):
            maybe0 = bool(sh_hi > i)
            maybe1 = False

            j_lo = max(0, i - int(sh_hi))
            j_hi = min(a.width - 1, i - int(sh_lo))

            if j_lo <= j_hi:
                for j in range(j_lo, j_hi + 1):
                    bj = a.bit(j)
                    if bj is Bit3.Z0:
                        maybe0 = True
                    elif bj is Bit3.Z1:
                        maybe1 = True
                    else:
                        maybe0 = True
                        maybe1 = True
                    if maybe0 and maybe1:
                        break

            if maybe0 and not maybe1:
                out_bits.append(Bit3.Z0)
            elif maybe1 and not maybe0:
                out_bits.append(Bit3.Z1)
            else:
                out_bits.append(Bit3.X)

        return _as_out(BV3.from_bits(out_bits, signed=False).trunc(y_w))

    if op == "SHR":
        a = vec("A")
        if a.width != y_w:
            raise ValueError(...)
        shv = vec("B")
        sh_lo, sh_hi = shv.range_unsigned()
        # 移位量确定时
        if sh_lo == sh_hi:
            sh = int(sh_lo)
            if y_w <= 0:
                return _as_out(BV3(width=0, signed=False, known_mask=0, known_value=0))
            m = (1 << y_w) - 1
            fill = min(sh, y_w)
            hi_zero_mask = (((1 << fill) - 1) << (y_w - fill)) if fill > 0 else 0
            km = ((a.known_mask >> sh) & m) | hi_zero_mask
            kv = (a.known_value >> sh) & m
            return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))
        # 移位量可以小规模枚举时
        cands = _possible_uvals_from_bv3(shv)
        if cands is not None:
            m = (1 << y_w) - 1 if y_w > 0 else 0
            outs: List[BV3] = []
            for sh in cands:
                fill = min(int(sh), y_w)
                hi_zero_mask = (((1 << fill) - 1) << (y_w - fill)) if fill > 0 else 0
                km = ((a.known_mask >> int(sh)) & m) | hi_zero_mask
                kv = (a.known_value >> int(sh)) & m
                outs.append(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))
            return _as_out(_join_bv3_values(outs))
        # 枚举不了时
        out_bits: List[Bit3] = []
        for i in range(y_w):
            valid_hi = a.width - 1 - i
            maybe0 = bool(sh_hi > valid_hi)
            maybe1 = False

            j_lo = i + int(sh_lo)
            j_hi = min(a.width - 1, i + int(sh_hi))

            if j_lo <= j_hi:
                for j in range(j_lo, j_hi + 1):
                    bj = a.bit(j)
                    if bj is Bit3.Z0:
                        maybe0 = True
                    elif bj is Bit3.Z1:
                        maybe1 = True
                    else:
                        maybe0 = True
                        maybe1 = True
                    if maybe0 and maybe1:
                        break

            if maybe0 and not maybe1:
                out_bits.append(Bit3.Z0)
            elif maybe1 and not maybe0:
                out_bits.append(Bit3.Z1)
            else:
                out_bits.append(Bit3.X)

        return _as_out(BV3.from_bits(out_bits, signed=False).trunc(y_w))

    if op == "ADD":
        a = vec("A")
        b = vec("B")
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"{op} expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")
        if y_w <= 0:
            return _as_out(BV3(width=0, signed=False, known_mask=0, known_value=0))

        full = (1 << y_w) - 1
        res_signed = out_signed

        if a.known_mask == full and b.known_mask == full:
            v = (a.known_value + b.known_value) & full
            return _as_out(BV3.const(y_w, v, signed=res_signed))
        if a.known_mask == full and a.known_value == 0:
            return _as_out(BV3(width=y_w, signed=res_signed, known_mask=b.known_mask, known_value=b.known_value))
        if b.known_mask == full and b.known_value == 0:
            return _as_out(BV3(width=y_w, signed=res_signed, known_mask=a.known_mask, known_value=a.known_value))

        alo, ahi = a.range_unsigned()
        blo, bhi = b.range_unsigned()
        s_lo = alo + blo
        s_hi = ahi + bhi
        mod = 1 << y_w
        if s_hi < mod:
            return _as_out(_interval_prefix_bv3(s_lo, s_hi, y_w, res_signed))
        if s_lo >= mod:
            return _as_out(_interval_prefix_bv3(s_lo - mod, s_hi - mod, y_w, res_signed))

        out = _as_out(_add_bv3(a, b, y_w))
        return _as_out(_tighten_add_no_split(out, a, b))

    if op == "SUB":
        a = vec("A")
        b = vec("B")
        if a.width != b.width or a.width != y_w:
            raise ValueError(f"{op} expects canonical widths, got A={a.width}, B={b.width}, Y={y_w}")

        if y_w <= 0:
            return _as_out(BV3(width=0, signed=False, known_mask=0, known_value=0))

        full = (1 << y_w) - 1
        res_signed = out_signed

        if a.known_mask == full and b.known_mask == full:
            v = (a.known_value - b.known_value) & full
            return _as_out(BV3.const(y_w, v, signed=res_signed))
        if b.known_mask == full and b.known_value == 0:
            return _as_out(BV3(width=y_w, signed=res_signed, known_mask=a.known_mask, known_value=a.known_value))
        if a.known_mask == full and b.known_mask == full and a.known_value == b.known_value:
            return _as_out(BV3.const(y_w, 0, signed=res_signed))

        alo, ahi = a.range_unsigned()
        blo, bhi = b.range_unsigned()
        d_lo = alo - bhi
        d_hi = ahi - blo
        mod = 1 << y_w
        if d_lo >= 0:
            return _as_out(_interval_prefix_bv3(d_lo, d_hi, y_w, res_signed))
        if d_hi < 0:
            return _as_out(_interval_prefix_bv3(d_lo + mod, d_hi + mod, y_w, res_signed))

        out = _as_out(_sub_bv3(a, b, y_w))
        return _as_out(_tighten_sub_no_split(out, a, b))

    if op == "ASHR":
        a = vec("A")
        if a.width != y_w:
            raise ValueError(...)
        shv = vec("B")
        sh_lo, sh_hi = shv.range_unsigned()
        # 移位量确定时
        if sh_lo == sh_hi:
            sh = int(sh_lo)
            if y_w <= 0:
                return _as_out(BV3(width=0, signed=False, known_mask=0, known_value=0))
            m = (1 << y_w) - 1
            fill = min(sh, y_w)
            body_km = (a.known_mask >> sh) & m
            body_kv = (a.known_value >> sh) & m
            hi_fill_mask = (((1 << fill) - 1) << (y_w - fill)) if fill > 0 else 0
            sign_i = a.width - 1
            sign_known = ((a.known_mask >> sign_i) & 1) if a.width > 0 else 0
            sign_val = ((a.known_value >> sign_i) & 1) if a.width > 0 else 0

            km = body_km
            kv = body_kv
            if sign_known:
                km |= hi_fill_mask
                if sign_val:
                    kv |= hi_fill_mask

            return _as_out(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))
        # 移位量可以小规模枚举时
        cands = _possible_uvals_from_bv3(shv)
        if cands is not None:
            m = (1 << y_w) - 1 if y_w > 0 else 0
            sign_i = a.width - 1
            sign_known = ((a.known_mask >> sign_i) & 1) if a.width > 0 else 0
            sign_val = ((a.known_value >> sign_i) & 1) if a.width > 0 else 0

            outs: List[BV3] = []
            for sh in cands:
                fill = min(int(sh), y_w)
                body_km = (a.known_mask >> int(sh)) & m
                body_kv = (a.known_value >> int(sh)) & m
                hi_fill_mask = (((1 << fill) - 1) << (y_w - fill)) if fill > 0 else 0

                km = body_km
                kv = body_kv
                if sign_known:
                    km |= hi_fill_mask
                    if sign_val:
                        kv |= hi_fill_mask

                outs.append(BV3(width=y_w, signed=False, known_mask=km, known_value=kv))

            return _as_out(_join_bv3_values(outs))
        # 枚举不了时
        sign_bit = a.bit(a.width - 1) if a.width > 0 else Bit3.X
        out_bits: List[Bit3] = []
        for i in range(y_w):
            valid_hi = a.width - 1 - i
            maybe0 = False
            maybe1 = False

            if sh_hi > valid_hi:
                if sign_bit is Bit3.Z0:
                    maybe0 = True
                elif sign_bit is Bit3.Z1:
                    maybe1 = True
                else:
                    maybe0 = True
                    maybe1 = True

            j_lo = i + int(sh_lo)
            j_hi = min(a.width - 1, i + int(sh_hi))

            if j_lo <= j_hi:
                for j in range(j_lo, j_hi + 1):
                    bj = a.bit(j)
                    if bj is Bit3.Z0:
                        maybe0 = True
                    elif bj is Bit3.Z1:
                        maybe1 = True
                    else:
                        maybe0 = True
                        maybe1 = True
                    if maybe0 and maybe1:
                        break

            if maybe0 and not maybe1:
                out_bits.append(Bit3.Z0)
            elif maybe1 and not maybe0:
                out_bits.append(Bit3.Z1)
            else:
                out_bits.append(Bit3.X)

        return _as_out(BV3.from_bits(out_bits, signed=False).trunc(y_w))

    if op in ("LT", "LE", "GT", "GE"):
        a = vec("A")
        b = vec("B")
        if a.width != b.width:
            raise ValueError(f"{op} expects canonical widths, got A={a.width}, B={b.width}")
        signed_cmp = bool(params.get("A_SIGNED", 0) == 1) and bool(params.get("B_SIGNED", 0) == 1)
        if signed_cmp and hasattr(a, "range_signed") and hasattr(b, "range_signed"):
            alo, ahi = a.range_signed()
            blo, bhi = b.range_signed()
        else:
            alo, ahi = a.range_unsigned()
            blo, bhi = b.range_unsigned()

        def definitely_true() -> bool:
            if op == "LT":
                return ahi < blo
            if op == "LE":
                return ahi <= blo
            if op == "GT":
                return alo > bhi
            if op == "GE":
                return alo >= bhi
            return False

        def definitely_false() -> bool:
            if op == "LT":
                return alo >= bhi
            if op == "LE":
                return alo > bhi
            if op == "GT":
                return ahi <= blo
            if op == "GE":
                return ahi < blo
            return False

        if definitely_true():
            return _as_out(BV3.from_bits([Bit3.Z1]).trunc(y_w))
        if definitely_false():
            return _as_out(BV3.from_bits([Bit3.Z0]).trunc(y_w))
        return _as_out(BV3.from_bits([Bit3.X]).trunc(y_w))

    return _as_out(BV3.top(y_w))

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
    # deps[当前节点]={它依赖的那些节点}
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
    # Kahn拓扑排序
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
        outv = _eval_node(
            op,
            ports,
            params,
            env,
            out_signed=bool(n.get("out_signed", False)),
        )
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
