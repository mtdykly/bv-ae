module top(
  input  wire [63:0] a,
  input  wire [63:0] b,
  input  wire [5:0]  sh,
  input  wire [1:0]  sel,
  output wire [63:0] y
);
  wire [63:0] t0 = {a[31:0], b[63:32]};
  wire [63:0] t1 = {b[15:0], a[63:16]};
  wire [63:0] t2 = t0 + t1;
  wire [63:0] t3 = t2 << sh;
  wire [63:0] t4 = $signed(t2) >>> sh;
  wire [63:0] t5 = t3 ^ t4;
  assign y = (sel == 2'b00) ? t2 :
             (sel == 2'b01) ? t3 :
             (sel == 2'b10) ? t4 : t5;
endmodule
