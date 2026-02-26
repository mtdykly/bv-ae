# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `111X` |
| `b` | `00X1` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y_add` | 4 | 0 | `XXXX` | `0x0` | `0x0` | 4 | `[0, 15]` | `[-8, 7]` |
| `y_sub` | 4 | 0 | `1XXX` | `0x8` | `0x8` | 3 | `[8, 15]` | `[-8, -1]` |
