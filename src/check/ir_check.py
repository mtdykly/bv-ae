from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from src.ir.ir_types import ModuleIR


def _as_ir_dict(ir: Dict[str, Any] | ModuleIR) -> Dict[str, Any]:
    return ir.to_dict() if isinstance(ir, ModuleIR) else ir


def check_ir(ir: Dict[str, Any] | ModuleIR) -> None:
    ir = _as_ir_dict(ir)
    _check_top_fields(ir) # # 检查IR顶层结构是否完整
    signals: List[Dict[str, Any]] = ir.get("signals", [])
    nodes: List[Dict[str, Any]] = ir.get("nodes", [])
    bit_index: Dict[str, Any] = ir.get("bit_index", {})
    _check_signals(signals) # 检查signals中信号的合法性
    _check_nodes(nodes) # 检查nodes中节点的结构完整性
    _check_resize_nodes(nodes) # 检查显式位宽调整节点ZEXT、SEXT、TRUNC的合法性
    _check_canonical_widths(nodes) # 检查关键运算节点是否满足位宽约束
    _check_mux(nodes) 
    _check_extract_concat(nodes) 
    _check_shift_eq(nodes)
    _check_logic_not_pmux(nodes)
    _check_rel_cmp(nodes)
    _check_multi_driver(nodes, signals) # 检查多驱动问题
    _check_bit_index(bit_index, signals, nodes)
    _check_driver_coverage(bit_index, signals) # 检查驱动覆盖是否完整
    _check_dag(nodes) 

def _check_top_fields(ir: Dict[str, Any]) -> None:
    must = ["ir_version", "source_format", "top_module", "signals", "nodes", "bit_index"]
    for k in must:
        if k not in ir:
            raise ValueError(f"IR missing top field: {k}")
    if ir.get("source_format") != "yosys_write_json":
        raise ValueError(f"Unexpected source_format: {ir.get('source_format')}")
    
def _check_signals(signals: List[Dict[str, Any]]) -> None:
    seen: Set[str] = set()
    for s in signals:
        name = s.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Signal missing or invalid name")
        if name in seen:
            raise ValueError(f"Duplicate signal name: {name}")
        seen.add(name)
        width = s.get("width")
        bits = s.get("bits", [])
        if not isinstance(bits, list):
            raise ValueError(f"Signal bits not list: {name}")
        if not isinstance(width, int):
            raise ValueError(f"Signal width not int: {name}")
        if width != len(bits):
            raise ValueError(f"Signal width mismatch: {name}, width={width}, bits={len(bits)}")
        kind = s.get("kind")
        if kind not in ("input", "output", "wire"):
            raise ValueError(f"Signal kind invalid: {name}, kind={kind}")
        # BitRef基本形态校验
        for br in bits:
            if not isinstance(br, dict):
                raise ValueError(f"BitRef not dict in signal: {name}")
            k = br.get("kind")
            if k == "wire":
                if not isinstance(br.get("id"), int):
                    raise ValueError(f"Wire BitRef missing id in signal: {name}")
            elif k == "const":
                if not isinstance(br.get("val"), str):
                    raise ValueError(f"Const BitRef missing val in signal: {name}")
            else:
                raise ValueError(f"Unknown BitRef kind in signal {name}: {k}")
            
def _check_nodes(nodes: List[Dict[str, Any]]) -> None:
    seen: Set[str] = set()
    for n in nodes:
        nid = n.get("nid")
        if not isinstance(nid, str) or not nid:
            raise ValueError("Node missing or invalid nid")
        if nid in seen:
            raise ValueError(f"Duplicate nid: {nid}")
        seen.add(nid)
        op = n.get("op")
        if not isinstance(op, str) or not op:
            raise ValueError(f"Node missing op: nid={nid}")
        ports = n.get("ports", {})
        if not isinstance(ports, dict):
            raise ValueError(f"Node ports not dict: nid={nid}")
        # out_width与ports.Y的一致性
        out_width = n.get("out_width")
        if not isinstance(out_width, int):
            raise ValueError(f"Node out_width not int: nid={nid}")
        if "Y" in ports:
            y_bits = ports.get("Y", [])
            if not isinstance(y_bits, list):
                raise ValueError(f"Node Y not list: nid={nid}")
            if out_width != len(y_bits):
                raise ValueError(
                    f"Node out_width mismatch with Y: nid={nid}, out_width={out_width}, Y={len(y_bits)}"
                )

