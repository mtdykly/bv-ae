// 覆盖 EQ LT LE GT GE，并验证“必须真/必须假”判定
module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  output wire eq,
  output wire lt,
  output wire le,
  output wire gt,
  output wire ge
);
  assign eq = (a == b);
  assign lt = (a <  b);
  assign le = (a <= b);
  assign gt = (a >  b);
  assign ge = (a >= b);
endmodule