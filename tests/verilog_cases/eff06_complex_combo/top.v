module top(
  input  wire [63:0] a,
  input  wire [63:0] b,
  input  wire [63:0] c,
  input  wire [63:0] d,
  input  wire [5:0]  sh0,
  input  wire [5:0]  sh1,
  input  wire        sel0,
  input  wire        sel1,
  output wire [63:0] y_main,
  output wire [63:0] y_aux,
  output wire        flag
);
  wire [63:0] p0 = a + b;
  wire [63:0] p1 = c - d;
  wire [63:0] p2 = p0 ^ p1;
  wire [63:0] p3 = {p2[31:0], a[63:32]};
  wire [63:0] p4 = p3 << sh0;
  wire [63:0] p5 = p3 >> sh1;
  wire [63:0] p6 = $signed(p2) >>> sh0;
  wire        f0 = (p4 < p5);
  wire        f1 = (p6 >= p0);
  wire [63:0] m0 = sel0 ? p4 : p5;
  wire [63:0] m1 = sel1 ? m0 : p6;
  assign y_main = f0 ? (m1 + p1) : (m1 - p0);
  assign y_aux  = {y_main[31:0], p2[63:32]} ^ {p4[15:0], p5[15:0], p6[15:0], p1[15:0]};
  assign flag   = f0 ^ f1;
endmodule
