# 读取 Yosys write_json 输出，提供基础解析与映射工具

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

CELL_TYPE_TO_OP: Dict[str, str] = {
    "$and": "AND",
    "$or": "OR",
    "$xor": "XOR",
    "$not": "NOT",
    "$mux": "MUX",
    "$add": "ADD",
    "$sub": "SUB",
    "$slice": "EXTRACT",
    "$concat": "CONCAT",
    "$shl": "SHL",
    "$shr": "SHR",
    "$eq": "EQ",
    "$sshr": "ASHR",
    "$lt": "LT",
    "$le": "LE",
    "$gt": "GT",
    "$ge": "GE"
}

# design.v:7.19-7.24
_SRC_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<ls>\d+)\.(?P<cs>\d+)-(?P<le>\d+)\.(?P<ce>\d+)$"
)

# 从Yosys JSON中选择顶层模块
def pick_top_module(yosys_obj: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    modules = yosys_obj.get("modules", {})
    if not isinstance(modules, dict) or len(modules) == 0:
        raise ValueError("Invalid Yosys JSON: missing or empty 'modules'")
    # 若只有一个module，直接返回
    if len(modules) == 1:
        name = next(iter(modules.keys()))
        return name, modules[name]
    # 否则尝试找attributes.top非零的模块
    for name, mod in modules.items():
        attrs = (mod or {}).get("attributes", {}) if isinstance(mod, dict) else {}
        top_raw = attrs.get("top")
        if isinstance(top_raw, str):
            try:
                if int(top_raw, 2) != 0:
                    return name, mod
            except ValueError:
                pass
    name = next(iter(modules.keys()))
    return name, modules[name]

# 将Yosys参数里的32位二进制字符串解码为整数
def decode_bin32(raw: Any) -> int:
    if raw is None:
        raise ValueError("decode_bin32: raw is None")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        s = raw.strip().replace("_", "")
        if s == "":
            return 0
        if all(ch in "01" for ch in s):
            return int(s, 2)
        return int(s)

    return int(raw)

# 解析Yosys的src字符串为SrcSpan
def parse_src_span(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    m = _SRC_RE.match(raw)
    if not m:
        return {"raw": raw}
    return {
        "file": m.group("file"),
        "line_start": int(m.group("ls")),
        "col_start": int(m.group("cs")),
        "line_end": int(m.group("le")),
        "col_end": int(m.group("ce")),
        "raw": raw,
    }

# 将Yosys bits元素统一转成BitRef
def to_bitref(x: Any) -> Dict[str, Any]:
    if isinstance(x, int):
        return {"kind": "wire", "id": x}
    if isinstance(x, str):
        return {"kind": "const", "val": x}
    raise TypeError(f"Unsupported bit type: {type(x)}  value={x!r}")

# 将Yosys cell type映射为核心算子op
def map_cell_type_to_op(yosys_type: str) -> str:
    return CELL_TYPE_TO_OP.get(yosys_type, "UNSUPPORTED")