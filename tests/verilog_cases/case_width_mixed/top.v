module top(
  input  signed [7:0] a,
  input         [2:0] c,

  output signed [7:0] y_add_u,
  output signed [7:0] y_add_s,
  output signed [7:0] y_sub_u,
  output signed [7:0] y_sub_s,

  output              y_lt_u,
  output              y_lt_s
);

  assign y_add_u = a + c;
  assign y_sub_u = a - c;
  assign y_lt_u  = (a < c);

  assign y_add_s = a + $signed(c);
  assign y_sub_s = a - $signed(c);
  assign y_lt_s  = ($signed(a) < $signed(c));

endmodule