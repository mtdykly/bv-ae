module top(
  input  wire [7:0] a,
  input  wire [7:0] b,
  input  wire [2:0] sh,
  input  wire [1:0] sel,
  output wire [7:0] y
);
  wire [7:0] t = {a[3:0], b[7:4]};           // concat + extract
  wire [7:0] u = {b[1:0], a[7:2]};           // concat + extract
  wire [7:0] v = t << sh;                    // shift
  wire [7:0] w = u >> sh;                    // shift

  assign y = (sel == 2'b00) ? v :
             (sel == 2'b01) ? w :
             (sel == 2'b10) ? {v[3:0], w[3:0]} :
                              {w[7:4], v[7:4]};
endmodule