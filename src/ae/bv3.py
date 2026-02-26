from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, List

class Bit3(Enum):
    Z0 = 0
    Z1 = 1
    X = 2

    def __str__(self) -> str:
        return "0" if self is Bit3.Z0 else "1" if self is Bit3.Z1 else "X"

# 生成低width位全1的掩码
def _mask(width: int) -> int:
    return (1 << width) - 1 if width > 0 else 0

# 统计整数二进制里1的个数
def _popcount(x: int) -> int:
    return x.bit_count()

@dataclass(frozen=True)
# 3值位向量抽象：
# 用known_mask标记哪些位是确定的
# 用known_value给出这些确定位的值
class BV3:
    width: int
    signed: bool = False
    known_mask: int = 0
    known_value: int = 0

    # ----------构造函数----------
    @staticmethod
    def top(width: int, signed: bool = False) -> "BV3":
        return BV3(width=width, signed=signed, known_mask=0, known_value=0)

    @staticmethod
    def const(width: int, value: int, signed: bool = False) -> "BV3":
        m = _mask(width)
        v = value & m
        return BV3(width=width, signed=signed, known_mask=m, known_value=v)

    @staticmethod
    def from_bits(bits_lsb_first: List[Bit3], signed: bool = False) -> "BV3":
        km = 0
        kv = 0
        for i, b in enumerate(bits_lsb_first):
            if b is Bit3.Z0:
                km |= (1 << i)
            elif b is Bit3.Z1:
                km |= (1 << i)
                kv |= (1 << i)
            else:
                pass
        return BV3(width=len(bits_lsb_first), signed=signed, known_mask=km, known_value=kv)

    # ----------派生属性----------
    @property
    def unknown_mask(self) -> int:
        return (~self.known_mask) & _mask(self.width)

    @property
    def unknown_count(self) -> int:
        return _popcount(self.unknown_mask)

    def bit(self, i: int) -> Bit3:
        if i < 0 or i >= self.width:
            raise IndexError("bit index out of range")
        if (self.known_mask >> i) & 1 == 0:
            return Bit3.X
        return Bit3.Z1 if ((self.known_value >> i) & 1) else Bit3.Z0

    def to_bits(self) -> List[Bit3]:
        return [self.bit(i) for i in range(self.width)]

    def to_str_msb(self) -> str:
        return "".join(str(self.bit(i)) for i in reversed(range(self.width)))
    
    # ----------偏序与合并----------
    def leq(self, other: "BV3") -> bool:
        # 精度比较：self是否比other更精确（集合更小）。
        # 条件：other已知的位，self必须也已知且一致。
        if self.width != other.width:
            return False
        if self.signed != other.signed:
            # signed不同就当不可比
            return False
        # other.mask ⊆ self.mask
        if (other.known_mask & ~self.known_mask) != 0:
            return False
        # 在other已知位上，值要一致
        if ((self.known_value ^ other.known_value) & other.known_mask) != 0:
            return False
        return True

    def join(self, other: "BV3") -> "BV3":
        # 合并：保留双方都已知且值相同的位，其余变为未知。
        a, b = BV3.align_pair(self, other, policy="zext")
        same = ~(a.known_value ^ b.known_value) & _mask(a.width)
        km = a.known_mask & b.known_mask & same
        kv = a.known_value & km
        return BV3(width=a.width, signed=a.signed, known_mask=km, known_value=kv)

    # ----------位宽对齐----------
    # 截断到更小宽度
    def trunc(self, new_width: int) -> "BV3":
        if new_width < 0:
            raise ValueError("new_width must be >= 0")
        if new_width >= self.width:
            return self
        m = _mask(new_width)
        return BV3(
            width=new_width,
            signed=self.signed,
            known_mask=self.known_mask & m,
            known_value=self.known_value & m,
        )
    
    # 零扩展：新增高位全为已知0
    def zext(self, new_width: int) -> "BV3":
        if new_width < self.width:
            return self.trunc(new_width)
        add = new_width - self.width
        if add == 0:
            return self
        hi_mask = ((_mask(add)) << self.width)
        km = self.known_mask | hi_mask
        kv = self.known_value
        return BV3(width=new_width, signed=self.signed, known_mask=km, known_value=kv)

    # 符号扩展
    def sext(self, new_width: int) -> "BV3":
        if new_width < self.width:
            return self.trunc(new_width)
        add = new_width - self.width
        if add == 0:
            return self
        sign_i = self.width - 1
        sign_known = (self.known_mask >> sign_i) & 1
        sign_val = (self.known_value >> sign_i) & 1
        hi_mask = ((1 << add) - 1) << self.width
        if sign_known == 0:
            # 符号位未知：扩展出来的高位全部未知
            km = self.known_mask
            kv = self.known_value
            return BV3(width=new_width, signed=self.signed, known_mask=km, known_value=kv)
        # 符号位已知：扩展出来的高位全部等于符号位
        km = self.known_mask | hi_mask
        if sign_val == 1:
            kv = self.known_value | hi_mask
        else:
            kv = self.known_value
        return BV3(width=new_width, signed=self.signed, known_mask=km, known_value=kv)

    @staticmethod
    # 对齐两操作数宽度
    def align_pair(a: "BV3", b: "BV3", policy: str = "zext") -> Tuple["BV3", "BV3"]:
        if policy not in ("zext", "sext", "trunc"):
            raise ValueError("policy must be 'zext', 'sext' or 'trunc'")
        if policy == "zext":
            w = max(a.width, b.width)
            return a.zext(w), b.zext(w)
        elif policy == "sext":
            w = max(a.width, b.width)
            return a.sext(w), b.sext(w)
        else:
            w = min(a.width, b.width)
            return a.trunc(w), b.trunc(w)

    # ----------范围推导----------
    def range_unsigned(self) -> Tuple[int, int]:
        # 从已知位派生无符号范围
        # min：未知位按0
        # max：未知位按1
        m = _mask(self.width)
        umin = self.known_value & m
        umax = (self.known_value | self.unknown_mask) & m
        return umin, umax
    
    def range_signed(self) -> tuple[int, int]:
        w = self.width
        if w == 0:
            return (0, 0)

        umin, umax = self.range_unsigned()
        sign_i = w - 1
        sign_known = (self.known_mask >> sign_i) & 1
        sign_val = (self.known_value >> sign_i) & 1
        lo = -(1 << (w - 1))
        hi = (1 << (w - 1)) - 1
        # sign未知：直接返回整个signed范围
        if sign_known == 0:
            return (lo, hi)
        if sign_val == 0:
            # 非负，signed范围等同unsigned范围
            return (umin, umax)
        # 负数：unsigned映射到signed需要减2^w
        mod = 1 << w
        return (umin - mod, umax - mod)

    def to_dict(self) -> dict:
        umin, umax = self.range_unsigned()
        return {
            "width": self.width,
            "signed": self.signed,
            "bits_msb": self.to_str_msb(),
            "known_mask_hex": hex(self.known_mask),
            "known_value_hex": hex(self.known_value),
            "unknown_count": self.unknown_count,
            "range_unsigned": [umin, umax],
            "range_signed": list(self.range_signed()),
        }