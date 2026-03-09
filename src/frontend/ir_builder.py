# 将Yosys JSON转换为IR
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from src.ir.ir_types import ModuleIR
from src.frontend.yosys_json_reader import (
    pick_top_module,
    decode_bin32,
    parse_src_span,
    to_bitref,
    map_cell_type_to_op,
)

# 从Yosys JSON构建ModuleIR（dataclass）
def build_module_ir(yosys_obj: Dict[str, Any]) -> ModuleIR:
    top_name, top_mod = pick_top_module(yosys_obj)
    creator = yosys_obj.get("creator", "")
    signals = build_signals(top_mod)
    nodes = build_nodes(top_mod)
    bit_index = build_bit_index(signals, nodes, top_mod)
    outputs = _build_outputs(signals)
    src_files = _collect_src_files(top_mod, signals, nodes)
    ir = {
        "ir_version": "0.1",
        "source_format": "yosys_write_json",
        "source_creator": creator,
        "top_module": top_name,
        "src_files": sorted(list(src_files)),
        "signals": signals,
        "nodes": nodes,
        "outputs": outputs,
        "bit_index": bit_index,
    }
    return ModuleIR.from_dict(ir)

def build_module_ir_dict(yosys_obj: Dict[str, Any]) -> Dict[str, Any]:
    return build_module_ir(yosys_obj).to_dict()

# 构建signals表
def build_signals(top_mod: Dict[str, Any]) -> List[Dict[str, Any]]:
    ports = top_mod.get("ports", {}) or {}
    netnames = top_mod.get("netnames", {}) or {}
    sig_map: Dict[str, Dict[str, Any]] = {}

    # netnames->signals（先都当wire）
    for name, nn in netnames.items():
        bits_raw = nn.get("bits", [])
        bits = [to_bitref(b) for b in bits_raw]
        src_raw = (nn.get("attributes", {}) or {}).get("src")
        signed_flag = 1 if nn.get("signed", 0) == 1 else 0
        sig_map[name] = {
            "sid": name,
            "name": name,
            "kind": "wire",
            "width": len(bits),
            "signed": bool(signed_flag),
            "bits": bits,
            "src": parse_src_span(src_raw),
            "alias_of": None,
        }

    # ports覆盖kind或补建，同时覆盖signed
    for pname, p in ports.items():
        direction = p.get("direction")
        if direction == "input":
            kind = "input"
        elif direction == "output":
            kind = "output"
        else:
            kind = "wire"

        bits_raw = p.get("bits", [])
        bits = [to_bitref(b) for b in bits_raw]
        port_signed = bool(p.get("signed", 0) == 1)
        if pname in sig_map:
            sig_map[pname]["kind"] = kind
            # 端口信息优先
            sig_map[pname]["signed"] = port_signed or bool(sig_map[pname].get("signed", False))
            if sig_map[pname]["width"] != len(bits):
                sig_map[pname]["width"] = len(bits)
                sig_map[pname]["bits"] = bits
        else:
            sig_map[pname] = {
                "sid": pname,
                "name": pname,
                "kind": kind,
                "width": len(bits),
                "signed": port_signed,
                "bits": bits,
                "src": None,
                "alias_of": None,
            }

    return list(sig_map.values())

