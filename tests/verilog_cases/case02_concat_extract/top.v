// 覆盖 CONCAT + EXTRACT + 重排
module top(
  input  wire [3:0] a,
  input  wire [3:0] b,
  output wire [7:0] y
);
  wire [7:0] c = {a, b};
  assign y = {c[3:0], (c[7:4] ^ 4'b1010)};
endmodule