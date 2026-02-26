# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `0010XX01` |
| `b` | `1101X0X1` |
| `sh` | `0XX` |
| `sel` | `X0` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 8 | 0 | `XXXXXXXX` | `0x0` | `0x0` | 8 | `[0, 255]` | `[-128, 127]` |