# 构建nodes表: 每个cell一个Node
def build_nodes(top_mod: Dict[str, Any]) -> List[Dict[str, Any]]:
    cells = top_mod.get("cells", {}) or {}
    if not isinstance(cells, dict):
        raise ValueError("Invalid Yosys JSON: modules[top].cells is not a dict")
    ports = top_mod.get("ports", {}) or {}
    netnames = top_mod.get("netnames", {}) or {}
    # wire bit id -> signed(bool)
    bit_signed_true: Dict[int, bool] = {}
    bit_declared: Set[int] = set()

    def _mark_bits_decl(bits_raw: List[Any], signed: bool) -> None:
    # 无论signed与否，只要声明里出现过，就记为declared
        for b in bits_raw or []:
            br = to_bitref(b)
            if br.get("kind") != "wire":
                continue
            bid = int(br["id"])
            bit_declared.add(bid)
            if signed:
                bit_signed_true[bid] = True

    # netnames
    for _n, nn in netnames.items():
        _mark_bits_decl(nn.get("bits", []) or [], bool(nn.get("signed", 0) == 1))

    # ports
    for _n, p in ports.items():
         _mark_bits_decl(p.get("bits", []) or [], bool(p.get("signed", 0) == 1))

    # 从输出端反推节点的out_signed
    def _infer_out_signed_from_Y(
        ports_obj: Dict[str, List[Dict[str, Any]]]
    ) -> Optional[bool]:
        y_bits = ports_obj.get("Y", []) or []
        y_wire_ids: List[int] = []
        for br in y_bits:
            if br.get("kind") != "wire":
                continue
            y_wire_ids.append(int(br["id"]))

        if not y_wire_ids:
            return None

        # 向量级完全匹配：如果某个netname/port的bits序列完全等于Y，就用它的signed
        def _bits_ids(bits_raw: List[Any]) -> List[int]:
            ids: List[int] = []
            for b in bits_raw or []:
                br = to_bitref(b)
                if br.get("kind") == "wire":
                    ids.append(int(br["id"]))
            return ids

        for _n, nn in netnames.items():
            if _bits_ids(nn.get("bits", []) or []) == y_wire_ids:
                return bool(nn.get("signed", 0) == 1)
        for _n, p in ports.items():
            if _bits_ids(p.get("bits", []) or []) == y_wire_ids:
                return bool(p.get("signed", 0) == 1)

        # bit级一致性
        saw_declared = False
        all_signed = True
        all_unsigned = True
        for bid in y_wire_ids:
            if bid in bit_declared:
                saw_declared = True
            # 若某位属于signed net，则这一位signed
            is_signed_bit = (bid in bit_signed_true)
            all_signed = all_signed and is_signed_bit
            all_unsigned = all_unsigned and (not is_signed_bit)

        if saw_declared:
            if all_signed:
                return True
            if all_unsigned:
                return False
            # 不确定
            return None

        return None
    
    nodes: List[Dict[str, Any]] = []
    # 按cell_name排序
    cell_items = sorted(cells.items(), key=lambda kv: kv[0])
    nid_counter = 0
    for cell_name, c in cell_items:
        nid_counter += 1
        nid = f"n{nid_counter}"
        yosys_type = c.get("type", "")
        op = map_cell_type_to_op(yosys_type)
        ports_obj: Dict[str, List[Dict[str, Any]]] = {}
        connections = c.get("connections", {}) or {}
        for port_name, conn_bits in connections.items():
            ports_obj[port_name] = [to_bitref(b) for b in (conn_bits or [])]
        # params二进制字符串解码为int
        params_raw = c.get("parameters", {}) or {}
        params: Dict[str, Any] = {}
        for k, v in params_raw.items():
            try:
                params[k] = decode_bin32(v)
            except Exception:
                params[k] = v
        # src节点位置
        src_raw = (c.get("attributes", {}) or {}).get("src")
        src = parse_src_span(src_raw)
        node: Dict[str, Any] = {
            "nid": nid,
            "op": op,
            "yosys_type": yosys_type,
            "yosys_name": cell_name,
            "ports": ports_obj,
            "params": params,
            "src": src,
        }
        out_width = _guess_out_width(node)
        node["out_width"] = out_width
        # out_signed推导：先从Y连接到的net/port声明推导；再退化到params推导
        out_signed_decl = _infer_out_signed_from_Y(ports_obj)
        if out_signed_decl is not None:
            node["out_signed"] = out_signed_decl
        else:
            # 根据运算语义推导
            a_signed = bool(params.get("A_SIGNED", 0) == 1)
            b_signed = bool(params.get("B_SIGNED", 0) == 1)
            if op in ("LT", "LE", "GT", "GE", "EQ"):
                node["out_signed"] = False
            elif op in ("SHL", "SHR", "ASHR"):
                node["out_signed"] = a_signed
            elif op in ("ADD", "SUB"):
                node["out_signed"] = a_signed or b_signed
            else:
                node["out_signed"] = False
        node["args"] = _normalize_args(node)
        nodes.append(node)
    # 若cells没生成EXTRACT/CONCAT（常被优化成纯连线），则从netnames/ports补view节点
    has_extract = any(n.get("op") == "EXTRACT" for n in nodes)
    has_concat  = any(n.get("op") == "CONCAT"  for n in nodes)
    want_extract = not has_extract
    want_concat  = not has_concat
    if want_extract or want_concat:
        nodes, nid_counter = _synth_view_nodes_from_wiring(
            top_mod,
            nodes,
            nid_counter,
            want_extract=want_extract,
            want_concat=want_concat,
        )
    return nodes

