import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from src.ae.eval import eval_ir_bv3
from src.ae.exact_eval import eval_ir_exact_enum, compare_exact_vs_abstract
from tests._cases import CASES


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

    ir_path = ROOT / "out" / case / "ir.json"
    if not ir_path.exists():
        raise RuntimeError(f"ir.json not found after yosys run: {ir_path}")
    return ir_path

def _outputs_only(signals: Dict[str, dict]) -> Dict[str, dict]:
    return {k: v for k, v in (signals or {}).items() if isinstance(v, dict) and "width" in v}

def _avg_metrics(signals: Dict[str, dict]) -> Tuple[float, float, float]:
    sigs = _outputs_only(signals)
    if not sigs:
        return 0.0, 0.0, 0.0

    known_ratios: List[float] = []
    unknowns: List[float] = []
    spans: List[float] = []

    for _name, s in sigs.items():
        w = int(s.get("width", 0))
        unk = int(s.get("unknown_count", 0))
        lo, hi = (s.get("range_unsigned") or [0, 0])
        span = int(hi) - int(lo)

        if w > 0:
            known_ratios.append((w - unk) / w)
        unknowns.append(float(unk))
        spans.append(float(span))

    return (
        sum(known_ratios) / len(known_ratios),
        sum(unknowns) / len(unknowns),
        sum(spans) / len(spans),
    )

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None, help="override case list")
    ap.add_argument("--max-enum", type=int, default=1_000_000)
    ap.add_argument("--signals-mode", choices=["outputs", "all"], default="outputs")
    ap.add_argument("--out-csv", default="out/bench.csv")
    ap.add_argument("--out-md", default="out/bench.md")
    args = ap.parse_args()

    if os.name != "nt":
        raise RuntimeError("this benchmark runner expects Windows .bat yosys flow")

    cases = args.cases if args.cases else CASES

    rows: List[dict] = []

    for case in cases:
        print(f"[bench] {case} ...")

        ir_path = _run_yosys(case)
        ir = _read_json(ir_path)
        assume = _read_json(ROOT / "tests" / "verilog_cases" / case / "inputs.json")

        out_dir = ROOT / "out" / case
        out_dir.mkdir(parents=True, exist_ok=True)

        # 抽象求值
        t0 = time.perf_counter()
        abstract = eval_ir_bv3(ir, assume)
        t1 = time.perf_counter()
        abs_time = t1 - t0
        _write_json(out_dir / "eval.json", abstract)

        # 精确枚举
        t2 = time.perf_counter()
        exact = eval_ir_exact_enum(ir, assume, max_enum=args.max_enum, signals_mode=args.signals_mode)
        t3 = time.perf_counter()
        exact_time = t3 - t2
        _write_json(out_dir / "exact.json", exact)

        # 对比
        rep = compare_exact_vs_abstract(exact, abstract)
        _write_json(out_dir / "compare.json", rep)

        abs_known, abs_unk, abs_span = _avg_metrics(abstract.get("signals", {}))
        ex_known, ex_unk, ex_span = _avg_metrics(exact.get("signals", {}))

        rows.append(
            {
                "case": case,
                "sound_ok": bool(rep.get("ok", False)),
                "enum_var_bits": int(exact.get("enum_var_bits", 0)),
                "enum_count": int(exact.get("enum_count", 0)),
                "abs_time_s": f"{abs_time:.6f}",
                "exact_time_s": f"{exact_time:.6f}",
                "abs_known_ratio": f"{abs_known:.4f}",
                "exact_known_ratio": f"{ex_known:.4f}",
                "abs_avg_unknown_bits": f"{abs_unk:.2f}",
                "exact_avg_unknown_bits": f"{ex_unk:.2f}",
                "abs_avg_range_span": f"{abs_span:.2f}",
                "exact_avg_range_span": f"{ex_span:.2f}",
                "issues_count": len(rep.get("issues", []) or []),
            }
        )

        print(
            f"  ok={rows[-1]['sound_ok']} enum=2^{rows[-1]['enum_var_bits']}={rows[-1]['enum_count']} "
            f"abs={abs_time:.4f}s exact={exact_time:.4f}s"
        )

    # 写CSV
    out_csv = ROOT / args.out_csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # 写Markdown 表
    out_md = ROOT / args.out_md
    out_md.parent.mkdir(parents=True, exist_ok=True)

    headers = list(rows[0].keys())
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(r[h]) for h in headers) + " |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    all_ok = all(bool(r["sound_ok"]) for r in rows)
    print(f"[bench] done. all_sound_ok={all_ok}")
    print(f"[bench] wrote: {out_csv}")
    print(f"[bench] wrote: {out_md}")

if __name__ == "__main__":
    main()