# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `0001XX10` |
| `b` | `1110X0X1` |
| `sh` | `01X` |
| `sel` | `X` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 8 | 0 | `XXXXXXXX` | `0x0` | `0x0` | 8 | `[0, 255]` | `[-128, 127]` |
