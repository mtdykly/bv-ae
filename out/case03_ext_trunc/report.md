# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `u` | `10XX` |
| `s` | `1X01` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 6 | 0 | `00XXXX` | `0x30` | `0x0` | 4 | `[0, 15]` | `[0, 15]` |
