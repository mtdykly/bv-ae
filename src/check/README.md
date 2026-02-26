## IR 检查说明

为保证后续抽象求值与结果解释的可靠性，本项目考虑在 IR 生成后执行统一合法性检查。检查入口为 `check_ir`，若发现违规即抛出异常并终止流程。

### 1. 顶层字段完整性与格式一致性

- 检查 `ir_version`、`source_format`、`top_module`、`signals`、`nodes`、`bit_index` 等必需字段是否存在，并约束 `source_format` 为 `yosys_write_json`（`_check_top_fields`）。

### 2. 信号与节点的结构/位宽一致性

- 检查信号名唯一性、`Signal.width == len(bits)`、`kind` 合法性，以及 `BitRef` 形态（`wire.id` / `const.val`）正确（`_check_signals`）。  
- 检查节点 `nid` 唯一性、`ports` 结构合法性，以及 `Node.out_width == len(ports.Y)`（`_check_nodes`）。

### 3. 关键算子结构约束

- 检查 `MUX` 条件位宽必须为 1（`_check_mux`）。  
- 检查 `EXTRACT` / `CONCAT` 的端口完整性、位宽关系与参数一致性（`_check_extract_concat`）。  
- 检查 `EQ` 输出位宽为 1；`SHL` / `SHR` / `ASHR` 的端口完整性、移位量非空、输入输出位宽及参数一致性（`_check_shift_eq`）。  
- 检查 `LT` / `LE` / `GT` / `GE` 的端口完整性及 1 位布尔输出约束（`_check_rel_cmp`）。

### 4. 连接关系与可分析性约束

- 检查非视图节点（`is_view=False`）的 wire 位是否存在多驱动冲突（`_check_multi_driver`）。  
- 检查 `bit_index` 的 `owners` / `driver` / `uses` 引用是否指向有效信号/节点（`_check_bit_index`）。  
- 检查每个 `output` 的每个 wire 位在 `bit_index` 中均存在合法 `driver`（`_check_driver_coverage`）。  
- 检查组合依赖图无环（DAG），避免循环依赖导致求值不稳定（`_check_dag`）。

### 5. 检查失败语义

- 任一检查失败均抛出 `ValueError`，并给出具体节点/信号/bit 的定位信息，用于快速修复 IR 构建或前端转换问题。