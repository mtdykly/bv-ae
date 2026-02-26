module top(
  input  signed [3:0] a_s,
  input  signed [3:0] b_s,
  input         [3:0] a_u,
  input         [3:0] b_u,

  output y_s_lt,
  output y_s_ge,
  output y_u_lt,
  output y_u_ge
);

  assign y_s_lt = (a_s <  b_s);
  assign y_s_ge = (a_s >= b_s);

  assign y_u_lt = (a_u <  b_u);
  assign y_u_ge = (a_u >= b_u);

endmodule