// 覆盖比较算子“必须真 必须假”判定
module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  output wire lt,
  output wire ge
);
  assign lt = (a < b);
  assign ge = (a >= b);
endmodule