# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `x` | `1X0010XX` |
| `sh` | `0XX` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y_shl` | 8 | 0 | `XXXXXXXX` | `0x0` | `0x0` | 8 | `[0, 255]` | `[-128, 127]` |
| `y_shr` | 8 | 0 | `XXXXXXXX` | `0x0` | `0x0` | 8 | `[0, 255]` | `[-128, 127]` |
| `y_ashr` | 8 | 0 | `1XXXXXXX` | `0x80` | `0x80` | 7 | `[128, 255]` | `[-128, -1]` |
