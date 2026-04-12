module top(
  input  wire [31:0] x,
  input  wire [31:0] y,
  input  wire [31:0] z,
  input  wire [4:0]  sh0,
  input  wire [4:0]  sh1,
  output wire [31:0] out,
  output wire        c0,
  output wire        c1
);
  wire [31:0] t0 = x << sh0;
  wire [31:0] t1 = y >> sh1;
  wire [31:0] t2 = $signed(z) >>> sh0;
  assign c0 = (t0 < t1);
  assign c1 = (t2 >= x);
  wire [31:0] m0 = c0 ? t0 : t1;
  wire [31:0] m1 = c1 ? m0 : t2;
  assign out = m1 ^ {t0[15:0], t1[15:0]};
endmodule
