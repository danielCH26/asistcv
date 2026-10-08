# AsistCV — Paleta y roles semánticos (issue #57)

Paleta sobria: estructura suiza + superficies clay. Todos los pares
texto/fondo están validados automáticamente en
`frontend/src/lib/tokens/contrast.test.ts` (52+ aserciones, AA 4.5:1 /
UI 3:1 / AAA body 7:1). Los comentarios de este documento citan el ratio
medido; si cambiás un valor, el test te lo va a reclamar.

## Mapping de nombres

Los nombres propuestos en el issue #57 mapean al vocabulario canónico del
repo (precedente de #54: el vocabulario shipped es la fuente de verdad):

| Nombre en el issue | Token canónico | Valor (light) | Ratio clave |
|---|---|---|---|
| `--color-bg` | `--color-canvas` | `#f8fafc` | ink encima: ~14.6:1 (**AAA**) |
| `--color-bg-elevated` | `--color-surface` | `#ffffff` | ink encima: ~15.4:1 |
| `--color-bg-sunken` | `--color-surface-alt` | `#f1f5f9` | ink encima: ~13.9:1 |
| `--color-fg` | `--color-ink` | `#1f2937` | — |
| `--color-fg-muted` | `--color-ink-muted` | `#475569` | sobre surface: 7.6:1 (**AAA**) |
| `--color-fg-subtle` | `--color-line-strong` (dual-use) | `#64748b` | 4.55 canvas / 4.76 surface (**AA**) |
| `--color-accent` | `--color-action` | `#0369a1` | on-action encima: 5.9:1 |
| `--color-accent-hover` | `--color-accent-hover` | `#075985` | on-action encima: ~7.9:1 (**AAA**) |
| `--color-accent-pressed` | `--color-accent-pressed` | `#0c4a6e` | on-action encima: ~10:1 (**AAA**) |
| `--color-success` | `--color-success` | `#047857` | on-success: 5.5:1 |
| `--color-warning` | `--color-warning` | `#92400e` | warning-as-text en muted: 7.1:1 |
| `--color-danger` | `--color-danger` | `#b91c1c` | on-danger: 5.9:1 |
| `--color-info` | `--color-info` | `#0369a1` | on-info: 5.9:1 |
| `--color-border` | `--color-line` | `#e2e8f0` | hairline decorativa (exenta 1.4.11) |
| `--color-border-strong` | `--color-line-strong` | `#64748b` | 4.55 canvas / 4.76 surface (≥3:1 ✓) |

## Contrato de uso

1. **Textos sobre tintes pálidos** (`--color-X-muted`): el texto es el
   color REGULAR (`--color-X`), nunca el on-color blanco (mediría ~1:1).
2. **Chips invertidos** (fondo oscuro + label blanco): `--color-on-X`
   sobre `--color-X` — los fills están tuneados para blanco ≥4.5:1.
3. **Score fills** (`--score-low/mid/high`): Layer 0, mode-invariant;
   el label es siempre `--color-on-score-fill` (#ffffff, 4.83/7.09/5.48).
4. **`--color-line`** es hairline decorativa — NO usar como único cue de
   un control esencial; para eso existe `--color-line-strong` (≥3:1).
5. **Hover/pressed de action buttons**: `--color-accent-hover` /
   `--color-accent-pressed` como background; el label `--color-on-action`
   mantiene AA/AAA en ambos.

## Dark theme

Cada token con override dark está en el bloque
`@media (prefers-color-scheme: dark)` de `app.css`, con el racional por
línea. Los accent steps se invierten (hover aclara, pressed oscurece)
porque en dark el contraste viene de luminancia sobre la superficie:

| Token | Dark | Label | Ratio |
|---|---|---|---|
| `--color-accent-hover` | `#7dd3fc` | `--color-on-action #0f172a` | ~13:1 |
| `--color-accent-pressed` | `#0ea5e9` | `--color-on-action #0f172a` | ~6:1 |

## Dónde vive cada cosa

- Tokens CSS: `frontend/src/app.css` (5 capas documentadas, light + dark + reduced-motion).
- Registro TS: `frontend/src/lib/tokens/colors.ts` (+ `contrast.test.ts` con la paridad byte-a-byte).
- Documento de contraste: `docs/security/service-principal.md` no; este archivo.
- Issue: #57 (T1 mergeado en PR #97, T2 en este PR).
