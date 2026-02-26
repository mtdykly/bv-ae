// 覆盖 SHL SHR ASHR
module top(
  input  wire [7:0] x,
  input  wire [2:0] sh,
  output wire [7:0] y_shl,
  output wire [7:0] y_shr,
  output wire [7:0] y_ashr
);
  assign y_shl  = x << sh;
  assign y_shr  = x >> sh;
  assign y_ashr = $signed(x) >>> sh;
endmodule