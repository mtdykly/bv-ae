module shifter8(
  input  signed [7:0] a,
  input        [2:0] shamt,
  output signed [7:0] y_shl,
  output signed [7:0] y_shr,
  output signed [7:0] y_ashr
);
  (* keep *) wire signed [7:0] t_shl  = a << shamt;
  (* keep *) wire signed [7:0] t_shr  = a >> shamt;
  (* keep *) wire signed [7:0] t_ashr = a >>> shamt;

  assign y_shl  = t_shl;
  assign y_shr  = t_shr;
  assign y_ashr = t_ashr;
endmodule