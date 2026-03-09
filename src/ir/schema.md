# Bit-Vector IR Schema (from Yosys JSON)

**版本**：0.1  

**目标**：将 Yosys `write_json` 输出的网表 JSON 转换为本项目自定义 IR，用于后续字级算子网络上的抽象求值与分析。
**特点**：字级多位信号 + 算子节点 + 位级来源映射 + 源码位置追溯。

## 1. 术语与约定

### 1.1 位序约定

在本 IR 中，任意多位向量 `bits` 列表满足：
- `bits[0]` 表示最低位（LSB）
- `bits[width-1]` 表示最高位（MSB）

后续所有算子语义、位切片、拼接都基于此约定。

### 1.2 BitRef（位引用）
Yosys JSON 的 `bits` 列表元素可能是：
- 整数：表示内部 wire 的单比特编号，如：

```json
"b": {
  "hide_name": 0, // 表示非自动生成的临时名
  "bits": [ 6, 7, 8, 9 ],
  "attributes": {
    "src": "top.v:3.16-3.17"
  }
},
```

- 字符串：表示常量或特殊值，如：

```json
"t": {
  "hide_name": 0,
  "bits": [ "1" ],
  "attributes": {
    "src": "top.v:9.8-9.9"
  }
},
```

本 IR 统一用 `BitRef` 表示单比特引用：

- wire 位：
```json
{ "kind": "wire", "id": 15 }
```

- 常量位：

```json
{ "kind": "const", "val": "1" }
```

`val` 允许值集合：

- `"0"`, `"1"`
- `"x"`, `"z"`（若后续考虑四值逻辑，可保留原样；第一阶段可仅保留字符串，不解释）

### 1.3 SrcSpan（源码位置）

Yosys 常见形式：`design.v:7.19-7.24` 或 `design.v:1.1-10.10`

本 IR 解析为结构化位置：

```json
{
  "file": "design.v",
  "line_start": 7,
  "col_start": 19,
  "line_end": 7,
  "col_end": 24,
  "raw": "design.v:7.19-7.24"
}
```

若无法解析，可仅保留：

```json
{ "raw": "..." }
```

## 2. 顶层结构：ModuleIR

一个 IR 文件对应一个顶层模块（或一个被选定为顶层的模块）。 

```json
{
  "ir_version": "0.1",
  "source_format": "yosys_write_json",
  "source_creator": "Yosys ...",
  "top_module": "top",
  "src_files": ["design.v"],
  "signals": [ ... ],
  "nodes": [ ... ],
  "outputs": { ... },
  "bit_index": { ... }
}
```

### 2.1 字段说明

