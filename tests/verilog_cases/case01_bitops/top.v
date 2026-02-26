// 覆盖 AND OR XOR NOT
module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  output wire [7:0] y
);
  wire [7:0] t1 = a & b;
  wire [7:0] t2 = ~a;
  wire [7:0] t3 = t2 | b;
  assign y = t1 ^ t3;
endmodule