def _check_resize_nodes(nodes: List[Dict[str, Any]]) -> None:
    for n in nodes:
        op = n.get("op")
        if op not in ("ZEXT", "SEXT", "TRUNC"):
            continue

        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        if "A" not in ports or "Y" not in ports:
            raise ValueError(f"{op} missing ports A or Y: nid={nid}")

        a_bits = ports.get("A", [])
        y_bits = ports.get("Y", [])
        if not isinstance(a_bits, list) or not isinstance(y_bits, list):
            raise ValueError(f"{op} ports not list: nid={nid}")

        if op in ("ZEXT", "SEXT"):
            if len(a_bits) > len(y_bits):
                raise ValueError(
                    f"{op} requires |A| <= |Y|: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )

        if op == "TRUNC":
            if len(a_bits) < len(y_bits):
                raise ValueError(
                    f"TRUNC requires |A| >= |Y|: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )

def _check_canonical_widths(nodes: List[Dict[str, Any]]) -> None:
    for n in nodes:
        op = n.get("op")
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}

        if op in ("AND", "OR", "XOR"):
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"{op} missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"{op} ports not list: nid={nid}")
            if not (len(a_bits) == len(b_bits) == len(y_bits)):
                raise ValueError(
                    f"{op} canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}, Y={len(y_bits)}"
                )

        elif op == "NOT":
            if "A" not in ports or "Y" not in ports:
                raise ValueError(f"NOT missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"NOT ports not list: nid={nid}")
            if len(a_bits) != len(y_bits):
                raise ValueError(
                    f"NOT canonical width mismatch: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )

        elif op in ("ADD", "SUB"):
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"{op} missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"{op} ports not list: nid={nid}")
            if not (len(a_bits) == len(b_bits) == len(y_bits)):
                raise ValueError(
                    f"{op} canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}, Y={len(y_bits)}"
                )

        elif op in ("EQ", "LT", "LE", "GT", "GE"):
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"{op} missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"{op} ports not list: nid={nid}")
            if len(a_bits) != len(b_bits):
                raise ValueError(
                    f"{op} canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}"
                )
            if len(y_bits) != 1:
                raise ValueError(f"{op} output width must be 1: nid={nid}, Y={len(y_bits)}")

        elif op == "LOGIC_NOT":
            if "A" not in ports or "Y" not in ports:
                raise ValueError(f"LOGIC_NOT missing ports: nid={nid}")
            y_bits = ports.get("Y", [])
            if not isinstance(y_bits, list):
                raise ValueError(f"LOGIC_NOT Y not list: nid={nid}")
            if len(y_bits) != 1:
                raise ValueError(f"LOGIC_NOT canonical output width must be 1: nid={nid}, Y={len(y_bits)}")

        elif op == "PMUX":
            if "A" not in ports or "B" not in ports or "S" not in ports or "Y" not in ports:
                raise ValueError(f"PMUX missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            s_bits = ports.get("S", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) \
               or not isinstance(s_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"PMUX ports not list: nid={nid}")
            if len(a_bits) != len(y_bits):
                raise ValueError(
                    f"PMUX canonical width mismatch: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )
            if len(b_bits) != len(s_bits) * len(y_bits):
                raise ValueError(
                    f"PMUX canonical B width mismatch: nid={nid}, "
                    f"B={len(b_bits)}, S={len(s_bits)}, Y={len(y_bits)}"
                )
            
def _check_mux(nodes: List[Dict[str, Any]]) -> None:
    for n in nodes:
        if n.get("op") != "MUX":
            continue
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        args = n.get("args", {})

        cond = (args or {}).get("cond", [])
        if not isinstance(cond, list):
            raise ValueError(f"MUX cond not list: nid={nid}")
        if len(cond) != 1:
            raise ValueError(f"MUX cond width must be 1: nid={nid}, got={len(cond)}")

        a_bits = ports.get("A", [])
        b_bits = ports.get("B", [])
        y_bits = ports.get("Y", [])
        if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
            raise ValueError(f"MUX ports not list: nid={nid}")
        if not (len(a_bits) == len(b_bits) == len(y_bits)):
            raise ValueError(
                f"MUX canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}, Y={len(y_bits)}"
            )

def _get_param_int(params: dict, keys: list[str]) -> int | None:
    for k in keys:
        v = params.get(k)
        if isinstance(v, int):
            return v
    return None

def _check_extract_concat(nodes: list[dict]) -> None:
    for n in nodes:
        op = n.get("op")
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        params = n.get("params", {}) or {}
        if op == "EXTRACT":
            if "A" not in ports or "Y" not in ports:
                raise ValueError(f"EXTRACT missing ports A or Y: nid={nid}")
            a_bits = ports.get("A", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"EXTRACT ports not list: nid={nid}")
            a_w = len(a_bits)
            y_w = len(y_bits)
            # 兼容读取OFFSET与WIDTH
            offset = _get_param_int(params, ["OFFSET", "A_OFFSET", "START", "LO"])
            width  = _get_param_int(params, ["Y_WIDTH", "WIDTH", "SLICE_WIDTH"])
            if width is None:
                width = y_w
            if offset is None:
                if y_w <= 0 or y_w > a_w:
                    raise ValueError(f"EXTRACT width invalid: nid={nid}, A={a_w}, Y={y_w}")
                continue
            if width != y_w:
                raise ValueError(f"EXTRACT Y width mismatch: nid={nid}, width={width}, Y={y_w}")
            if offset < 0 or offset >= a_w:
                raise ValueError(f"EXTRACT offset out of range: nid={nid}, offset={offset}, A={a_w}")
            if offset + width > a_w:
                raise ValueError(
                    f"EXTRACT range out of A: nid={nid}, offset={offset}, width={width}, A={a_w}"
                )
        if op == "CONCAT":
            # 需要 A B Y
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"CONCAT missing ports A or B or Y: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"CONCAT ports not list: nid={nid}")
            a_w = len(a_bits)
            b_w = len(b_bits)
            y_w = len(y_bits)
            if a_w + b_w != y_w:
                raise ValueError(
                    f"CONCAT width mismatch: nid={nid}, A={a_w}, B={b_w}, Y={y_w}"
                )
            y_width_param = _get_param_int(params, ["Y_WIDTH", "WIDTH"])
            if y_width_param is not None and y_width_param != y_w:
                raise ValueError(
                    f"CONCAT param width mismatch: nid={nid}, param={y_width_param}, Y={y_w}"
                )

def _check_shift_eq(nodes: list[dict]) -> None:
    for n in nodes:
        op = n.get("op")
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        params = n.get("params", {}) or {}
        if op == "EQ":
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"EQ missing ports: nid={nid}")
            y_bits = ports.get("Y", [])
            if not isinstance(y_bits, list):
                raise ValueError(f"EQ Y not list: nid={nid}")
            if len(y_bits) != 1:
                raise ValueError(f"EQ output width must be 1: nid={nid}, Y={len(y_bits)}")
            y_width_param = _get_param_int(params, ["Y_WIDTH", "WIDTH"])
            if y_width_param is not None and y_width_param != 1:
                raise ValueError(f"EQ param Y_WIDTH must be 1: nid={nid}, param={y_width_param}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list):
                raise ValueError(f"EQ A/B not list: nid={nid}")
            if len(a_bits) != len(b_bits):
                raise ValueError(f"EQ canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}")
        if op in ("SHL", "SHR", "ASHR"):
            if "A" not in ports or "B" not in ports or "Y" not in ports:
                raise ValueError(f"{op} missing ports: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"{op} ports not list: nid={nid}")
            if len(b_bits) == 0:
                raise ValueError(f"{op} shift amount is empty: nid={nid}")
            # 逻辑移位：输出宽度应等于被移位值宽度
            if len(y_bits) != len(a_bits):
                raise ValueError(
                    f"{op} width mismatch: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )
            a_w = _get_param_int(params, ["A_WIDTH"])
            b_w = _get_param_int(params, ["B_WIDTH"])
            y_w = _get_param_int(params, ["Y_WIDTH", "WIDTH"])

            if a_w is not None and a_w != len(a_bits):
                raise ValueError(f"{op} param A_WIDTH mismatch: nid={nid}, param={a_w}, A={len(a_bits)}")
            if b_w is not None and b_w != len(b_bits):
                raise ValueError(f"{op} param B_WIDTH mismatch: nid={nid}, param={b_w}, B={len(b_bits)}")
            if y_w is not None and y_w != len(y_bits):
                raise ValueError(f"{op} param Y_WIDTH mismatch: nid={nid}, param={y_w}, Y={len(y_bits)}")

def _check_logic_not_pmux(nodes: List[Dict[str, Any]]) -> None:
    for n in nodes:
        op = n.get("op")
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        params = n.get("params", {}) or {}

        if op == "LOGIC_NOT":
            if "A" not in ports or "Y" not in ports:
                raise ValueError(f"LOGIC_NOT missing ports A or Y: nid={nid}")
            a_bits = ports.get("A", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"LOGIC_NOT ports not list: nid={nid}")
            if len(y_bits) != 1:
                raise ValueError(f"LOGIC_NOT output width must be 1 in canonical IR: nid={nid}, Y={len(y_bits)}")

            a_w = _get_param_int(params, ["A_WIDTH"])
            y_w = _get_param_int(params, ["Y_WIDTH", "WIDTH"])
            if a_w is not None and a_w != len(a_bits):
                raise ValueError(
                    f"LOGIC_NOT param A_WIDTH mismatch: nid={nid}, param={a_w}, A={len(a_bits)}"
                )
            if y_w is not None and y_w != len(y_bits):
                raise ValueError(
                    f"LOGIC_NOT param Y_WIDTH mismatch: nid={nid}, param={y_w}, Y={len(y_bits)}"
                )

        if op == "PMUX":
            if "A" not in ports or "B" not in ports or "S" not in ports or "Y" not in ports:
                raise ValueError(f"PMUX missing ports A or B or S or Y: nid={nid}")
            a_bits = ports.get("A", [])
            b_bits = ports.get("B", [])
            s_bits = ports.get("S", [])
            y_bits = ports.get("Y", [])
            if not isinstance(a_bits, list) or not isinstance(b_bits, list) \
               or not isinstance(s_bits, list) or not isinstance(y_bits, list):
                raise ValueError(f"PMUX ports not list: nid={nid}")

            if len(a_bits) != len(y_bits):
                raise ValueError(
                    f"PMUX width mismatch: nid={nid}, A={len(a_bits)}, Y={len(y_bits)}"
                )

            if len(s_bits) == 0:
                raise ValueError(f"PMUX select is empty: nid={nid}")

            if len(b_bits) != len(s_bits) * len(y_bits):
                raise ValueError(
                    f"PMUX B width mismatch: nid={nid}, "
                    f"B={len(b_bits)}, S={len(s_bits)}, Y={len(y_bits)}"
                )

            a_w = _get_param_int(params, ["WIDTH", "A_WIDTH"])
            y_w = _get_param_int(params, ["WIDTH", "Y_WIDTH"])
            s_w = _get_param_int(params, ["S_WIDTH"])
            if a_w is not None and a_w != len(a_bits):
                raise ValueError(
                    f"PMUX param WIDTH mismatch with A: nid={nid}, param={a_w}, A={len(a_bits)}"
                )
            if y_w is not None and y_w != len(y_bits):
                raise ValueError(
                    f"PMUX param Y/WIDTH mismatch: nid={nid}, param={y_w}, Y={len(y_bits)}"
                )
            if s_w is not None and s_w != len(s_bits):
                raise ValueError(
                    f"PMUX param S_WIDTH mismatch: nid={nid}, param={s_w}, S={len(s_bits)}"
                )

def _check_rel_cmp(nodes: list[dict]) -> None:
    for n in nodes:
        op = n.get("op")
        if op not in ("LT", "LE", "GT", "GE"):
            continue
        nid = n.get("nid")
        ports = n.get("ports", {}) or {}
        params = n.get("params", {}) or {}
        # 必须有 A/B/Y
        if "A" not in ports or "B" not in ports or "Y" not in ports:
            raise ValueError(f"{op} missing ports: nid={nid}")
        a_bits = ports.get("A", [])
        b_bits = ports.get("B", [])
        y_bits = ports.get("Y", [])
        if not isinstance(a_bits, list) or not isinstance(b_bits, list) or not isinstance(y_bits, list):
            raise ValueError(f"{op} ports not list: nid={nid}")
        if len(a_bits) != len(b_bits):
            raise ValueError(
                f"{op} canonical width mismatch: nid={nid}, A={len(a_bits)}, B={len(b_bits)}"
            )
        if len(y_bits) != 1:
            raise ValueError(f"{op} output width must be 1: nid={nid}, Y={len(y_bits)}")
        y_width_param = _get_param_int(params, ["Y_WIDTH", "WIDTH"])
        if y_width_param is not None and y_width_param != 1:
            raise ValueError(f"{op} param Y_WIDTH must be 1: nid={nid}, param={y_width_param}")
        
def _check_multi_driver(nodes: List[Dict[str, Any]], signals: List[Dict[str, Any]]) -> None:
    driven_by: Dict[int, str] = {}  # bit_id -> nid
    for n in nodes:
        if n.get("is_view", False):
            continue
        ports = n.get("ports", {}) or {}
        y_bits = ports.get("Y", [])
        for br in y_bits:
            if not isinstance(br, dict) or br.get("kind") != "wire":
                continue
            bid = br.get("id")
            if not isinstance(bid, int):
                continue
            nid = n.get("nid")
            if bid in driven_by and driven_by[bid] != nid:
                raise ValueError(f"Multi-driver wire bit: id={bid}, nids=({driven_by[bid]}, {nid})")
            driven_by[bid] = nid

def _check_bit_index(bit_index: Dict[str, Any], signals: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> None:
    if not isinstance(bit_index, dict):
        raise ValueError("bit_index not dict")

    wire_bits = bit_index.get("wire_bits", {})
    if not isinstance(wire_bits, dict):
        raise ValueError("bit_index.wire_bits not dict")

    sig_names = {s["name"] for s in signals}
    node_ids = {n["nid"] for n in nodes}
    # 反向构建signal bits的owners期望集合，校验owners至少不出界
    for bid, entry in wire_bits.items():
        if not isinstance(entry, dict):
            raise ValueError(f"bit_index.wire_bits[{bid}] not dict")

        owners = entry.get("owners", [])
        if not isinstance(owners, list):
            raise ValueError(f"owners not list for bit {bid}")
        for on in owners:
            if on not in sig_names:
                raise ValueError(f"bit_index owner refers to unknown signal: bit={bid}, owner={on}")

        driver = entry.get("driver")
        if driver is not None:
            if not isinstance(driver, dict):
                raise ValueError(f"driver not dict for bit {bid}")
            kind = driver.get("kind")
            if kind == "node":
                nid = driver.get("nid")
                if nid not in node_ids:
                    raise ValueError(f"bit_index driver refers to unknown nid: bit={bid}, nid={nid}")
            elif kind == "port":
                # port 名不强制校验
                pass
            else:
                raise ValueError(f"bit_index driver kind invalid: bit={bid}, kind={kind}")

        uses = entry.get("uses", [])
        if not isinstance(uses, list):
            raise ValueError(f"uses not list for bit {bid}")
        for u in uses:
            if not isinstance(u, dict):
                raise ValueError(f"use entry not dict for bit {bid}")
            if u.get("kind") != "node":
                raise ValueError(f"use kind invalid for bit {bid}: {u.get('kind')}")
            if u.get("nid") not in node_ids:
                raise ValueError(f"use refers to unknown nid: bit={bid}, nid={u.get('nid')}")

# 检查组合依赖是否存在环(仅对非view节点做强检查)
def _check_dag(nodes: List[Dict[str, Any]]) -> None:
    # 收集每个wire bit的驱动节点（非view）
    driver_of: Dict[int, str] = {}
    active_nodes: Dict[str, Dict[str, Any]] = {}

    for n in nodes:
        nid = n.get("nid")
        if not isinstance(nid, str) or not nid:
            continue
        if n.get("is_view", False):
            continue
        active_nodes[nid] = n
        ports = n.get("ports", {}) or {}
        for br in ports.get("Y", []) or []:
            if not isinstance(br, dict) or br.get("kind") != "wire":
                continue
            bid = br.get("id")
            if isinstance(bid, int):
                driver_of[bid] = nid

    # 建图：v->u
    adj: Dict[str, Set[str]] = {nid: set() for nid in active_nodes.keys()}
    indeg: Dict[str, int] = {nid: 0 for nid in active_nodes.keys()}

    for u_nid, u in active_nodes.items():
        ports = u.get("ports", {}) or {}
        for pname, bits in ports.items():
            if pname == "Y":
                continue
            for br in bits or []:
                if not isinstance(br, dict) or br.get("kind") != "wire":
                    continue
                bid = br.get("id")
                if not isinstance(bid, int):
                    continue
                v_nid = driver_of.get(bid)
                if v_nid is None:
                    continue
                if v_nid == u_nid:
                    # 自环：节点用到了自己驱动的bit
                    raise ValueError(f"DAG check failed: self-cycle at nid={u_nid} via bit={bid}")
                if u_nid not in adj[v_nid]:
                    adj[v_nid].add(u_nid)
                    indeg[u_nid] += 1

    # Kahn拓扑排序判环
    queue: List[str] = [nid for nid, d in indeg.items() if d == 0]
    visited = 0

    while queue:
        x = queue.pop()
        visited += 1
        for y in adj.get(x, ()):
            indeg[y] -= 1
            if indeg[y] == 0:
                queue.append(y)

    if visited != len(active_nodes):
        # 找出在环中的节点（入度>0的）
        cyclic = [nid for nid, d in indeg.items() if d > 0]
        cyclic = cyclic[:20]
        raise ValueError(f"DAG check failed: cycle detected among nodes: {cyclic}")

# 检查每个output信号的每个wire bit都必须在bit_index中有driver
def _check_driver_coverage(bit_index: Dict[str, Any], signals: List[Dict[str, Any]]) -> None:
    wire_bits = (bit_index.get("wire_bits", {}) or {})
    if not isinstance(wire_bits, dict):
        raise ValueError("bit_index.wire_bits not dict")
    for s in signals:
        if s.get("kind") != "output":
            continue
        name = s.get("name")
        for br in s.get("bits", []) or []:
            if not isinstance(br, dict):
                continue
            if br.get("kind") != "wire":
                # 输出位一般不会是const，但如果是const也可以认为有驱动
                continue
            bid = br.get("id")
            if not isinstance(bid, int):
                continue
            entry = wire_bits.get(str(bid))
            if entry is None:
                raise ValueError(f"driver_coverage: output bit missing in bit_index: signal={name}, bit={bid}")
            drv = entry.get("driver")
            if drv is None:
                raise ValueError(f"driver_coverage: output bit has no driver: signal={name}, bit={bid}")
            if not isinstance(drv, dict) or drv.get("kind") not in ("node", "port"):
                raise ValueError(f"driver_coverage: invalid driver entry: signal={name}, bit={bid}, driver={drv}")
