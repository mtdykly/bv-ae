// 综合混合
module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  input  wire [2:0] sh,
  input  wire       sel,
  output wire [7:0] y
);
  wire [7:0] p = {a[3:0], b[7:4]};      // concat + extract
  wire [7:0] q = (p + a);               // add
  wire [7:0] r = q >> sh;               // shift
  assign y = sel ? r : (q ^ b);         // mux + xor
endmodule