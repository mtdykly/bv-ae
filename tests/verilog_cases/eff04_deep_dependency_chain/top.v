module top(
  input  wire [31:0] a,
  input  wire [31:0] b,
  input  wire [31:0] c,
  output wire [31:0] y
);
  wire [31:0] s0  = a + b;
  wire [31:0] s1  = s0 ^ c;
  wire [31:0] s2  = s1 - (a >> 1);
  wire [31:0] s3  = s2 + {b[15:0], c[15:0]};
  wire [31:0] s4  = s3 ^ (s1 << 2);
  wire [31:0] s5  = s4 - (s0 >> 3);
  wire [31:0] s6  = s5 + (c << 1);
  wire [31:0] s7  = s6 ^ {s2[7:0], s4[23:0]};
  wire [31:0] s8  = s7 - (s3 << 1);
  wire [31:0] s9  = s8 + (s5 >> 2);
  wire [31:0] s10 = s9 ^ {s6[15:0], s7[15:0]};
  wire [31:0] s11 = s10 - (s8 >> 1);
  wire [31:0] s12 = s11 + {s9[23:0], s10[31:24]};
  wire [31:0] s13 = s12 ^ (s11 << 3);
  wire [31:0] s14 = s13 - (s12 >> 4);
  assign y = s14 + s10;
endmodule
