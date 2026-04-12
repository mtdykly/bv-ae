import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.frontend.ir_builder import build_module_ir
from src.check.ir_check import check_ir
from src.ae.eval import eval_ir_bv3

CASES = ['ws008_fixed_template', 'ws016_fixed_template', 'ws032_fixed_template', 'ws064_fixed_template', 'ws128_fixed_template', 'ws256_fixed_template', 'ws512_fixed_template']


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_yosys(case: str) -> Path:
    bat = ROOT / "tools" / "run_yosys.bat"
    if not bat.exists():
        raise FileNotFoundError(f"missing: {bat}")
    p = subprocess.run([str(bat), case], cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"run_yosys failed for {case}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    yosys_json = ROOT / "out" / case / "yosys.json"
    if not yosys_json.exists():
        raise RuntimeError(f"yosys.json not found after yosys run: {yosys_json}")
    return yosys_json


def _width_of_outputs(ir: dict) -> int:
    total = 0
    for s in ir.get("signals", []) or []:
        if isinstance(s, dict) and s.get("kind") == "output":
            total += int(s.get("width", 0))
    return total


def _width_of_inputs(ir: dict) -> int:
    total = 0
    for s in ir.get("signals", []) or []:
        if isinstance(s, dict) and s.get("kind") == "input":
            total += int(s.get("width", 0))
    return total


def _max_signal_width(ir: dict) -> int:
    m = 0
    for s in ir.get("signals", []) or []:
        if isinstance(s, dict):
            m = max(m, int(s.get("width", 0)))
    return m


def _case_width(case: str) -> int:
    digits = ''.join(ch for ch in case if ch.isdigit())
    return int(digits[:3]) if len(digits) >= 3 else -1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--repeat", type=int, default=30)
    ap.add_argument("--out-csv", default="out/bench_width_sweep.csv")
    ap.add_argument("--out-md", default="out/bench_width_sweep.md")
    args = ap.parse_args()

    if os.name != "nt":
        raise RuntimeError("this runner expects Windows .bat yosys flow")

    cases = args.cases if args.cases else CASES
    rows: List[Dict[str, str]] = []

    for case in cases:
        print(f"[width-sweep] {case} ...")
        yosys_json_path = _run_yosys(case)
        yosys_obj = _read_json(yosys_json_path)
        ir_obj = build_module_ir(yosys_obj)
        ir = ir_obj.to_dict()
        check_ir(ir)

        out_dir = ROOT / "out" / case
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "ir.json", ir)

        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")

        times = []
        last_eval = None
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            last_eval = eval_ir_bv3(ir, assume)
            t1 = time.perf_counter()
            times.append(t1 - t0)

        if last_eval is not None:
            _write_json(out_dir / "eval.json", last_eval)

        node_count = len(ir.get("nodes", []) or [])
        signal_count = len(ir.get("signals", []) or [])
        rows.append(
            {
                "case": case,
                "width": str(_case_width(case)),
                "max_signal_width": str(_max_signal_width(ir)),
                "input_bits": str(_width_of_inputs(ir)),
                "output_bits": str(_width_of_outputs(ir)),
                "node_count": str(node_count),
                "signal_count": str(signal_count),
                "repeat": str(args.repeat),
                "avg_abs_time_s": f"{sum(times) / len(times):.6f}",
                "min_abs_time_s": f"{min(times):.6f}",
                "max_abs_time_s": f"{max(times):.6f}",
            }
        )
        print(
            f"  width={rows[-1]['width']} nodes={node_count} avg={rows[-1]['avg_abs_time_s']}s"
        )

    rows.sort(key=lambda r: int(r["width"]))

    out_csv = ROOT / args.out_csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    out_md = ROOT / args.out_md
    headers = list(rows[0].keys())
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(r[h]) for h in headers) + " |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[width-sweep] wrote: {out_csv}")
    print(f"[width-sweep] wrote: {out_md}")


if __name__ == "__main__":
    main()
