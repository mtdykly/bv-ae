# Abstract Evaluation Report

- top_module: `top`
- domain: `bv3`

## Inputs (assumptions)

| name | bits_msb |
| --- | --- |
| `a` | `00XX1100` |
| `b` | `00XX1111` |
| `c` | `00001111` |
| `s0` | `X` |
| `s1` | `X` |

## Outputs

| name | width | signed | bits_msb | known_mask_hex | known_value_hex | unknown_count | range_unsigned | range_signed |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
| `y` | 8 | 0 | `00XX11XX` | `0xcc` | `0xc` | 4 | `[12, 63]` | `[12, 63]` |
