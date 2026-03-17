# 输入假设统一解析
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, Mapping, Optional

from src.ae.bv3 import BV3, Bit3
from src.ir.ir_types import ModuleIR

def _as_ir_dict(ir: dict | ModuleIR) -> dict:
    return ir.to_dict() if isinstance(ir, ModuleIR) else ir

def _mask(width: int) -> int:
    return (1 << width) - 1 if width > 0 else 0

def _signed_bounds(width: int) -> tuple[int, int]:
    if width <= 0:
        return (0, 0)
    return (-(1 << (width - 1)), (1 << (width - 1)) - 1)

def _interval_prefix_bv3(lo: int, hi: int, width: int, signed: bool) -> BV3:
    if width <= 0:
        return BV3(width=0, signed=signed, known_mask=0, known_value=0)
    m = _mask(width)
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

def _parse_int_range(raw: Any, name: str, field: str) -> tuple[int, int]:
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError(f"assume.{name}.{field} must be a two-element list")
    lo, hi = raw
    if not isinstance(lo, int) or isinstance(lo, bool) or not isinstance(hi, int) or isinstance(hi, bool):
        raise ValueError(f"assume.{name}.{field} elements must be integers")
    if lo > hi:
        raise ValueError(f"assume.{name}.{field} must satisfy lo <= hi")
    return int(lo), int(hi)

@dataclass(frozen=True)
class InputConstraint:
    name: str
    width: int
    signed: bool
    kind: str
    bits_msb: Optional[str] = None
    lo: Optional[int] = None
    hi: Optional[int] = None

    def domain_size(self) -> int:
        if self.kind == "bits":
            bits = self.bits_msb or ""
            return 1 << sum(1 for ch in bits if ch in ("X", "x"))
        if self.lo is None or self.hi is None:
            return 0
        return int(self.hi - self.lo + 1)

    def has_exact_bit_cube(self) -> bool:
        return self.kind == "bits"

    def bit_unknown_count(self) -> int:
        if self.kind != "bits":
            return 0
        bits = self.bits_msb or ""
        return sum(1 for ch in bits if ch in ("X", "x"))

    def display_spec(self) -> str:
        if self.kind == "bits":
            return f"bits_msb={self.bits_msb}"
        if self.kind == "range_unsigned":
            return f"range_unsigned=[{self.lo}, {self.hi}]"
        if self.kind == "range_signed":
            return f"range_signed=[{self.lo}, {self.hi}]"
        return f"{self.kind}=[{self.lo}, {self.hi}]"

    def to_bv3(self) -> BV3:
        if self.kind == "bits":
            bits_lsb = []
            for ch in reversed(self.bits_msb or ""):
                if ch == "0":
                    bits_lsb.append(Bit3.Z0)
                elif ch == "1":
                    bits_lsb.append(Bit3.Z1)
                elif ch in ("X", "x"):
                    bits_lsb.append(Bit3.X)
                else:
                    raise ValueError(f"invalid char in assume bits_msb for {self.name}: {ch}")
            return BV3.from_bits(bits_lsb, signed=self.signed)

        if self.kind == "range_unsigned":
            assert self.lo is not None and self.hi is not None
            return _interval_prefix_bv3(self.lo, self.hi, self.width, self.signed)

        if self.kind == "range_signed":
            assert self.lo is not None and self.hi is not None
            mod = 1 << self.width if self.width > 0 else 1
            if self.hi < 0:
                return _interval_prefix_bv3(self.lo + mod, self.hi + mod, self.width, self.signed)
            if self.lo >= 0:
                return _interval_prefix_bv3(self.lo, self.hi, self.width, self.signed)

            neg = _interval_prefix_bv3(self.lo + mod, mod - 1, self.width, self.signed)
            pos = _interval_prefix_bv3(0, self.hi, self.width, self.signed)
            return neg.join(pos)

        raise ValueError(f"unsupported constraint kind for {self.name}: {self.kind}")

    def iter_unsigned_values(self) -> Iterator[int]:
        if self.kind == "bits":
            bits_lsb = list(reversed(self.bits_msb or ""))
            unknown_idx = [i for i, ch in enumerate(bits_lsb) if ch in ("X", "x")]
            base = 0
            for i, ch in enumerate(bits_lsb):
                if ch == "1":
                    base |= (1 << i)
                elif ch not in ("0", "X", "x"):
                    raise ValueError(f"invalid char in assume bits_msb for {self.name}: {ch}")
            for mask_bits in range(1 << len(unknown_idx)):
                value = base
                for j, bit_i in enumerate(unknown_idx):
                    if (mask_bits >> j) & 1:
                        value |= (1 << bit_i)
                    else:
                        value &= ~(1 << bit_i)
                yield value & _mask(self.width)
            return

        if self.kind == "range_unsigned":
            assert self.lo is not None and self.hi is not None
            for value in range(self.lo, self.hi + 1):
                yield value & _mask(self.width)
            return

        if self.kind == "range_signed":
            assert self.lo is not None and self.hi is not None
            for value in range(self.lo, self.hi + 1):
                yield value & _mask(self.width)
            return

        raise ValueError(f"unsupported constraint kind for {self.name}: {self.kind}")


