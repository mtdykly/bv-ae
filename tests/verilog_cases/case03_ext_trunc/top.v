// 覆盖 SEXT ZEXT TRUNC
module top(
  input  wire [3:0] u,
  input  wire signed [3:0] s,
  output wire [5:0] y
);
  wire [7:0] zext = {4'b0000, u};
  wire signed [7:0] sext = {{4{s[3]}}, s};
  wire signed [8:0] sum = $signed(zext) + sext; // 9 位临时和
  assign y = sum[5:0];
endmodule