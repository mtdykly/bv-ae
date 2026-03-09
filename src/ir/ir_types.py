from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal, Mapping


BitKind = Literal["wire", "const"]
SignalKind = Literal["input", "output", "wire"]
DriverKind = Literal["port", "node"]

def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)

def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)

# ---- basic types ----

@dataclass(frozen=True)
class SrcSpan:
    raw: str
    file: Optional[str] = None
    line_start: Optional[int] = None
    col_start: Optional[int] = None
    line_end: Optional[int] = None
    col_end: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> Optional["SrcSpan"]:
        if d is None:
            return None
        _expect(isinstance(d, Mapping), "SrcSpan must be a dict-like object")
        raw = d.get("raw")
        _expect(isinstance(raw, str) and raw, "SrcSpan.raw must be non-empty str")
        return cls(
            raw=assert_str(raw),
            file=d.get("file"),
            line_start=d.get("line_start"),
            col_start=d.get("col_start"),
            line_end=d.get("line_end"),
            col_end=d.get("col_end"),
        )

    def validate(self) -> None:
        _expect(isinstance(self.raw, str) and self.raw, "SrcSpan.raw must be non-empty str")
        if self.file is not None:
            _expect(isinstance(self.file, str) and self.file, "SrcSpan.file must be non-empty str when present")
            for k, v in [
                ("line_start", self.line_start),
                ("col_start", self.col_start),
                ("line_end", self.line_end),
                ("col_end", self.col_end),
            ]:
                _expect(v is None or _is_int(v), f"SrcSpan.{k} must be int or None")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"raw": self.raw}
        if self.file is not None:
            d["file"] = self.file
            d["line_start"] = self.line_start
            d["col_start"] = self.col_start
            d["line_end"] = self.line_end
            d["col_end"] = self.col_end
        return d

def assert_str(x: Any) -> str:
    _expect(isinstance(x, str), "expected str")
    return x

@dataclass(frozen=True)
class BitRef:
    kind: BitKind
    id: Optional[int] = None
    val: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BitRef":
        _expect(isinstance(d, Mapping), "BitRef must be a dict-like object")
        k = d.get("kind")
        _expect(k in ("wire", "const"), f"BitRef.kind invalid: {k}")
        if k == "wire":
            bid = d.get("id")
            _expect(_is_int(bid), "BitRef(kind='wire') requires int id")
            return cls(kind="wire", id=int(bid))
        else:
            v = d.get("val")
            _expect(isinstance(v, str), "BitRef(kind='const') requires str val")
            return cls(kind="const", val=v)

    def validate(self) -> None:
        _expect(self.kind in ("wire", "const"), f"BitRef.kind invalid: {self.kind}")
        if self.kind == "wire":
            _expect(_is_int(self.id), "BitRef(kind='wire') requires int id")
        else:
            _expect(isinstance(self.val, str), "BitRef(kind='const') requires str val")

    def to_dict(self) -> Dict[str, Any]:
        if self.kind == "wire":
            return {"kind": "wire", "id": self.id}
        return {"kind": "const", "val": self.val}

@dataclass
class Signal:
    sid: str
    name: str
    kind: SignalKind
    width: int
    signed: bool
    bits: List[BitRef]
    src: Optional[SrcSpan] = None
    alias_of: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Signal":
        _expect(isinstance(d, Mapping), "Signal must be a dict-like object")
        bits_raw = d.get("bits", [])
        _expect(isinstance(bits_raw, list), "Signal.bits must be list")
        return cls(
            sid=assert_str(d.get("sid")),
            name=assert_str(d.get("name")),
            kind=d.get("kind"),
            width=d.get("width"),
            signed=bool(d.get("signed", False)),
            bits=[BitRef.from_dict(br) for br in bits_raw],
            src=SrcSpan.from_dict(d.get("src")),
            alias_of=d.get("alias_of"),
        )

    def validate(self) -> None:
        _expect(isinstance(self.sid, str) and self.sid, "Signal.sid must be non-empty str")
        _expect(isinstance(self.name, str) and self.name, "Signal.name must be non-empty str")
        _expect(self.kind in ("input", "output", "wire"), f"Signal.kind invalid: {self.kind}")
        _expect(_is_int(self.width) and self.width >= 0, f"Signal.width invalid: {self.width}")
        _expect(isinstance(self.bits, list), "Signal.bits must be list")
        _expect(self.width == len(self.bits), f"Signal.width mismatch: {self.name}, width={self.width}, bits={len(self.bits)}")
        for br in self.bits:
            _expect(isinstance(br, BitRef), "Signal.bits element must be BitRef")
            br.validate()
        if self.src is not None:
            self.src.validate()
        if self.alias_of is not None:
            _expect(isinstance(self.alias_of, str) and self.alias_of, "Signal.alias_of must be non-empty str when present")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sid": self.sid,
            "name": self.name,
            "kind": self.kind,
            "width": self.width,
            "signed": self.signed,
            "bits": [b.to_dict() for b in self.bits],
            "src": (self.src.to_dict() if self.src else None),
            "alias_of": self.alias_of,
        }