# 构建bit_index.wire_bits
def build_bit_index(
    signals: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
    top_mod: Dict[str, Any],
) -> Dict[str, Any]:
    owners_map: Dict[str, Set[str]] = {}
    for s in signals:
        sname = s.get("name")
        for br in s.get("bits", []):
            if br.get("kind") != "wire":
                continue
            bid = str(br.get("id"))
            owners_map.setdefault(bid, set()).add(sname)
    # driver：先写input ports，再写node outputs
    drivers: Dict[str, Optional[Dict[str, Any]]] = {}
    ports = top_mod.get("ports", {}) or {}
    for pname, p in ports.items():
        if p.get("direction") != "input":
            continue
        for b in p.get("bits", []) or []:
            br = to_bitref(b)
            if br.get("kind") != "wire":
                continue
            bid = str(br["id"])
            drivers[bid] = {"kind": "port", "name": pname}
    uses: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        nid = n.get("nid")
        ports_obj = n.get("ports", {}) or {}
        for port_name, bit_list in ports_obj.items():
            for br in bit_list or []:
                if br.get("kind") != "wire":
                    continue
                bid = str(br["id"])
                if port_name == "Y":
                    if not n.get("is_view", False):
                    # 输出端口：driver
                        drivers[bid] = {"kind": "node", "nid": nid, "port": "Y"}
                else:
                    # 输入端口：uses
                    uses.setdefault(bid, []).append(
                        {"kind": "node", "nid": nid, "port": port_name}
                    )
    # 汇总所有出现过的wire bit id
    all_ids: Set[str] = set()
    all_ids |= set(owners_map.keys())
    all_ids |= set(drivers.keys())
    all_ids |= set(uses.keys())
    wire_bits: Dict[str, Any] = {}
    for bid in sorted(all_ids, key=lambda x: int(x) if x.isdigit() else x):
        wire_bits[bid] = {
            "owners": sorted(list(owners_map.get(bid, set()))),
            "driver": drivers.get(bid),
            "uses": uses.get(bid, []),
        }
    return {"wire_bits": wire_bits}

