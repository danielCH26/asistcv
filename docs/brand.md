# eptus — identidad de marca

La marca vive en tres lugares y **cambian juntos, en el mismo commit**:

| Dónde | Qué | Archivo |
|---|---|---|
| Frontend | la marca (SVG inline, hereda el color) | `frontend/src/lib/components/Logo.svelte` |
| Frontend | favicon (tile índigo + marca blanca) | `frontend/static/favicon.svg` |
| Frontend | la marca suelta, para OG / redes | `frontend/static/logo-mark.svg` |
| Backend | copia del servidor, para los correos HTML | `backend/app/core/brand.py` |

> La geometría está **duplicada** a propósito: los correos se arman con
> strings (no hay motor de plantillas) y el backend no puede importar el SVG
> del frontend. Si cambia la marca, cambian los dos lados en el mismo commit.

## La marca

Una **"e" geométrica**: un anillo con una barra horizontal, con la boca
abierta abajo a la derecha. Es una letra geométrica —no un símbolo abstracto—
porque "eptus" se nombra en todas las pantallas: la marca tiene que leerse
como la primera letra de la palabra, incluso a 16 px.

Geometría (viewBox `0 0 32 32`, trazo `4.5`, extremos redondeados):

- el arco **arranca en el extremo derecho de la barra** (3 o'clock, `25.5 16`)
  y recorre casi todo el anillo hasta 45°: `M25.5 16 A9.5 9.5 0 1 0 22.72 22.72`;
- la barra cierra la horizontal: `M6.5 16 H25.5`.

El `sweep-flag` es `0` (antihorario) y `large-arc-flag` es `1` (>180°): con
los flags al revés la forma sale como una "G", que es el error más fácil de
cometer. Para iterar sobre la geometría, `qa-reports/logo-geometry2.html`
deja ver las variantes lado a lado.

**Por qué esta forma y no otra:** el header actual usaba un monograma de
texto ("CV") dentro de un tile. Un "CV" no es una marca —es una sigla— y
además ataba el producto a la búsqueda de currículos. Una "e" geométrica
funciona como favicon, como isotipo y como lockup, y el mismo glifo escala de
16 px a 48 px sin variantes.

### Reglas de uso

- **El color lo pone `--color-action`**, no el de la marca. En light es el
  índigo `#4f46e5`; en dark, el índigo claro `#a5b4fc`. La marca no tiene
  un color propio: tiene el color del tema.
- **El favicon es el excepción**: tile índigo `#4f46e5` con la marca en
  blanco, para que se lea sobre cualquier color de pestaña.
- **Zona de respeto**: el alto de la marca (26 px en el header). Nada
  adentro de esa caja.
- **Nunca** estirar, rotar ni cambiar el grosor del trazo.
- La marca es decorativa (`aria-hidden`): el nombre va siempre en texto.

## La paleta

Índigo profundo + neutros fríos con matiz violeta. El hue de marca
(`--color-action`) está **separado del verde de los estados** (éxito,
`score-high`), así que un botón primario nunca se lee como "estado: bueno".

Los tokens viven en `frontend/src/app.css` (canónico) y
`frontend/src/lib/tokens/colors.ts` (registro tipado). El test de paridad
`tokens.test.ts` exige que sean **byte-idénticos**, y `contrast.test.ts`
recalcula todos los pares WCAG desde esos hex en cada `vitest`.

### Tokens de marca (light)

| Token | Hex | Rol |
|---|---|---|
| `--color-action` | `#4f46e5` | hue de marca: botones, enlaces, focus |
| `--color-on-action` | `#ffffff` | label sobre el action (6.29:1) |
| `--color-action-muted` | `#e0e7ff` | fondo pálido para chips de marca |
| `--color-accent-hover` | `#4338ca` | hover (7.90:1 con el label) |
| `--color-accent-pressed` | `#3730a3` | pressed (9.93:1) |
| `--color-info` | `#4f46e5` | comparte el hue de marca (5.10:1 sobre su tinte) |

### Tokens de marca (dark)

| Token | Hex |
|---|---|
| `--color-action` | `#a5b4fc` |
| `--color-on-action` | `#1e1b4b` (8.02:1) |
| `--color-action-muted` | `#312e81` |
| `--color-accent-hover` | `#c7d2fe` |
| `--color-accent-pressed` | `#a5b4fc` |

En dark el label del action **se invierte** (oscuro sobre índigo claro): con
blanco daría 1.8:1.

### Los neutros fríos

| Token | Hex | Antes (AsistCV) |
|---|---|---|
| `--color-canvas` | `#f8f8fc` | `#f8fafc` |
| `--color-surface` | `#ffffff` | `#ffffff` |
| `--color-surface-alt` | `#f1f1f9` | `#f1f5f9` |
| `--color-line` | `#e3e4ef` | `#e2e8f0` |
| `--color-line-strong` | `#6b6b83` | `#64748b` |
| `--color-ink` | `#1c1c2b` | `#1f2937` |
| `--color-ink-strong` | `#111120` | `#0f172a` |
| `--color-ink-muted` | `#4c4c63` | `#475569` |

Los neutros llevan un punto de violeta: es lo que hace que el índigo no
parezca pegado sobre una superficie neutra genérica.

### Estados (no son marca, no se tocan)

`--color-success #047857` · `--color-warning #92400e` · `--color-danger #b91c1c` ·
los `--score-*` (fills mode-invariant) · `--color-on-score-fill #ffffff`.

## Ratios medidos (WCAG 2.1)

Los del esquema light, recalculados por `contrast.test.ts`:

| Par | Ratio |
|---|---|
| `--color-ink` sobre `--color-canvas` | 15.85:1 (AAA) |
| `--color-ink` sobre `--color-surface` | 16.80:1 |
| `--color-ink-muted` sobre `--color-surface` | 8.33:1 (AAA) |
| `--color-line-strong` sobre `--color-canvas` | 4.89:1 (≥3:1 de 1.4.11) |
| `--color-on-action` sobre `--color-action` | 6.29:1 (AA) |
| `--color-on-action` sobre `--color-accent-hover` | 7.90:1 (AAA) |
| `--color-on-action` sobre `--color-accent-pressed` | 9.93:1 (AAA) |
| `--color-action` sobre `--color-action-muted` | 5.10:1 (AA) |

El cuerpo de texto (ink sobre canvas) queda en 15.85:1, muy por encima del
AAA de 7:1 que el test exige.

## Lo que NO cambia en este rename

- Las claves de `localStorage` (`asistcv.session`, `asistcv.locale`,
  `asistcv.activeProfileId`): renombrarlas saca la sesión de todos los
  usuarios que ya tienen cuenta.
- El dominio (`asistcv-frontend.pages.dev`) y el nombre del repo.
- Los `id` de planos y los `price_id` de los proveedores de pago: cambiarlos
  rompe la suscripción de los que ya compraron.
- `EMAIL_FROM`: el dominio emisor tiene que estar verificado en Resend. El
  default es `eptus <noreply@eptus.com>`; en producción se sobreescribe con
  el dominio real.