# ---- node types ----

Op = str  # AND, OR, XOR, NOT, MUX, ADD, SUB, EXTRACT, CONCAT, SHL, SHR, EQ, LT, LE, GT, GE, ASHR, UNSUPPORTED

@dataclass(frozen=True)
class DriverRef:
    kind: DriverKind
    name: Optional[str] = None   # kind=port
    nid: Optional[str] = None    # kind=node
    port: Optional[str] = None   # kind=node

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> Optional["DriverRef"]:
        if d is None:
            return None
        _expect(isinstance(d, Mapping), "DriverRef must be a dict-like object")
        k = d.get("kind")
        _expect(k in ("port", "node"), f"DriverRef.kind invalid: {k}")
        if k == "port":
            nm = d.get("name")
            _expect(isinstance(nm, str) and nm, "DriverRef(kind='port') requires non-empty name")
            return cls(kind="port", name=nm)
        else:
            nid = d.get("nid")
            port = d.get("port")
            _expect(isinstance(nid, str) and nid, "DriverRef(kind='node') requires non-empty nid")
            _expect(isinstance(port, str) and port, "DriverRef(kind='node') requires non-empty port")
            return cls(kind="node", nid=nid, port=port)

    def validate(self) -> None:
        _expect(self.kind in ("port", "node"), f"DriverRef.kind invalid: {self.kind}")
        if self.kind == "port":
            _expect(isinstance(self.name, str) and self.name, "DriverRef(kind='port') requires name")
        else:
            _expect(isinstance(self.nid, str) and self.nid, "DriverRef(kind='node') requires nid")
            _expect(isinstance(self.port, str) and self.port, "DriverRef(kind='node') requires port")

    def to_dict(self) -> Dict[str, Any]:
        if self.kind == "port":
            return {"kind": "port", "name": self.name}
        return {"kind": "node", "nid": self.nid, "port": self.port}


@dataclass(frozen=True)
class UseRef:
    kind: Literal["node"]
    nid: str
    port: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "UseRef":
        _expect(isinstance(d, Mapping), "UseRef must be a dict-like object")
        _expect(d.get("kind") == "node", "UseRef.kind must be 'node'")
        nid = d.get("nid")
        port = d.get("port")
        _expect(isinstance(nid, str) and nid, "UseRef.nid must be non-empty str")
        _expect(isinstance(port, str) and port, "UseRef.port must be non-empty str")
        return cls(kind="node", nid=nid, port=port)

    def validate(self) -> None:
        _expect(self.kind == "node", "UseRef.kind must be 'node'")
        _expect(isinstance(self.nid, str) and self.nid, "UseRef.nid must be non-empty str")
        _expect(isinstance(self.port, str) and self.port, "UseRef.port must be non-empty str")

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "node", "nid": self.nid, "port": self.port}


