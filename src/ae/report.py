from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, List

from src.ae.eval import eval_ir_bv3
from src.ir.ir_types import ModuleIR


def _as_ir_dict(ir: dict | ModuleIR) -> dict:
    return ir.to_dict() if isinstance(ir, ModuleIR) else ir

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def _fmt_range(r: Any) -> str:
    if isinstance(r, list) and len(r) == 2:
        return f"[{r[0]}, {r[1]}]"
    return str(r)

def _md_escape(s: str) -> str:
    return s.replace("|", "\\|")

# 用src位置信息排序，尽量还原端口声明顺序。
def _span_sort_key(span: Optional[Dict[str, Any]]) -> tuple:
    if not isinstance(span, dict):
        return ("", 10**9, 10**9, 10**9, 10**9)
    f = span.get("file") or ""
    ls = span.get("line_start")
    cs = span.get("col_start")
    le = span.get("line_end")
    ce = span.get("col_end")
    def _i(x): return int(x) if isinstance(x, int) else 10**9
    return (str(f), _i(ls), _i(cs), _i(le), _i(ce))

def _get_output_signal_order(ir: dict | ModuleIR) -> List[str]:
    ir = _as_ir_dict(ir)
    sigs = ir.get("signals", []) or []
    outs = [s for s in sigs if isinstance(s, dict) and s.get("kind") == "output" and s.get("name")]
    outs.sort(key=lambda s: (_span_sort_key(s.get("src")), str(s.get("name"))))
    return [s["name"] for s in outs]

def build_report_md(ir: dict | ModuleIR, assume: Optional[dict], ev: dict) -> str:
    ir = _as_ir_dict(ir)
    top = ir.get("top_module", "")
    lines: List[str] = []
    lines.append(f"# Abstract Evaluation Report")
    lines.append("")
    lines.append(f"- top_module: `{_md_escape(str(top))}`")
    lines.append(f"- domain: `{_md_escape(str(ev.get('domain', '')))}`")
    lines.append("")
    lines.append("## Inputs (assumptions)")
    lines.append("")
    if not assume:
        lines.append("_No assumptions provided._")
        lines.append("")
    else:
        sigs = assume.get("signals", {}) or {}
        lines.append("| name | bits_msb |")
        lines.append("| --- | --- |")
        for name, spec in sigs.items():
            if isinstance(spec, str):
                bits_msb = spec
            elif isinstance(spec, dict):
                bits_msb = spec.get("bits_msb", "")
            else:
                bits_msb = ""
            lines.append(f"| `{_md_escape(str(name))}` | `{_md_escape(str(bits_msb))}` |")
        lines.append("")

    lines.append("## Outputs")
    lines.append("")
    lines.append("| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |")
    lines.append("| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |")

    # 输出顺序：尽量按端口声明顺序
    out_names = _get_output_signal_order(ir)

    sig_ev = (ev.get("signals", {}) or {})
    for name in out_names:
        if name not in sig_ev:
            continue
        d = sig_ev[name]
        lines.append(
            "| `{}` | {} | {} | `{}` | `{}` | `{}` | {} | `{}` | `{}` |".format(
                _md_escape(str(name)),
                d.get("width", ""),
                "1" if d.get("signed", False) else "0",
                _md_escape(str(d.get("bits_msb", ""))),
                _md_escape(str(d.get("known_mask_hex", ""))),
                _md_escape(str(d.get("known_value_hex", ""))),
                d.get("unknown_count", ""),
                _md_escape(_fmt_range(d.get("range_unsigned"))),
                _md_escape(_fmt_range(d.get("range_signed"))),
            )
        )
    lines.append("")

    return "\n".join(lines)

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate markdown report for abstract evaluation")
    ap.add_argument("--ir", required=True, help="Path to ir.json")
    ap.add_argument("--assume", default="", help="Path to inputs.json (optional)")
    ap.add_argument("--eval", default="", help="Path to eval.json (optional). If not provided, eval will be run.")
    ap.add_argument("--out", required=True, help="Path to output report.md")
    args = ap.parse_args()

    ir_path = Path(args.ir)
    ir = _read_json(ir_path)

    assume = _read_json(Path(args.assume)) if args.assume else None

    if args.eval:
        ev = _read_json(Path(args.eval))
    else:
        ev = eval_ir_bv3(ir, assume=assume)

    md = build_report_md(ir, assume, ev)
    _write_text(Path(args.out), md)
    print(f"[OK] Report written to: {args.out}")

if __name__ == "__main__":
    main()
