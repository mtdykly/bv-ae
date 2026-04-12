module top(
  input  wire [127:0] a,
  input  wire [127:0] b,
  input  wire [127:0] c,
  input  wire [127:0] d,
  input  wire [6:0] sh,
  input  wire sel,
  output wire [127:0] y,
  output wire flag
);
  wire [127:0] n0 = (a ^ b) + c;
  wire [127:0] n1 = (n0 & d) | (~a);
  wire [127:0] n2 = (n1 << sh) ^ (b >> sh);
  wire signed [127:0] n1s = n1;
  wire [127:0] n3 = n1s >>> sh;
  wire [127:0] n4 = {{n2[63:0], n3[127:64]}} ^ n0;
  wire lt = (n4 < c);
  wire eq = (n2 == n3);
  wire [127:0] n5 = sel ? (n4 + d) : (n4 - b);
  wire [127:0] n6 = lt ? (n5 ^ n1) : (n5 | n0);
  assign y = eq ? n6 : (n6 & ~n3);
  assign flag = lt ^ eq;
endmodule
