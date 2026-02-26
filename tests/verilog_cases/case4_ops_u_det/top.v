module top(
  input  [7:0] a,
  input  [7:0] b,
  input  [2:0] shamt,
  input        sel,

  output [7:0] y_and,
  output [7:0] y_or,
  output [7:0] y_xor,
  output [7:0] y_not,
  output [7:0] y_mux,
  output [7:0] y_add,
  output [7:0] y_sub,

  output [3:0] y_slice,
  output [15:0] y_concat,

  output [7:0] y_shl,
  output [7:0] y_shr,
  output [7:0] y_ashr,

  output       y_eq,
  output       y_lt,
  output       y_le,
  output       y_gt,
  output       y_ge
);

  // 逻辑类
  (* keep *) wire [7:0] t_and;  assign t_and = a & b;  assign y_and = t_and;
  (* keep *) wire [7:0] t_or;   assign t_or  = a | b;  assign y_or  = t_or;
  (* keep *) wire [7:0] t_xor;  assign t_xor = a ^ b;  assign y_xor = t_xor;
  (* keep *) wire [7:0] t_not;  assign t_not = ~a;     assign y_not = t_not;

  // 选择
  (* keep *) wire [7:0] t_mux;  assign t_mux = sel ? b : a;  assign y_mux = t_mux;

  // 算术
  (* keep *) wire [7:0] t_add;  assign t_add = a + b;  assign y_add = t_add;
  (* keep *) wire [7:0] t_sub;  assign t_sub = a - b;  assign y_sub = t_sub;

  // 选位与拼接
  (* keep *) wire [3:0]  t_slice;  assign t_slice  = a[5:2];     assign y_slice  = t_slice;
  (* keep *) wire [15:0] t_concat; assign t_concat = {a, b};     assign y_concat = t_concat;

  // 移位
  (* keep *) wire [7:0] t_shl;  assign t_shl = a << shamt;  assign y_shl = t_shl;
  (* keep *) wire [7:0] t_shr;  assign t_shr = a >> shamt;  assign y_shr = t_shr;

  // 这里为了覆盖$sshr（ASHR），用显式$signed强制算术右移生成$sshr
  (* keep *) wire [7:0] t_ashr; assign t_ashr = $signed(a) >>> shamt;  assign y_ashr = t_ashr;

  // 比较与关系
  (* keep *) wire t_eq;  assign t_eq = (a == b);  assign y_eq = t_eq;
  (* keep *) wire t_lt;  assign t_lt = (a <  b);  assign y_lt = t_lt;
  (* keep *) wire t_le;  assign t_le = (a <= b);  assign y_le = t_le;
  (* keep *) wire t_gt;  assign t_gt = (a >  b);  assign y_gt = t_gt;
  (* keep *) wire t_ge;  assign t_ge = (a >= b);  assign y_ge = t_ge;

endmodule