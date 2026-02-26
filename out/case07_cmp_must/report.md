# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `0000XXXX` |
| `b` | `1111XXXX` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `lt` | 1 | 0 | `1` | `0x1` | `0x1` | 0 | `[1, 1]` | `[-1, -1]` |
| `ge` | 1 | 0 | `0` | `0x1` | `0x0` | 0 | `[0, 0]` | `[0, 0]` |