@dataclass
class Node:
    nid: str
    op: Op
    yosys_type: str
    yosys_name: str
    ports: Dict[str, List[BitRef]]
    args: Dict[str, List[BitRef]] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    out_width: int = 0
    out_signed: bool = False
    src: Optional[SrcSpan] = None
    is_view: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Node":
        _expect(isinstance(d, Mapping), "Node must be a dict-like object")
        ports_raw = d.get("ports", {})
        _expect(isinstance(ports_raw, Mapping), "Node.ports must be dict-like")
        args_raw = d.get("args", {}) or {}
        _expect(isinstance(args_raw, Mapping), "Node.args must be dict-like")

        def conv_map(m: Mapping[str, Any]) -> Dict[str, List[BitRef]]:
            out: Dict[str, List[BitRef]] = {}
            for k, v in m.items():
                _expect(isinstance(k, str), "Node port name must be str")
                _expect(isinstance(v, list), f"Node port '{k}' bits must be list")
                out[k] = [BitRef.from_dict(br) for br in v]
            return out

        return cls(
            nid=assert_str(d.get("nid")),
            op=assert_str(d.get("op")),
            yosys_type=str(d.get("yosys_type", "")),
            yosys_name=str(d.get("yosys_name", "")),
            ports=conv_map(ports_raw),
            args=conv_map(args_raw) if args_raw else {},
            params=dict(d.get("params", {}) or {}),
            out_width=int(d.get("out_width", 0)),
            out_signed=bool(d.get("out_signed", False)),
            src=SrcSpan.from_dict(d.get("src")),
            is_view=bool(d.get("is_view", False)),
        )

    def validate(self) -> None:
        _expect(isinstance(self.nid, str) and self.nid, "Node.nid must be non-empty str")
        _expect(isinstance(self.op, str) and self.op, f"Node.op must be non-empty str: nid={self.nid}")
        _expect(isinstance(self.ports, dict), f"Node.ports must be dict: nid={self.nid}")
        _expect(_is_int(self.out_width) and self.out_width >= 0, f"Node.out_width invalid: nid={self.nid}")
        for pn, bits in self.ports.items():
            _expect(isinstance(pn, str) and pn, f"Node port name invalid: nid={self.nid}")
            _expect(isinstance(bits, list), f"Node port bits not list: nid={self.nid}, port={pn}")
            for br in bits:
                _expect(isinstance(br, BitRef), f"Node port bit not BitRef: nid={self.nid}, port={pn}")
                br.validate()

        if "Y" in self.ports:
            _expect(self.out_width == len(self.ports["Y"]),
                    f"Node out_width mismatch: nid={self.nid}, out={self.out_width}, Y={len(self.ports['Y'])}")

        if self.src is not None:
            self.src.validate()

        # args只做结构合法性检查，不强制语义完整
        _expect(isinstance(self.args, dict), f"Node.args must be dict: nid={self.nid}")
        for ak, av in self.args.items():
            _expect(isinstance(ak, str) and ak, f"Node.args key invalid: nid={self.nid}")
            _expect(isinstance(av, list), f"Node.args[{ak}] must be list: nid={self.nid}")
            for br in av:
                _expect(isinstance(br, BitRef), f"Node.args bit not BitRef: nid={self.nid}")
                br.validate()

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "nid": self.nid,
            "op": self.op,
            "yosys_type": self.yosys_type,
            "yosys_name": self.yosys_name,
            "ports": {k: [b.to_dict() for b in v] for k, v in self.ports.items()},
            "args": {k: [b.to_dict() for b in v] for k, v in self.args.items()},
            "params": self.params,
            "out_width": self.out_width,
            "out_signed": self.out_signed,
            "src": (self.src.to_dict() if self.src else None),
        }
        if self.is_view:
            d["is_view"] = True
        return d


# ---- bit index ----

@dataclass
class BitIndexEntry:
    owners: List[str]
    driver: Optional[DriverRef]
    uses: List[UseRef]

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BitIndexEntry":
        _expect(isinstance(d, Mapping), "BitIndexEntry must be a dict-like object")
        owners = d.get("owners", [])
        _expect(isinstance(owners, list), "BitIndexEntry.owners must be list")
        for o in owners:
            _expect(isinstance(o, str) and o, "BitIndexEntry.owners item must be non-empty str")
        driver = DriverRef.from_dict(d.get("driver"))
        uses_raw = d.get("uses", [])
        _expect(isinstance(uses_raw, list), "BitIndexEntry.uses must be list")
        uses = [UseRef.from_dict(u) for u in uses_raw]
        return cls(owners=list(owners), driver=driver, uses=uses)

    def validate(self) -> None:
        _expect(isinstance(self.owners, list), "BitIndexEntry.owners must be list")
        for o in self.owners:
            _expect(isinstance(o, str) and o, "BitIndexEntry.owners item must be non-empty str")
        if self.driver is not None:
            self.driver.validate()
        _expect(isinstance(self.uses, list), "BitIndexEntry.uses must be list")
        for u in self.uses:
            _expect(isinstance(u, UseRef), "BitIndexEntry.uses item must be UseRef")
            u.validate()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owners": self.owners,
            "driver": (self.driver.to_dict() if self.driver else None),
            "uses": [u.to_dict() for u in self.uses],
        }


