# PR 本文 — `FIX: OSS_DRV in OSS_FRAME_GIO`

そのまま GitHub の PR 説明欄に貼れます。

| | |
|---|---|
| repo | `OpenSUSI/TR-1um` |
| base | `dev`（`6afbd91`） |
| head | `fix/oss-drv-gio-frame`（コミット `4932b5e`） |
| file | `libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds` |

```sh
cd ~/HogeHoge/OpenPDK/TR-1um
git push -u origin fix/oss-drv-gio-frame
open "https://github.com/OpenSUSI/TR-1um/compare/dev...fix/oss-drv-gio-frame?expand=1"
```

---

## Title

```
FIX: OSS_DRV in OSS_FRAME_GIO
```

## Body

```markdown
## What

Replaces the `OSS_DRV` (output driver) cell inside
`libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds` with the version that
`TR-1um_TD4` and `TR-1um_I2C_2026` were actually taped out with.

**Only `OSS_DRV` changes.** The other 28 structures in the library are
byte-identical — verified by hashing each `BGNSTR..ENDSTR` payload with the
timestamp records excluded:

| structure | before | after |
|---|---|---|
| `OSS_DRV` | `9f1e224b7c` | **`3fb5dc3f3f`** |
| 28 others | — | unchanged |

## Geometry diff

`OSS_DRV`, counted as unique coordinate sets per layer:

| layer | | before | after | |
|---|---|---:|---:|---|
| (3,1) | `AP` | 7 | **9** | +2 |
| (3,2) | `AN` | 12 | **14** | +2 |
| (8,1) | `GC` | 14 | 14 | 2 moved |
| (11,0) | `CO` | 96 | **84** | −12 |
| (13,0) | `M1` | 25 | 25 | 2 moved |
| (140,0) | `WN` | 2 | 2 | — |
| (48,1)/(49,1) | pins | 3 / 3 | 3 / 3 | — |

`SREF` (`cont_g` ×3, `diode_n` ×2, `via_1$1` ×8) and the 8 labels are unchanged.

## Why

This variant has been in use since

* `TR-1um_TD4` — 2026-09-11
* `TR-1um_I2C_2026` — 2026-09-14

but was never upstreamed, so both designs are built on a frame that does not
exist in this repository. I checked every revision of
`TR-1um_frame_25x25_GIO.gds` on every branch (`main`, `dev`, `dev_jun1okamura`,
`development_jun` and their remotes): `OSS_DRV` only ever had two contents
here — `0ea0db9798` (`e2eaa91`, `7eeee5f`) and `9f1e224b7c` (`146b1ed`,
`64e40f5`, `a43feef`, `f6ab900`). Neither is what those two designs use.

`TR-1um_SCLK_SPI` and `TR-1um_Async_I2C` are on the current upstream version,
so the two families have diverged.

Both TD4 and I2C_2026 passed DRC / LVS / ngspice with the version in this PR.

## Reproducing the comparison

```python
import struct, hashlib

def structures(path):
    """{structure name: md5 of its BGNSTR..ENDSTR payload, timestamps excluded}"""
    d = open(path, 'rb').read(); i = 0; cur = None; buf = bytearray(); out = {}
    while i < len(d) - 4:
        ln, rt = struct.unpack('>HH', d[i:i+4]); body = d[i+4:i+ln]
        if ln < 4: break
        if rt == 0x0502:                      # BGNSTR
            buf = bytearray()
        elif rt == 0x0606:                    # STRNAME
            cur = body.rstrip(b'\x00').decode()
        elif rt == 0x0700:                    # ENDSTR
            out[cur] = hashlib.md5(bytes(buf)).hexdigest()[:10]; cur = None
        elif cur is not None:
            buf += struct.pack('>HH', ln, rt) + body
        i += ln
    return out
```

## Note on file naming (separate issue, not fixed here)

This repository ships two frames whose base names collide once one of them is
copied elsewhere:

| file | structures | has `OSS_FRAME_GIO` |
|---|---:|---|
| `TR-1um_frame_25x25.gds` | 23 | no — analog pads (`OSS_ESD_5V_ANA`) |
| `TR-1um_frame_25x25_GIO.gds` | 29 | yes — `OSS_ESD_5V_DIO` / `OSS_DRV` / `OSS_*CH_DRV` |

Downstream repositories have been copying the GIO one under the *non-GIO*
name (`lef/TR-1um_frame_25x25.gds`), which is how this divergence went
unnoticed for a while. Anything resolving the frame by base name picks up the
wrong file. Worth considering a rename or a note in the library README.
```
