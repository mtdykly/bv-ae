# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `1X0X` |
| `b` | `0XX1` |
| `op` | `0XX` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 4 | 0 | `XXXX` | `0x0` | `0x0` | 4 | `[0, 15]` | `[-8, 7]` |
| `flag` | 1 | 0 | `0` | `0x1` | `0x0` | 0 | `[0, 0]` | `[0, 0]` |