@dataclass
class BitIndex:
    wire_bits: Dict[str, BitIndexEntry]

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BitIndex":
        _expect(isinstance(d, Mapping), "BitIndex must be a dict-like object")
        wb = d.get("wire_bits", {})
        _expect(isinstance(wb, Mapping), "BitIndex.wire_bits must be dict-like")
        out: Dict[str, BitIndexEntry] = {}
        for bid, entry in wb.items():
            _expect(isinstance(bid, str) and bid, "wire_bits key must be non-empty str")
            _expect(isinstance(entry, Mapping), f"wire_bits[{bid}] must be dict-like")
            out[bid] = BitIndexEntry.from_dict(entry)
        return cls(wire_bits=out)

    def validate(self) -> None:
        _expect(isinstance(self.wire_bits, dict), "BitIndex.wire_bits must be dict")
        for bid, entry in self.wire_bits.items():
            _expect(isinstance(bid, str) and bid, "wire_bits key must be non-empty str")
            _expect(isinstance(entry, BitIndexEntry), "wire_bits entry must be BitIndexEntry")
            entry.validate()

    def to_dict(self) -> Dict[str, Any]:
        return {"wire_bits": {bid: e.to_dict() for bid, e in self.wire_bits.items()}}


@dataclass
class ModuleIR:
    ir_version: str
    source_format: str
    source_creator: str
    top_module: str
    src_files: List[str]
    signals: List[Signal]
    nodes: List[Node]
    outputs: Dict[str, Dict[str, Any]]
    bit_index: BitIndex

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ModuleIR":
        _expect(isinstance(d, Mapping), "ModuleIR must be a dict-like object")
        sigs_raw = d.get("signals", [])
        nodes_raw = d.get("nodes", [])
        _expect(isinstance(sigs_raw, list), "ModuleIR.signals must be list")
        _expect(isinstance(nodes_raw, list), "ModuleIR.nodes must be list")

        src_files = d.get("src_files", [])
        _expect(isinstance(src_files, list), "ModuleIR.src_files must be list")
        for f in src_files:
            _expect(isinstance(f, str) and f, "ModuleIR.src_files item must be non-empty str")

        outputs = d.get("outputs", {}) or {}
        _expect(isinstance(outputs, Mapping), "ModuleIR.outputs must be dict-like")

        bit_index = BitIndex.from_dict(d.get("bit_index", {}) or {})

        return cls(
            ir_version=str(d.get("ir_version", "")),
            source_format=str(d.get("source_format", "")),
            source_creator=str(d.get("source_creator", "")),
            top_module=str(d.get("top_module", "")),
            src_files=list(src_files),
            signals=[Signal.from_dict(s) for s in sigs_raw],
            nodes=[Node.from_dict(n) for n in nodes_raw],
            outputs=dict(outputs),
            bit_index=bit_index,
        )

    def validate(self) -> None:
        _expect(self.source_format == "yosys_write_json", f"unexpected source_format: {self.source_format}")
        _expect(isinstance(self.top_module, str) and self.top_module, "ModuleIR.top_module must be non-empty str")
        _expect(isinstance(self.ir_version, str) and self.ir_version, "ModuleIR.ir_version must be non-empty str")

        seen_sig: set[str] = set()
        for s in self.signals:
            s.validate()
            _expect(s.name not in seen_sig, f"Duplicate signal name: {s.name}")
            seen_sig.add(s.name)

        seen_nid: set[str] = set()
        for n in self.nodes:
            n.validate()
            _expect(n.nid not in seen_nid, f"Duplicate nid: {n.nid}")
            seen_nid.add(n.nid)

        self.bit_index.validate()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ir_version": self.ir_version,
            "source_format": self.source_format,
            "source_creator": self.source_creator,
            "top_module": self.top_module,
            "src_files": self.src_files,
            "signals": [s.to_dict() for s in self.signals],
            "nodes": [n.to_dict() for n in self.nodes],
            "outputs": self.outputs,
            "bit_index": self.bit_index.to_dict(),
        }
