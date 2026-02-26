# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `01X0101X` |
| `b` | `11X0010X` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 8 | 0 | `10X1010X` | `0xde` | `0x94` | 2 | `[148, 181]` | `[-108, -75]` |
