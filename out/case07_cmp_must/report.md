# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | spec |
| --- | --- |
| `a` | `bits_msb=0000XXXX` |
| `b` | `bits_msb=1111XXXX` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `eq` | 1 | 0 | `0` | `0x1` | `0x0` | 0 | `[0, 0]` | `[0, 0]` |
| `lt` | 1 | 0 | `1` | `0x1` | `0x1` | 0 | `[1, 1]` | `[-1, -1]` |
| `le` | 1 | 0 | `1` | `0x1` | `0x1` | 0 | `[1, 1]` | `[-1, -1]` |
| `gt` | 1 | 0 | `0` | `0x1` | `0x0` | 0 | `[0, 0]` | `[0, 0]` |
| `ge` | 1 | 0 | `0` | `0x1` | `0x0` | 0 | `[0, 0]` | `[0, 0]` |
