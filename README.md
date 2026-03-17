# bv-ae：面向组合电路的位向量 IR 与 BV3 抽象求值原型

本仓库提供一个从 **Verilog（Yosys 前端）→ Yosys JSON 网表 → 自定义 IR → BV3（0/1/X）抽象域求值 → Markdown 报告** 的完整可运行原型，用于支持无环组合逻辑的位向量抽象求值实验。

---

## 目录
- [功能概览](#功能概览)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
  - [1. 安装依赖](#1-安装依赖)
  - [2. 运行一个用例](#2-运行一个用例)
  - [3. 生成 ir、eval 与 report](#3-生成-ireval-与-report)
- [输入假设 inputs.json 格式](#输入假设-inputsjson-格式)
- [IR 结构与算子支持](#ir-结构与算子支持)
- [抽象域 BV3 与输出解释](#抽象域-bv3-与输出解释)
- [测试与实验](#测试与实验)
- [设计说明](#设计说明)

---

## 功能概览

-  **Verilog → Yosys JSON**：使用 Yosys `write_json` 导出网表
-  **Yosys JSON → 自定义 IR**：统一成算子表达式网络（Node/Signal/BitIndex）
-  **IR 检查**：
   - 字段完整性、位宽一致性
   - MUX 条件位宽、EXTRACT/CONCAT 端口与宽度/参数合法性
   - SHL/SHR/ASHR、EQ、LT/LE/GT/GE 结构
   - multi-driver 检查、输出 driver 覆盖检查、DAG（无环）检查
-  **BV3 抽象域**：
   - 每位取 `{0,1,X}`
   - 支持 `known_mask/known_value` 表示与 `range_unsigned/range_signed` 派生
   - 支持零扩展/符号扩展（zext/sext）与截断（trunc）
   - 支持构造、偏序与合并
-  **抽象求值（forward abstract evaluation）**：
   - 支持 AND/OR/XOR/NOT/MUX/ADD/SUB/EXTRACT/CONCAT/SHL/SHR/ASHR/EQ/LT/LE/GT/GE
   - 通过 `inputs.json` 指定输入假设
-  **Report**：
   - 自动生成 Markdown：输入假设 + 各输出 bits_msb/unknown_count/range/known_mask 等

------

## 项目结构

```text
bv-ae/
|- README.md

|- src/
|  |- cli.py                     # 命令行主入口：yosys.json -> ir.json -> (eval.json, report.md)
|  |- ae/
|  |  |- bv3.py                  # BV3抽象域实现
|  |  |- eval.py                 # 抽象求值（前向传播）
|  |  |- exact_eval.py           # 精确枚举基准
|  |  |- report.py               # Markdown报告生成
|  |- check/
|  |  |- ir_check.py             # IR检查：结构/一致性/DAG/driver覆盖等
|  |  |- README.md               # IR检查规则文档
|  |- frontend/
|  |  |- ir_builder.py           # Yosys JSON -> IR
|  |  |- yosys_json_reader.py    # Yosys JSON读取与基础解析
|  |- ir/
|     |- ir_types.py             # IR数据结构定义（dataclass）与序列化/校验
|     |- schema.md               # IR格式规范文档

|- tests/
|  |- test_eval.py               # 功能正确性测试
|  |- test_precision.py          # 精度测试
|  |- test_soundness.py          # 健全性测试
|  |- test_exact_vs_abstract.py  # 精确枚举 vs 抽象求值的安全性测试
|  |- verilog_cases/
|     |- case1_ops_s_det/        # 示例
|     |  |- top.v                # Verilog电路
|     |  |- inputs.json          # 抽象输入假设（bits_msb）
|     |- case01_bitops/
|     |  |- top.v
|     |  |- inputs.json

|- scripts/
|  |- run_benchmark.py           # 批量跑case，生成bench.csv bench.md

|- tools/
|  |- flow.ys                    # Yosys脚本
|  |- run_yosys.bat              # 运行Yosys生成yosys.json

|- out/                          # 运行流程后生成的产物目录
|  |- bench.csv                  # 基准汇总表（CSV）
|  |- bench.md                   # 基准汇总表（Markdown表格）
|  |- <case_name>/
|     |- yosys.json              # Yosys网表JSON
|     |- ir.json                 # 项目IR
|     |- eval.json               # 抽象求值结果
|     |- exact.json              # 精确枚举结果
|     |- compare.json            # 安全性对比结果（abstract vs exact）
|     |- report.md               # 可读报告
```

---

## 快速开始

### 1. 安装依赖

- Windows 推荐安装 **OSS CAD Suite**（包含 Yosys）
- Python 3.10+

#### 配置 `OSSCAD_HOME`（Windows）

`run_yosys.bat` 会优先使用系统中的 `yosys`；如果找不到，会尝试读取环境变量 `OSSCAD_HOME`。  
请将 `OSSCAD_HOME` 设置为你本机 OSS CAD Suite 的安装目录（真实路径）。

示例：

```powershell
# 仅当前终端会话生效
$env:OSSCAD_HOME = "D:\oss-cad-suite"

# 永久写入当前用户环境变量（新开终端后生效）
[Environment]::SetEnvironmentVariable("OSSCAD_HOME", "D:\oss-cad-suite", "User")
```

### 2. 运行一个用例

每个用例放在：

```text
tests/verilog_cases/<case_name>/
  top.v
  （可选）其他 .v 依赖文件
  （可选）inputs.json
```

运行：

```powershell
tools\run_yosys.bat <case_name>
```

会生成：

```
out/<case_name>/yosys.json
```

> 多文件用例：同一 case 文件夹下的所有 `.v` 会一并读入 Yosys。若存在模块层级，默认 flow 会 `flatten` 拍平到基本算子网络。

### 3. 生成 ir、eval 与 report

```powershell
python -m src.cli --yosys_json out\<case_name>\yosys.json --out_ir out\<case_name>\ir.json --eval --assume tests\verilog_cases\<case_name>\inputs.json --report
```

输出：

```
out/<case_name>/ir.json
out/<case_name>/eval.json
out/<case_name>/report.md
```

------

## 输入假设 inputs.json 格式

文件示例（两种格式可混用）：

```json
{
  "signals": {
    "a": { "bits_msb": "10XX" },
    "b": { "range_unsigned": [8, 11] },
    "s": { "range": [-4, -1] },
    "sel": { "bits_msb": "1" }
  }
}
```

规则：

- 每个输入信号可以使用以下三种约束形式之一：
  - `bits_msb`
  - `range_unsigned`
  - `range_signed`
  - `range`
- 同一个信号的约束对象中，以上字段必须 **恰好出现一个**
- `bits_msb` 为 **MSB→LSB** 字符串
- `bits_msb` 允许字符：`0` / `1` / `X`
- `bits_msb` 字符串长度必须等于该输入信号位宽
- IR 内部 bit 列表为 LSB-first，工具会自动对齐（反转映射）
- `range_unsigned: [lo, hi]`
  - 要求 `0 <= lo <= hi <= 2^width - 1`
  - 按无符号整数范围解释
- `range_signed: [lo, hi]`
  - 要求 `-(2^(width-1)) <= lo <= hi <= 2^(width-1)-1`
  - 按 two's complement 有符号范围解释
- `range: [lo, hi]`
  - 会根据该输入信号在 IR 中的 `signed` 属性自动解释
  - 若信号是 unsigned，则等价于 `range_unsigned`
  - 若信号是 signed，则等价于 `range_signed`

补充说明：

- `bits_msb: "10XX"` 表示这是一个按位约束，允许的具体值集合是 `1000/1001/1010/1011`
- 对于这种“可枚举的有限范围”，`range_unsigned: [8, 11]` 与上面的 `bits_msb: "10XX"` 是等价的
- 当范围不是 2 的幂大小、也不是单纯公共前缀能精确表示时：
  - 抽象求值会把它转成一个 sound 的 BV3 近似
  - 精确枚举器会按范围内所有具体值逐个枚举

## IR 结构与算子支持

IR 由以下部分组成（详见 `src/ir/schema.md`）：

- `signals[]`：输入/输出/内部网线，含位宽、signed、bits、src
- `nodes[]`：算子节点，含 op、ports（A/B/Y/S）、params（A_SIGNED/B_SIGNED/宽度等）、src
- `outputs{}`：输出信号集合
- `bit_index.wire_bits{}`：每个 wire bit 的 owners/driver/uses

支持算子：

| Yosys cell        | IR op       |
| ----------------- | ----------- |
| `$and`            | AND         |
| `$or`             | OR          |
| `$xor`            | XOR         |
| `$not`            | NOT         |
| `$mux`            | MUX         |
| `$add`            | ADD         |
| `$sub`            | SUB         |
| `$slice`          | EXTRACT     |
| `$concat`         | CONCAT      |
| `$shl`            | SHL         |
| `$shr`            | SHR         |
| `$sshr`           | ASHR        |
| `$eq`             | EQ          |
| `$lt/$le/$gt/$ge` | LT/LE/GT/GE |

#### signed 语义说明

- `signal.signed`：信号声明层面的 signed 属性（来自 Yosys ports/netnames）

- `node.params.A_SIGNED/B_SIGNED`：表达式/运算语义层面的 signed 属性（来自 Yosys cell parameters）

- 抽象求值中：

  - ASHR 依赖 A_SIGNED

  - 比较 LT/LE/GT/GE 使用 signed/unsigned 区间判断（由 A_SIGNED/B_SIGNED 决定）

  - 对齐时使用 `sext` 或 `zext`（由端口 signedness 决定）

------

## 抽象域 BV3 与输出解释

BV3 抽象值结构：

- width：位宽
- signed：是否按有符号语义解释

- `known_mask`：已知位掩码（1 表示该位已知）
- `known_value`：已知位的取值（在 mask=1 的位上有效）
- `bits_msb`：输出的可读字符串（MSB→LSB），未知位显示为 X
- `range_unsigned`：基于已知位导出的无符号范围（保守）
- `range_signed`：基于 two’s complement 导出的有符号范围（保守）
- `unknown_count`：未知位数量

> 即使 `signed=false`，工具仍会同时给出 `range_unsigned` 与 `range_signed`，它们是同一抽象位信息的两种解释视角。

### range 精化策略：移位算子

针对 `SHL/SHR/ASHR`，求值器采用“**可枚举优先，区间回退**”策略：

- 当移位量未知位较少时，先枚举移位量候选，逐候选计算后按位 `join`，得到更精确结果。
- 当移位量无法安全枚举（未知位过多）时，不再直接退化为 `top`，而是基于移位量的 `range_unsigned=[sh_lo, sh_hi]` 做保守精化：
  - `SHL`：综合 `i-sh` 可能命中的源位区间，并考虑越界补 `0`。
  - `SHR`：综合 `i+sh` 可能命中的源位区间，并考虑越界补 `0`。
  - `ASHR`：综合 `i+sh` 可能命中的源位区间，并考虑越界补符号位。
- 上述策略保持 soundness（不漏真实取值）的同时，通常能比“直接 `top`”保留更多已知位信息。

## 测试与实验

**运行全部测试：**

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
```

**安全性回归测试（精确枚举 vs 抽象求值）：**

```powershell
python -m unittest tests.test_exact_vs_abstract -q
```

**批量基准实验（生成 `bench.csv` 与 `bench.md`）：**

```powershell
python scripts/run_benchmark.py
```

**`bench.md` 的含义**

bench 表每行对应一个 case，列含义如下：

- case：用例名

- sound_ok：安全性是否通过（抽象确定的位是否都被精确枚举支持）

- enum_var_bits：精确枚举的变量位数 k（inputs 中 X 的总位数）

- enum_count：枚举次数 2^k

- abs_time_s：抽象求值耗时（秒）

- exact_time_s：精确枚举耗时（秒）

- abs_known_ratio：抽象输出的平均已知位比例（越大越好）

- exact_known_ratio：精确枚举输出的平均已知位比例（真实恒定位比例，作为参考上界）

- abs_avg_unknown_bits：抽象输出平均未知位数（越小越好）

- exact_avg_unknown_bits：精确枚举输出平均未知位数（真实不确定性）

- abs_avg_range_span：抽象输出 range_unsigned 的平均跨度 hi-lo（越小越紧）

- exact_avg_range_span：精确枚举输出真实跨度（真实 min max）

- issues_count：对比发现的问题数量

## 设计说明

- 当前聚焦 **无环组合逻辑**：如需时序，需要扩展 IR 与求值框架（不动点/时序迭代）
- 默认会对层级设计做 `flatten`，以得到纯算子网络
