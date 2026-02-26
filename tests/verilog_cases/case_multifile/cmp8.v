module cmp8(
  input  signed [7:0] a,
  input  signed [7:0] b,
  output y_eq,
  output y_lt,
  output y_le,
  output y_gt,
  output y_ge
);
  (* keep *) wire t_eq = (a == b);
  (* keep *) wire t_lt = ($signed(a) <  $signed(b));
  (* keep *) wire t_le = ($signed(a) <= $signed(b));
  (* keep *) wire t_gt = ($signed(a) >  $signed(b));
  (* keep *) wire t_ge = ($signed(a) >= $signed(b));

  assign y_eq = t_eq;
  assign y_lt = t_lt;
  assign y_le = t_le;
  assign y_gt = t_gt;
  assign y_ge = t_ge;
endmodule