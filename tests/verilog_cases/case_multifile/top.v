module top(
  input  signed [7:0] a,
  input  signed [7:0] b,
  input        [2:0] shamt,
  input              sel,

  output signed [7:0] y_logic,
  output signed [7:0] y_arith,
  output signed [7:0] y_shift,
  output signed [7:0] y_final,

  output              y_eq,
  output              y_lt,
  output              y_le,
  output              y_gt,
  output              y_ge,

  output signed [3:0]  y_slice,
  output signed [15:0] y_concat
);

  wire signed [7:0] w_and, w_or, w_xor, w_not;
  wire signed [7:0] w_add, w_sub;
  wire signed [7:0] w_shl, w_shr, w_ashr;
  wire              w_eq, w_lt, w_le, w_gt, w_ge;

  alu8 u_alu (
    .a(a), .b(b),
    .y_and(w_and), .y_or(w_or), .y_xor(w_xor), .y_not(w_not),
    .y_add(w_add), .y_sub(w_sub)
  );

  shifter8 u_sh (
    .a(a), .shamt(shamt),
    .y_shl(w_shl), .y_shr(w_shr), .y_ashr(w_ashr)
  );

  cmp8 u_cmp(
    .a(a), .b(b),
    .y_eq(w_eq), .y_lt(w_lt), .y_le(w_le), .y_gt(w_gt), .y_ge(w_ge)
  );

  // 聚合输出
  assign y_logic  = w_and ^ w_or;      // XOR
  assign y_arith  = w_add - w_sub;     // SUB
  assign y_shift  = w_ashr;            // ASHR

  // slice/concat
  assign y_slice  = a[5:2];
  assign y_concat = {a, b};

  assign y_final = sel ? y_shift : y_arith;

  assign y_eq = w_eq;
  assign y_lt = w_lt;
  assign y_le = w_le;
  assign y_gt = w_gt;
  assign y_ge = w_ge;

endmodule