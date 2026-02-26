// 覆盖 ADD SUB
module top(
  input  wire [3:0] a,
  input  wire [3:0] b,
  output wire [3:0] y_add,
  output wire [3:0] y_sub
);
  assign y_add = a + b;
  assign y_sub = a - b;
endmodule
