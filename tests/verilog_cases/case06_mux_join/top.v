// 覆盖 MUX
module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  input  wire [7:0] c,
  input  wire       s0,
  input  wire       s1,
  output wire [7:0] y
);
  wire [7:0] m0 = s0 ? a : b;
  assign y = s1 ? m0 : c;
endmodule