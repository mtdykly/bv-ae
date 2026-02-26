module alu8(
  input  signed [7:0] a,
  input  signed [7:0] b,
  output signed [7:0] y_and,
  output signed [7:0] y_or,
  output signed [7:0] y_xor,
  output signed [7:0] y_not,
  output signed [7:0] y_add,
  output signed [7:0] y_sub
);
  (* keep *) wire signed [7:0] t_and = a & b;
  (* keep *) wire signed [7:0] t_or  = a | b;
  (* keep *) wire signed [7:0] t_xor = a ^ b;
  (* keep *) wire signed [7:0] t_not = ~a;
  (* keep *) wire signed [7:0] t_add = a + b;
  (* keep *) wire signed [7:0] t_sub = a - b;

  assign y_and = t_and;
  assign y_or  = t_or;
  assign y_xor = t_xor;
  assign y_not = t_not;
  assign y_add = t_add;
  assign y_sub = t_sub;
endmodule