def _build_outputs(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    outputs: Dict[str, Any] = {}
    for s in signals:
        if s.get("kind") == "output":
            outputs[s["name"]] = {"bits": s.get("bits", [])}
    return outputs

def _guess_out_width(node: Dict[str, Any]) -> int:
    params = node.get("params", {}) or {}
    if "Y_WIDTH" in params and isinstance(params["Y_WIDTH"], int):
        return params["Y_WIDTH"]
    if "WIDTH" in params and isinstance(params["WIDTH"], int):
        return params["WIDTH"]
    ports_obj = node.get("ports", {}) or {}
    y_bits = ports_obj.get("Y", [])
    return len(y_bits)

def _normalize_args(node: Dict[str, Any]) -> Dict[str, Any]:
    op = node.get("op")
    ports_obj = node.get("ports", {}) or {}

    if op == "MUX":
        # Yosys $mux: S=0选A, S=1选 B
        return {
            "cond": ports_obj.get("S", []),
            "else": ports_obj.get("A", []),
            "then": ports_obj.get("B", []),
            "out": ports_obj.get("Y", []),
        }
    if op == "PMUX":
        # Yosys $pmux:S全0选A，S[i]=1选B的第i段
        return {
            "sel": ports_obj.get("S", []),
            "default": ports_obj.get("A", []),
            "cases": ports_obj.get("B", []),
            "out": ports_obj.get("Y", []),
        }
    
    if op in ("AND", "OR", "XOR", "ADD", "SUB", "EQ", "LT", "LE", "GT", "GE"):
        return {
            "lhs": ports_obj.get("A", []),
            "rhs": ports_obj.get("B", []),
            "out": ports_obj.get("Y", []),
        }

    if op in ("NOT", "LOGIC_NOT"):
        return {
            "in": ports_obj.get("A", []),
            "out": ports_obj.get("Y", []),
        }
    
    if op == "EXTRACT":
        return {
            "in":  ports_obj.get("A", []),
            "out": ports_obj.get("Y", []),
        }

    if op == "CONCAT":
        return {
            "low":  ports_obj.get("A", []),
            "high": ports_obj.get("B", []),
            "out":  ports_obj.get("Y", []),
        }

    if op in ("SHL", "SHR", "ASHR"):
        # lhs是被移位数（A），rhs是移位量（B）
        return {
            "value": ports_obj.get("A", []),
            "shift": ports_obj.get("B", []),
            "out": ports_obj.get("Y", []),
        }

    return {}

# 收集出现过的源文件名，用于ModuleIR.src_files
def _collect_src_files(
    top_mod: Dict[str, Any],
    signals: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
) -> Set[str]:
    files: Set[str] = set()
    def add_from_span(span: Optional[Dict[str, Any]]) -> None:
        if not span:
            return
        f = span.get("file")
        if isinstance(f, str) and f:
            files.add(f)
        else:
            raw = span.get("raw")
            if isinstance(raw, str) and ":" in raw:
                files.add(raw.split(":", 1)[0])
    mod_src_raw = (top_mod.get("attributes", {}) or {}).get("src")
    add_from_span(parse_src_span(mod_src_raw))
    for s in signals:
        add_from_span(s.get("src"))
    for n in nodes:
        add_from_span(n.get("src"))

    return files

# 按bits序列找信号
def _bits_key(bits: list[dict]) -> tuple:
    out = []
    for br in bits:
        k = br.get("kind")
        if k == "wire":
            out.append(("w", br.get("id")))
        else:
            out.append(("c", br.get("val")))
    return tuple(out)

def _build_name_to_bits(top_mod: dict) -> dict[str, list[dict]]:
    m: dict[str, list[dict]] = {}
    netnames = top_mod.get("netnames", {}) or {}
    ports = top_mod.get("ports", {}) or {}
    for name, nn in netnames.items():
        m[name] = [to_bitref(b) for b in (nn.get("bits", []) or [])]
    for name, p in ports.items():
        if name not in m:
            m[name] = [to_bitref(b) for b in (p.get("bits", []) or [])]
    return m

def _build_port_dirs(top_mod: dict) -> dict[str, str]:
    ports = top_mod.get("ports", {}) or {}
    d: dict[str, str] = {}
    for name, p in ports.items():
        d[name] = p.get("direction", "")
    return d

def _find_contiguous_slice(parent_bits: list[dict], child_bits: list[dict]) -> int | None:
    w = len(child_bits)
    if w == 0 or w > len(parent_bits):
        return None
    for off in range(0, len(parent_bits) - w + 1):
        if parent_bits[off:off + w] == child_bits:
            return off
    return None

def _synth_view_nodes_from_wiring(
    top_mod: dict,
    nodes: list[dict],
    nid_counter: int,
    want_extract: bool = True,
    want_concat: bool = True,
) -> tuple[list[dict], int]:
    name_to_bits = _build_name_to_bits(top_mod)
    port_dirs = _build_port_dirs(top_mod)
    # 反向索引：bits序列->signal name（用于拼接时匹配lo/hi）
    bits_to_name: dict[tuple, str] = {}
    for n, bits in name_to_bits.items():
        bits_to_name[_bits_key(bits)] = n
    netnames = top_mod.get("netnames", {}) or {}
    ports = top_mod.get("ports", {}) or {}
    bit_signed_true: dict[int, bool] = {}
    bit_declared: set[int] = set()

    def _mark_bits_decl(bits_raw, signed: bool) -> None:
        for b in bits_raw or []:
            br = to_bitref(b)
            if br.get("kind") != "wire":
                continue
            bid = int(br["id"])
            bit_declared.add(bid)
            if signed:
                bit_signed_true[bid] = True

    for _n, nn2 in netnames.items():
        _mark_bits_decl(nn2.get("bits", []) or [], bool(nn2.get("signed", 0) == 1))

    for _n, p2 in ports.items():
        _mark_bits_decl(p2.get("bits", []) or [], bool(p2.get("signed", 0) == 1))

    def _infer_out_signed_from_Y_bits(y_bits: list[dict]) -> Optional[bool]:
        y_wire_ids: list[int] = []
        for br in y_bits or []:
            if br.get("kind") != "wire":
                continue
            y_wire_ids.append(int(br["id"]))
        if not y_wire_ids:
            return None

        # 向量级完全匹配：若某个netname/port的bits序列完全等于Y，就用它的signed
        def _bits_ids(bits_raw) -> list[int]:
            ids: list[int] = []
            for b in bits_raw or []:
                br = to_bitref(b)
                if br.get("kind") == "wire":
                    ids.append(int(br["id"]))
            return ids

        for _n, nn2 in netnames.items():
            if _bits_ids(nn2.get("bits", []) or []) == y_wire_ids:
                return bool(nn2.get("signed", 0) == 1)
        for _n, p2 in ports.items():
            if _bits_ids(p2.get("bits", []) or []) == y_wire_ids:
                return bool(p2.get("signed", 0) == 1)

        # bit级一致性
        saw_declared = False
        all_signed = True
        all_unsigned = True
        for bid in y_wire_ids:
            if bid in bit_declared:
                saw_declared = True
            is_signed_bit = (bid in bit_signed_true)
            all_signed = all_signed and is_signed_bit
            all_unsigned = all_unsigned and (not is_signed_bit)

        if saw_declared:
            if all_signed:
                return True
            if all_unsigned:
                return False
            return None 

        return None
    
    # 合成EXTRACT：对每个内部网线，找一个input端口作为父向量
    if want_extract:
        for child_name, nn in netnames.items():
            # 跳过端口本身
            if child_name in port_dirs:
                continue
            child_bits = name_to_bits.get(child_name, [])
            if not child_bits:
                continue
            # 先在input端口里找父向量
            parent_candidates = [p for p, d in port_dirs.items() if d == "input"]
            parent_found = None
            offset_found = None
            for parent_name in parent_candidates:
                parent_bits = name_to_bits.get(parent_name, [])
                off = _find_contiguous_slice(parent_bits, child_bits)
                if off is not None:
                    parent_found = parent_name
                    offset_found = off
                    break
            if parent_found is None:
                continue
            nid_counter += 1
            nid = f"n{nid_counter}"
            src_raw = (nn.get("attributes", {}) or {}).get("src")
            node = {
                "nid": nid,
                "op": "EXTRACT",
                "yosys_type": "$slice",
                "yosys_name": f"$synth$slice${child_name}",
                "ports": {
                    "A": name_to_bits[parent_found],
                    "Y": child_bits,
                },
                "params": {
                    "A_WIDTH": len(name_to_bits[parent_found]),
                    "Y_WIDTH": len(child_bits),
                    "OFFSET": offset_found,
                },
                "src": parse_src_span(src_raw),
                "is_view": True,
            }
            node["out_width"] = len(child_bits)
            node["out_signed"] = _infer_out_signed_from_Y_bits(node["ports"]["Y"])
            node["args"] = _normalize_args(node)
            nodes.append(node)

    # 合成CONCAT：对output端口和netnames，拆成两段，各自匹配某个信号bits
    if want_concat:
        made: set[tuple] = set()
        def _is_all_const(bits: list[dict]) -> bool:
            return len(bits) > 0 and all(br.get("kind") == "const" for br in bits)

        def _is_repeat(bits: list[dict]) -> bool:
            if len(bits) <= 1:
                return False
            first = bits[0]
            if first.get("kind") == "wire":
                fid = first.get("id")
                return all(br.get("kind") == "wire" and br.get("id") == fid for br in bits)
            if first.get("kind") == "const":
                fv = first.get("val")
                return all(br.get("kind") == "const" and br.get("val") == fv for br in bits)
            return False

        def _chunk_ok(bits: list[dict]) -> bool:
            # 能匹配到某个已命名信号
            if _bits_key(bits) in bits_to_name:
                return True
            # 常量段：如0000
            if _is_all_const(bits):
                return True
            # 重复段：如 {4{s[3]}}
            if _is_repeat(bits):
                return True
            return False

        def _try_split_concat(target_bits: list[dict]) -> Optional[tuple[list[dict], list[dict]]]:
            if len(target_bits) < 2:
                return None
            for k in range(1, len(target_bits)):
                low_bits = target_bits[0:k]
                high_bits = target_bits[k:]
                if _chunk_ok(low_bits) and _chunk_ok(high_bits):
                    return (low_bits, high_bits)
            return None

        targets: list[tuple[str, list[dict], Optional[str]]] = []

        # output ports
        for out_name, d in port_dirs.items():
            if d != "output":
                continue
            out_bits = name_to_bits.get(out_name, [])
            if not out_bits:
                continue
            out_nn = (netnames.get(out_name) or {})
            out_src_raw = ((out_nn.get("attributes", {}) or {}).get("src"))
            targets.append((out_name, out_bits, out_src_raw))

        # netnames
        for net_name, nn in netnames.items():
            if net_name in port_dirs:
                continue  # 排除端口名（input/output）
            bits = name_to_bits.get(net_name, [])
            if not bits:
                continue
            src_raw = ((nn.get("attributes", {}) or {}).get("src"))
            targets.append((net_name, bits, src_raw))

        # 生成CONCAT节点
        for tgt_name, tgt_bits, tgt_src_raw in targets:
            key = _bits_key(tgt_bits)
            if key in made:
                continue

            found = _try_split_concat(tgt_bits)
            if not found:
                continue
            low_bits, high_bits = found

            nid_counter += 1
            nid = f"n{nid_counter}"
            node = {
                "nid": nid,
                "op": "CONCAT",
                "yosys_type": "$concat",
                "yosys_name": f"$synth$concat${tgt_name}",
                "ports": {
                    "A": low_bits,
                    "B": high_bits,
                    "Y": tgt_bits,
                },
                "params": {
                    "A_WIDTH": len(low_bits),
                    "B_WIDTH": len(high_bits),
                    "Y_WIDTH": len(tgt_bits),
                },
                "src": parse_src_span(tgt_src_raw),
                "is_view": True,
            }
            node["out_width"] = len(tgt_bits)
            node["out_signed"] = bool(_infer_out_signed_from_Y_bits(node["ports"]["Y"]))
            node["args"] = _normalize_args(node)

            nodes.append(node)
            made.add(key)
    return nodes, nid_counter
