module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  input  wire [7:0] c,
  input  wire [7:0] d,
  input  wire [2:0] sh,
  input  wire sel,
  output wire [7:0] y,
  output wire flag
);
  wire [7:0] n0 = (a ^ b) + c;
  wire [7:0] n1 = (n0 & d) | (~a);
  wire [7:0] n2 = (n1 << sh) ^ (b >> sh);
  wire signed [7:0] n1s = n1;
  wire [7:0] n3 = n1s >>> sh;
  wire [7:0] n4 = {{n2[3:0], n3[7:4]}} ^ n0;
  wire lt = (n4 < c);
  wire eq = (n2 == n3);
  wire [7:0] n5 = sel ? (n4 + d) : (n4 - b);
  wire [7:0] n6 = lt ? (n5 ^ n1) : (n5 | n0);
  assign y = eq ? n6 : (n6 & ~n3);
  assign flag = lt ^ eq;
endmodule
