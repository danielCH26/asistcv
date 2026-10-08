# Feature: V2.0 Claymorphism + Minimalismo Suizo (#60)

## Specs

> **S1**: Paleta teal corporativa (elección del usuario, 2026-10-08):
> - Light: action `#0f766e` (5.47:1 AA), hover `#115e59` (7.58:1), pressed `#134e4a` (9.48:1), muted `#ccfbf1`
> - Dark (acento claro, etiqueta oscura `#0f172a`): action `#5eead4` (12.07:1), hover `#99f6e4` (14.16:1), pressed `#2dd4bf` (9.59:1), muted `#134e4a`
> - Info tokens siguen la misma familia; focus ring rgba actualizado
> - teal-600 `#0d9488` descartado: 3.74:1 con blanco, falla AA

> **S2**: Header con identidad corporativa: logo con tratamiento clay, nav activa como pill clay, jerarquía más clara

> **S3**: Claymorphism consistente en botones primarios e inputs de TODAS las páginas (login/signup y billing usaban aliases legacy flat)

> **S4**: Cards con "pressed clay" sutil (MatchResult, AdaptationResult, ReasoningBox, plan-card)

> **S5**: Sin literales hardcoded: todo desde tokens (`--color-*`, `--clay-*`)

> **S6**: Documentar el sistema en `frontend/docs/design-system.md`

## Acceptance criteria

- [x] Paleta teal aplicada en light + dark, WCAG AA verificado por `contrast.test.ts` (commit `3be1cad`)
- [x] Header rediseñado (logo clay, nav pill) (commit `402d19d`)
- [x] Login/signup/billing con clay effects (commits `df7246a`, `395638f`)
- [x] Cards principales con pressed clay (commit `f8e6a40`)
- [x] `tokens.test.ts` y `contrast.test.ts` en verde (54 tests tokens, 112 total)
- [x] Sin aliases legacy en páginas tocadas (grep 0 matches en login/signup/billing)
- [x] Docs en `frontend/docs/design-system.md`

## Tasks

> **T1**: ✅ Swap paleta teal — commit `3be1cad` (app.css light+dark, colors.ts, shadow.ts; 54 tests tokens OK, sin hex azules residuales)

> **T2**: ✅ Header clay — commit `402d19d` (logo chip teal clay, pill activa 600+elevación, signup control clay completo; 112 tests + svelte-check OK)

> **T3**: ✅ Auth clay — commit `df7246a` (inputs clay-fill/raised/focus-ring, submit control clay, 0 aliases legacy; 112 tests + svelte-check OK)

> **T4**: ✅ Billing clay — commit `395638f` (portal/choose clay secundario, Subscribe CTA primaria con disabled sin sombra, plan-cards clay-raised, 0 aliases; 112 tests OK)

> **T5**: ✅ Cards clay — commit `f8e6a40` (MatchResult/AdaptationResult/ReasoningBox +clay-raised; ya usaban tokens modernos; ScoreCard intacta)

> **T6**: ✅ Docs — commit de docs con `frontend/docs/design-system.md` + este feature doc. Verificación final: 112 tests, svelte-check 0 errores, `npm run build` OK

## Log

- L1: "me gusta la paleta de colores que definiste, para el resto toma las desiciones segun convengan mejor visualmente y en la calidad del proyecto" — sesión anterior
- L2: "aun no veo los cambios en el estilo del front [...] me gustaria ver los cambios solicitados en sesiones anteriores en el menu superior y el cambio de la paleta de colores por una mas corporativa y fresca" — sesión actual
- L3: Usuario eligió scope "Header + paleta" y paleta "Teal corporativo" (#0d9488 family, ajustada a teal-700+ por WCAG AA)
- L4: Inventarios completos en Engram (`odd/v2-clay-swiss`): explorador mapeó qué falta (login/signup/billing sin clay, cards flat, aliases legacy)
