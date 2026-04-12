module top(
  input  wire [15:0] a,
  input  wire [15:0] b,
  input  wire [15:0] c,
  output wire [15:0] y
);
  wire [15:0] s0 = (a & b) ^ c;
  wire [15:0] s1 = (s0 | a) ^ (b & ~c);
  wire [15:0] s2 = (s1 & (a ^ c)) | (~b);
  wire [15:0] s3 = (s2 ^ (b | c)) & (a | ~s0);
  wire [15:0] s4 = (s3 | (a & s1)) ^ (c & ~s2);
  wire [15:0] s5 = (s4 & (b ^ s0)) | (a ^ ~s3);
  wire [15:0] s6 = (s5 ^ s2) & (s4 | c);
  wire [15:0] s7 = (s6 | s1) ^ (s5 & ~a);
  assign y = s7 ^ s4;
endmodule
