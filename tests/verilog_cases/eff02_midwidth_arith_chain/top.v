module top(
  input  wire [15:0] a,
  input  wire [15:0] b,
  input  wire [15:0] c,
  input  wire [15:0] d,
  output wire [15:0] y,
  output wire        f0,
  output wire        f1
);
  wire [15:0] s0 = a + b;
  wire [15:0] s1 = s0 - c;
  wire [15:0] s2 = s1 + d;
  wire [15:0] s3 = s2 - a;
  wire [15:0] s4 = s3 + (b - d);
  assign f0 = (s2 < a);
  assign f1 = (s4 >= c);
  wire [15:0] m0 = f0 ? s2 : s1;
  wire [15:0] m1 = f1 ? m0 : s4;
  wire [15:0] s5 = m1 + (a - b);
  wire [15:0] s6 = s5 - (c + d);
  assign y = f0 ? s6 : s5;
endmodule