- `ir_version`：IR 版本号（字符串）
- `source_format`：固定为 `"yosys_write_json"
- `source_creator`：直接拷贝 Yosys JSON 根字段 `creator`
- `top_module`：顶层模块名
- `src_files`：工程中出现的源码文件集合（从各处 `src` 字段解析去重得到）
- `signals`：信号表
- `nodes`：算子节点表
- `outputs`：输出端口到 bits 的映射（可由 `signals` 推导，但建议显式写出，便于快速定位输出）
- `bit_index`：位级来源与使用映射（用于追溯与调试）

## 3. 信号表：signals

### 3.1 Signal 结构

```json
{
  "sid": "t1",
  "name": "t1",
  "kind": "wire",
  "width": 4,
  "signed": false,
  "bits": [ { "kind":"wire","id":15 }, { "kind":"wire","id":16 }, ... ],
  "src": { ...SrcSpan... },
  "alias_of": null
}
```

### 3.2 字段说明

- `sid`：信号唯一标识
- `name`：信号名
- `kind`：`input` 或 `output` 或 `wire`
- `width`：位宽，必须等于 `bits.length`
- `signed`：符号属性。
- `bits`：BitRef 列表，顺序满足位序约定
- `src`：信号来源源码位置。优先来自 Yosys `netnames[name].attributes.src`
- `alias_of`：可选。若多名字指向同一组 bits，可用 alias 记录别名关系（第一阶段可不启用，置空）

### 3.3 构建规则（从 Yosys JSON 到 signals）

输入：`modules[top].ports` 与 `modules[top].netnames`

规则：

1. 先遍历 `netnames`，为每个 netname 创建 Signal，`kind` 先置为 `wire`
2. 再遍历 `ports`，若同名 Signal 已存在则覆盖其 `kind` 为 `input` 或 `output`；若不存在则补建
3. `width = len(bits)`
4. `bits` 中整数转为 `{kind:"wire", id:n}`，字符串转为 `{kind:"const", val:s}`
5. `src`：
   - 信号优先来自 `netnames[name].attributes.src`
   - 若 ports 中缺少对应 src，可置空

## 4. 算子节点表：nodes

### 4.1 Node 结构

Node 记录两层信息：

- `ports`：完全保留 Yosys 的端口连接（便于追溯）

- `args`：规范化语义视图（便于后续实现抽象求值）

```json
{
  "nid": "n3",
  "op": "MUX",
  "yosys_type": "$mux",
  "yosys_name": "$ternary$design.v:9$3",
  "ports": {
    "A": [ ...BitRef... ],
    "B": [ ...BitRef... ],
    "S": [ ...BitRef... ],
    "Y": [ ...BitRef... ]
  },
  "args": {
    "cond": [ ...BitRef... ],
    "then": [ ...BitRef... ],
    "else": [ ...BitRef... ],
    "out":  [ ...BitRef... ]
  },
  "params": { "WIDTH": 4 },
  "out_width": 4,
  "out_signed": false,
  "src": { ...SrcSpan... }
}
```

### 4.2 字段说明

- `nid`：节点唯一编号
- `op`：本项目核心算子枚举（见 4.4）
- `yosys_type`：原始 Yosys cell 类型（如 `$and`, `$xor`, `$mux`）
- `yosys_name`：Yosys cell 名字（通常含源码定位片段）
- `ports`：端口名到 BitRef 列表映射，保持原样
- `args`：规范语义视图，不同算子对应不同键名（见 4.5）
- `params`：将 Yosys `parameters` 解码后的键值表（整数或布尔）
- `out_width`：输出位宽（优先从 params 获取，否则用 `ports.Y.length`）
- `out_signed`：输出符号属性
- `src`：节点来源位置，来自 `cell.attributes.src`

### 4.3 参数解码规则

Yosys 的参数常是 32 位二进制字符串。统一解码为整数：

- `decode_bin32("000...0100") = 4`

对 signed 类参数可解为布尔：

- `0` 为 `false`

- 非零为 `true`

### 4.4 核心算子 op 枚举与映射

| Yosys cell type | op          |
| --------------- | ----------- |
| `$and`          | `AND`       |
| `$or`           | `OR`        |
| `$xor`          | `XOR`       |
| `$not`          | `NOT`       |
| `$logic_not`    | `LOGIC_NOT` |
| `$mux`          | `MUX`       |
| `$pmux`         | `PMUX`      |
| `$add`          | `ADD`       |
| `$sub`          | `SUB`       |
| `$slice`        | `EXTRACT`   |
| `$concat`       | `CONCAT`    |
| `$shl`          | `SHL`       |
| `$shr`          | `SHR`       |
| `$eq`           | `EQ`        |
| `$sshr`         | `ASHR`      |
| `$lt`           | `LT`        |
| `$le`           | `LE`        |
| `$gt`           | `GT`        |
| `$ge`           | `GE`        |

若遇到未知 type：

- `op = "UNSUPPORTED"`
- 仍保留 `ports`, `params`, `src`，后续可在分析阶段对其保守处理

### 4.5 args 规范视图

为了后续抽象求值统一调用，为常见算子构造如下 `args`：

- MUX（由 `$mux` 构造）
  - 约定：`S=0` 选 `A`，`S=1` 选 `B`（与 Yosys `$mux` 一致）

```json
{ "cond": ports.S, "else": ports.A, "then": ports.B, "out": ports.Y }
```

- PMUX（由 `$pmux` 构造）
  - 约定：`S` 为选择信号，`A` 为默认分支，`B` 为候选分支集合，输出为 `Y`
  - 说明：当 `S` 全为 0 时选择 `A`；当 `S` 的某一位为 1 时，选择 `B` 中对应的一段


```json
{ "sel": ports.S, "default": ports.A, "cases": ports.B, "out": ports.Y }
```

- 二元运算
  - 适用：`AND`, `OR`, `XOR`, `ADD`, `SUB`, `EQ`, `LT`, `LE`, `GT`, `GE`
  - 约定：`A` 为左操作数，`B` 为右操作数，输出为 `Y`


```json
{ "lhs": ports.A, "rhs": ports.B, "out": ports.Y }
```

- 一元按位运算
  - 适用：`NOT`（按位取反）
  - 约定：输入为 `A`，输出为 `Y`


```json
{ "in": ports.A, "out": ports.Y }
```

- 一元逻辑运算

  - 适用：`LOGIC_NOT`（逻辑非`!`)
  - 约定：输入为 `A`，输出为 `Y`

  ```
  { "in": ports.A, "out": ports.Y }
  ```

- EXTRACT（由 `$slice` 构造）

  - 约定：输入为 `A`，输出为 `Y`

```json
{ "in": ports.A, "out": ports.Y }
```

- CONCAT（由 `$concat` 构造）
  - 约定：`low` 对应 `A`，`high` 对应 `B`，输出为 `Y`

```json
{ "low": ports.A, "high": ports.B, "out": ports.Y }
```

- 移位运算
  - 适用：`SHL`, `SHR`, `ASHR`
  - 约定：`A` 是被移位值，`B` 是移位量，输出为 `Y`

```json
{ "value": ports.A, "shift": ports.B, "out": ports.Y }
```

## 5. 输出端口映射：outputs

为了快速获取输出位向量，考虑保存一个简表：

```json
"outputs": {
  "y": { "bits": [ ...BitRef... ] }
}
```

构建规则：

- 从 `signals` 中筛选 `kind == "output"` 的信号，写入其 `bits`

## 6. 位级来源映射：bit_index

这是 IR 的调试核心，用于追溯“每一位从哪里来，被谁驱动，被谁使用”。

### 6.1 结构

```json
"bit_index": {
  "wire_bits": {
    "15": {
      "owners": ["t1"],
      "driver": { "kind": "node", "nid": "n1", "port": "Y" },
      "uses": [
        { "kind": "node", "nid": "n3", "port": "B" }
      ]
    }
  }
}
```

### 6.2 字段说明

对每个 wire bit id（以字符串作为 key）：

- `owners`：哪些 signal 拥有该位（由 signals 反向索引得到）

- `driver`：驱动来源

  - 输入端口位：`{kind:"port", name:"a"}`

  - 节点输出位：`{kind:"node", nid:"n1", port:"Y"}`

  - 若无法判定，可为 `null`

- `uses`：使用该位的地方列表（节点输入端口引用）

### 6.3 构建规则

输入：`signals`, `nodes`, 顶层 `ports`

1. owners

   - 遍历所有 signals 的 bits

   - 对每个 `{kind:"wire", id}`，将 signal.name 加入 owners[id]

2. driver

   - 对所有 input 端口 bits，设 driver 为 `{kind:"port", name:port_name}`

   - 对所有 nodes 的输出端口位（通常 `ports.Y`），设 driver 为 `{kind:"node", nid, port:"Y"}`
   
3. uses

   - 遍历 nodes 的非输出端口（如 A, B, S）

   - 对其 bits 中的 wire 位，追加 `{kind:"node", nid, port:port_name}`

## 7. 不变量与检查要点（`check_ir`）

`check_ir` 用于验证 IR 的结构合法性与语义，主要包括：

1. **顶层字段完整性**
    IR 必须包含 `ir_version`、`source_format`、`top_module`、`signals`、`nodes`、`bit_index`，且 `source_format` 应为 `yosys_write_json`。
2. **Signal 与 Node 一致性**
   - 每个 `Signal` 满足 `width == len(bits)`，名称唯一，类型合法
   - 每个 `Node` 满足 `out_width == len(ports.Y)`（若 `Y` 存在），`nid` 唯一，端口结构合法
3. **关键算子约束**
   - `MUX` 的条件位宽必须为 1
   - `EXTRACT` 的切片范围必须合法，输出宽度与切片宽度一致
   - `CONCAT` 满足输入宽度之和等于输出宽度
   - `EQ` 与关系比较算子的输出必须为 1 位
   - 移位算子的输出宽度必须与被移位值一致
4. **驱动合法性**
   - 同一个 `wire bit` 不允许被多个非 `view` 节点同时驱动
   - 每个输出 bit 都必须在 `bit_index` 中具有合法驱动来源
5. **`bit_index` 一致性**
    `bit_index.wire_bits` 中记录的 `owners`、`driver`、`uses` 必须与 `signals` 和 `nodes` 一致。
6. **无环性**
    基于节点间 bit 依赖建立组合图，并要求其为 DAG，以满足当前原型仅处理无环组合电路的前提。

## 8. 从 Yosys JSON 到 IR 的对应关系

给定 Yosys JSON 中顶层模块对象 `modules[top]`：

- `modules[top].attributes.src`
  - 可用于顶层模块级 src（当前 IR 未单独存，可用于生成 `src_files`）
- `modules[top].ports`
  - 用于构造端口 signals（kind 为 input 或 output）
- `modules[top].netnames`
  - 用于构造更多具备源码追溯的 signals（含 src）
- `modules[top].cells`
  - 每个 cell 对应一个 Node
  - `cell.type` 对应 `yosys_type`
  - `cell.connections` 对应 `ports`
  - `cell.parameters` 对应 `params`（需解码）
  - `cell.attributes.src` 对应 `src`