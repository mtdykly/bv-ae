module top(
  input  wire [3:0] a,
  input  wire [3:0] b,
  input  wire [2:0] op,
  output reg  [3:0] y,
  output wire       flag
);

  assign flag = (a < b);

  always @(*) begin
    case (op)
      3'b000: y = a + b;                 // ADD
      3'b001: y = a - b;                 // SUB
      3'b010: y = a & b;                 // AND
      3'b011: y = a | b;                 // OR
      3'b100: y = a ^ b;                 // XOR
      3'b101: y = a << b[1:0];           // SHL
      3'b110: y = a >> b[1:0];           // SHR
      3'b111: y = {3'b000, (a < b)};     // CMP -> LSB
      default: y = 4'b0000;
    endcase
  end
endmodule