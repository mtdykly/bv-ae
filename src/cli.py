from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.frontend.ir_builder import build_module_ir
from src.check.ir_check import check_ir
from src.ae.eval import eval_ir_bv3
from src.ae.report import build_report_md

def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json(path: Path, obj: dict, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Convert Yosys write_json output to project IR")
    ap.add_argument("--yosys_json", required=True, help="Path to yosys.json")
    ap.add_argument("--out_ir", required=True, help="Path to output ir.json")
    ap.add_argument("--no_check", action="store_true", help="Skip IR checks")
    ap.add_argument("--compact", action="store_true", help="Write compact JSON (no indent)")
    # 开启抽象求值
    ap.add_argument("--eval", action="store_true", help="Run abstract evaluation and write eval.json")
    ap.add_argument("--out_eval", default="", help="Path to output eval.json (default: alongside ir.json)")
    # 提供输入假设
    ap.add_argument("--assume", default="", help="Path to inputs.json for abstract evaluation")
    ap.add_argument("--report", action="store_true", help="Write markdown report (requires --eval)")
    ap.add_argument("--out_report", default="", help="Path to output report.md (default: alongside ir.json)")
    args = ap.parse_args()

    yosys_path = Path(args.yosys_json)
    out_ir_path = Path(args.out_ir)
    #执行yosys到ir的转换
    yosys_obj = _read_json(yosys_path)
    ir_obj = build_module_ir(yosys_obj)
    ir_obj.validate() # 基础合法性检查
    ir_out = ir_obj.to_dict()

    if not args.no_check:
        check_ir(ir_out)

    _write_json(out_ir_path, ir_out, pretty=(not args.compact))
    print(f"[OK] IR written to: {out_ir_path}")

    if args.report and not args.eval:
        raise SystemExit("[ERROR] --report requires --eval")
    
    # 抽象求值生成eval.json
    if args.eval:
        out_eval_path = Path(args.out_eval) if args.out_eval else (out_ir_path.parent / "eval.json")
        assume_obj = _read_json(Path(args.assume)) if args.assume else None
        ev = eval_ir_bv3(ir_out, assume=assume_obj)
        _write_json(out_eval_path, ev, pretty=True)
        print(f"[OK] Eval written to: {out_eval_path}")

        if args.report:
            out_report_path = Path(args.out_report) if args.out_report else (out_ir_path.parent / "report.md")
            md = build_report_md(ir_out, assume_obj, ev)
            out_report_path.parent.mkdir(parents=True, exist_ok=True)
            out_report_path.write_text(md, encoding="utf-8")
            print(f"[OK] Report written to: {out_report_path}")


if __name__ == "__main__":
    main()
