# eptus — Paleta y roles semánticos (issue #57)

Paleta sobria: estructura suiza + superficies "clay", con el **índigo de
marca** (`--color-action`) separado de los estados. Todos los pares
texto/fondo están validados automáticamente en
`frontend/src/lib/tokens/contrast.test.ts` (52+ aserciones, AA 4.5:1 /
UI 3:1 / AAA body 7:1). Los comentarios de este documento citan el ratio
medido; si cambiás un valor, el test te lo va a reclamar.

> La identidad (marca, logo, uso) está en [`brand.md`](./brand.md).

## Mapping de nombres

Los nombres propuestos en el issue #57 mapean al vocabulario canónico del
repo (precedente de #54: el vocabulario shipped es la fuente de verdad):

| Nombre en el issue | Token canónico | Valor (light) | Ratio clave |
|---|---|---|---|
| `--color-bg` | `--color-canvas` | `#f8f8fc` | ink encima: 15.85:1 (**AAA**) |
| `--color-bg-elevated` | `--color-surface` | `#ffffff` | ink encima: 16.80:1 |
| `--color-bg-sunken` | `--color-surface-alt` | `#f1f1f9` | ink encima: 14.95:1 |
| `--color-fg` | `--color-ink` | `#1c1c2b` | — |
| `--color-fg-muted` | `--color-ink-muted` | `#4c4c63` | sobre surface: 8.33:1 (**AAA**) |
| `--color-fg-subtle` | `--color-line-strong` (dual-use) | `#6b6b83` | 4.89 canvas / 5.18 surface (**AA**) |
| `--color-accent` | `--color-action` | `#4f46e5` | on-action encima: 6.29:1 |
| `--color-accent-hover` | `--color-accent-hover` | `#4338ca` | on-action encima: 7.90:1 (**AAA**) |
| `--color-accent-pressed` | `--color-accent-pressed` | `#3730a3` | on-action encima: 9.93:1 (**AAA**) |
| `--color-success` | `--color-success` | `#047857` | on-success: 5.48:1 |
| `--color-warning` | `--color-warning` | `#92400e` | warning-as-text en muted: 6.84:1 |
| `--color-danger` | `--color-danger` | `#b91c1c` | on-danger: 6.47:1 |
| `--color-info` | `--color-info` | `#4f46e5` | on-info: 6.29:1 |
| `--color-border` | `--color-line` | `#e3e4ef` | hairline decorativa (exenta 1.4.11) |
| `--color-border-strong` | `--color-line-strong` | `#6b6b83` | 4.89 canvas / 5.18 surface (≥3:1 ✓) |

## Contrato de uso

1. **Textos sobre tintes pálidos** (`--color-X-muted`): el texto es el
   color REGULAR (`--color-X`), nunca el on-color blanco (mediría ~1:1).
2. **Chips invertidos** (fondo oscuro + label blanco): `--color-on-X` sobre
   `--color-X` — los fills están tuneados para blanco ≥4.5:1.
3. **Score fills** (`--score-low/mid/high`): Layer 0, mode-invariant;
   el label es siempre `--color-on-score-fill` (#ffffff, 4.83/7.09/5.48).
4. **`--color-line`** es hairline decorativa — NO usar como único cue de
   un control esencial; para eso existe `--color-line-strong` (≥3:1).
5. **Hover/pressed de action buttons**: `--color-accent-hover` /
   `--color-accent-pressed` como background; el label `--color-on-action`
   mantiene AA/AAA en ambos.
6. **El hue de marca (`--color-action`) no se usa para estados.** Éxito,
   warning y danger son semánticos; si el primario compartiera hue con el
   éxito, un botón de acción se leería como "estado: bueno".

## Dark theme

Cada token con override dark está en el bloque
`@media (prefers-color-scheme: dark)` de `app.css`, con el racional por
línea. Los accent steps se invierten (hover aclara, pressed oscurece)
porque en dark el contraste viene de luminancia sobre la superficie:

| Token | Dark | Label | Ratio |
|---|---|---|---|
| `--color-action` | `#a5b4fc` | `--color-on-action #1e1b4b` | 8.02:1 |
| `--color-accent-hover` | `#c7d2fe` | `--color-on-action #1e1b4b` | 10.72:1 |
| `--color-accent-pressed` | `#a5b4fc` | `--color-on-action #1e1b4b` | 8.02:1 |

## Dónde vive cada cosa

- Tokens CSS: `frontend/src/app.css` (5 capas documentadas, light + dark + reduced-motion).
- Registro TS: `frontend/src/lib/tokens/colors.ts` (+ `contrast.test.ts` con la paridad byte-a-byte).
- Identidad y uso de marca: `docs/brand.md`.
- Issue: #57 (T1 mergeado en PR #97, T2 en este PR).
