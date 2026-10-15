# Feature: IA — match y adaptación fuera de /profile (#108)

## Decisión de IA

- **Home (/)** = Match (ya existe ahí — el profile lo duplicaba funcionalmente)
- **`/profile`** = cuenta + onboarding + Mis CVs solamente
- **`/adapt`** (nueva) = flujo de adaptación extraído del profile
- Tab "Solo CV" del profile desaparece (el audit vive en `/audit` con link en el nav)
- Nav: + "Adaptar" (7 links, content-driven con wrap en mobile)
- CTA del resultado de match en Home → /adapt

## Specs

> **S1**: `/adapt` (nueva página): CV a adaptar (select de los CVs del usuario), textarea JD, botón adaptar, adaptaciones previas (GET /v1/adaptations/by-cv/{id}), resultado con approval flow si existe. Mismo comportamiento que la sección extraída.

> **S2**: `/profile`: remover sections profile__match (tabs + JdForm + resultado) y profile__adapt; remover el estado/lógica asociada (jdText, matching, matchResult, planLimitReached, runMatch, soloMode, activeTab, adapt state). Queda: user info, onboarding, Mis CVs.

> **S3**: Nav + "Adaptar" → /adapt. i18n: keys nuevas en ambos locales (nav.jobAdapt, adapt.*), paridad verificada.

> **S4**: Home: CTA "Adaptá tu CV" en/tras el resultado del match → /adapt (el flujo match → adaptar).

> **S5**: Limpieza i18n: keys que quedaron huérfanas tras quitar las secciones (verificar paridad).

> **S6**: vitest + svelte-check + CI verdes.

## Tasks

> **T1**: Writer: /adapt page + strip de /profile + nav + i18n (S1-S3, S5 — acoplados, un solo writer)

> **T2**: Home CTA → /adapt (S4)

> **T3**: Suite + PR + CI

## Log

- L1: Feedback del usuario en /profile (2026-10-09): match y adaptación "deberían tener su propia página por fuera del profile" — issue #108
- L2: Verificado: el match del profile duplica Home (mismo apiClient.match + profile_id); el tab Solo CV duplica /audit