def parse_input_constraints(ir: dict | ModuleIR, assume: Optional[dict]) -> Dict[str, InputConstraint]:
    ir = _as_ir_dict(ir)
    sigs = ir.get("signals", []) or []
    signal_map = {
        s.get("name"): s for s in sigs if isinstance(s, dict) and isinstance(s.get("name"), str)
    }
    input_map = {
        s.get("name"): s
        for s in sigs
        if isinstance(s, dict) and s.get("kind") == "input" and isinstance(s.get("name"), str)
    }

    assume_sigs: Mapping[str, Any] = {}
    if assume:
        assume_sigs = assume.get("signals", {}) or {}
        if not isinstance(assume_sigs, Mapping):
            raise ValueError("assume.signals must be an object")
        for name in assume_sigs.keys():
            if name not in signal_map:
                raise ValueError(f"assume signal not found in IR: {name}")
            if name not in input_map:
                raise ValueError(f"assume only supports input signals currently: {name}")

    out: Dict[str, InputConstraint] = {}
    for name, sig in input_map.items():
        width = len(sig.get("bits", []) or [])
        signed = bool(sig.get("signed", False))
        spec = assume_sigs.get(name)
        out[name] = _parse_one_constraint(name, width, signed, spec)
    return out

def _parse_one_constraint(name: str, width: int, signed: bool, spec: Any) -> InputConstraint:
    if spec is None:
        return InputConstraint(name=name, width=width, signed=signed, kind="bits", bits_msb=("X" * width))

    if isinstance(spec, str):
        bits_msb = spec
        _validate_bits_msb(name, bits_msb, width)
        return InputConstraint(name=name, width=width, signed=signed, kind="bits", bits_msb=bits_msb)

    if not isinstance(spec, Mapping):
        raise ValueError(f"assume spec must be string or object: {name}")

    keys = [k for k in ("bits_msb", "range", "range_unsigned", "range_signed") if k in spec]
    if len(keys) == 0:
        raise ValueError(
            f"assume.{name} must provide one of bits_msb/range/range_unsigned/range_signed"
        )
    if len(keys) > 1:
        raise ValueError(f"assume.{name} must use exactly one input constraint form")

    field = keys[0]
    if field == "bits_msb":
        bits_msb = spec.get("bits_msb")
        if not isinstance(bits_msb, str):
            raise ValueError(f"assume.{name}.bits_msb must be string")
        _validate_bits_msb(name, bits_msb, width)
        return InputConstraint(name=name, width=width, signed=signed, kind="bits", bits_msb=bits_msb)

    key = field
    if field == "range":
        key = "range_signed" if signed else "range_unsigned"

    lo, hi = _parse_int_range(spec.get(field), name, field)

    if key == "range_unsigned":
        max_u = _mask(width)
        if lo < 0 or hi > max_u:
            raise ValueError(f"assume.{name}.range_unsigned must be within [0, {max_u}]")
        return InputConstraint(name=name, width=width, signed=signed, kind="range_unsigned", lo=lo, hi=hi)

    s_lo, s_hi = _signed_bounds(width)
    if lo < s_lo or hi > s_hi:
        raise ValueError(f"assume.{name}.range_signed must be within [{s_lo}, {s_hi}]")
    return InputConstraint(name=name, width=width, signed=signed, kind="range_signed", lo=lo, hi=hi)


def _validate_bits_msb(name: str, bits_msb: str, width: int) -> None:
    if len(bits_msb) != width:
        raise ValueError(
            f"assume width mismatch for {name}: bits_msb len={len(bits_msb)} IR width={width}"
        )
    for ch in bits_msb:
        if ch not in ("0", "1", "X", "x"):
            raise ValueError(f"invalid char in assume bits_msb for {name}: {ch}")
