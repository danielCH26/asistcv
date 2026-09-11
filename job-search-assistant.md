# Asistente de Búsqueda de Empleo

> Borrador de problema y solución. Sin detalle técnico — sirve para validar la idea, contar el proyecto a terceros, o usar como base para un PRD más adelante.

---

## TL;DR

Un asistente agéntico que ayuda a buscar trabajo de forma más inteligente: analiza descripciones de puestos, evalúa el match contra tu perfil, adapta tu CV, redacta el primer contacto, y trackea todo el proceso. El objetivo no es auto-aplicar a 100 puestos: es ayudarte a aplicar mejor a los 5-10 que sí valen la pena.

---

## El problema

Buscar trabajo hoy es un trabajo en sí mismo, y está roto en varios sentidos:

**1. El volumen mata la calidad.** Hay más ofertas abiertas que nunca, pero el formato es inconsistente: cada empresa describe el mismo puesto de 10 formas distintas. Leer 30 JDs para encontrar 5 buenos candidatos es una jornada entera.

**2. Adaptar el CV es agotador y se hace mal.** La mayoría de la gente adapta el CV cambiando tres palabras clave y reza. El resultado: ATS (sistemas automáticos de filtrado) lo descartan, y el reclutador nota que es genérico. Pierde match con puestos donde encajaría bien.

**3. La primera impresión se decide en el primer mensaje.** Un mail de outreach genérico ("adjunto mi CV, quedo atento") se ignora. Uno personalizado, breve, con contexto sobre la empresa, consigue respuestas. Pero escribirlos lleva tiempo y energía que no tenés cuando llevás 20 aplicaciones.

**4. El seguimiento se pierde.** ¿A quién le escribiste? ¿Cuándo? ¿Te respondieron? ¿Era la posición X o Y? Sin tracking, perdés oportunidades y duplicás esfuerzos.

**5. Decidir a qué aplicar es subjetivo y emocional.** Después de 20 rechazos, aplicás a todo. Después de un par de respuestas, te volvés selectivo sin razón. Falta un sistema que te dé una segunda opinión basada en hechos.

**El costo real**: para alguien que busca trabajo en serio (3-6 meses), esto significa 100+ horas de trabajo mecánico que podría enfocarse en preparar entrevistas, aprender, o descansar. Y aun así, el resultado suele ser peor que si cada aplicación tuviera 30 minutos de cuidado.

---

## La idea (solución propuesta)

Un producto que opera como un asistente personal de búsqueda de empleo, con tres capacidades centrales:

### 1. Decidir mejor
Tomás una descripción de puesto (pegás el texto o le pasás el link) y el sistema te dice en 30 segundos:

- Qué tan buen match es con tu perfil (un score honesto, no inflado)
- Por qué: qué skills encajan, cuáles faltan, qué se podría aprender rápido
- Cuánta energía vale la pena invertir (alto / medio / bajo)

No es un "sí o no" binario. Es una segunda opinión informada.

### 2. Aplicar mejor
Para los puestos que sí valen la pena, el sistema te ayuda a:

- Reescribir los bullets relevantes de tu CV para resaltar la experiencia que el puesto pide
- Redactar un primer mensaje (al reclutador o hiring manager) con tono configurable
- Investigar la empresa brevemente: tamaño, sector, qué hacen, señales de cultura

Vos revisás y aprobás antes de mandar nada. El sistema nunca envía nada por su cuenta.

### 3. No perder el hilo
Todo queda registrado en un panel personal: aplicaciones enviadas, status, fechas de seguimiento, próximos pasos. El sistema te recuerda cuándo hacer follow-up y qué aprendiste de cada interacción.

---

## Qué NO es

Esto es importante porque el espacio está lleno de herramientas con propuestas similares y diferentes problemas:

- **No es un auto-applier** tipo LazyApply o LoopCV que manda 100 CVs sin supervisión. Eso es spam, daña tu reputación a largo plazo, y los reclutadores lo detectan.
- **No es un generador de CVs** que te inventa experiencia. El sistema parte de tu CV real, solo reorganiza y resalta. Jamás agrega skills o logros que no tengas.
- **No es un chatbot más** estilo "consigue tu trabajo soñado con IA". Es una herramienta de trabajo que se gana su lugar ahorrándote tiempo real.
- **No reemplaza el trabajo humano** de buscar, entrevistar, decidir. Automatiza el 70% mecánico; el 30% estratégico sigue siendo tuyo.

---

## A quién ayuda

**Primario**: el propio autor del proyecto (durante su búsqueda actual). El uso real es el mejor motor de feedback.

**Secundarios** que podrían adoptarlo:

- **Desarrolladores en Latam** que aplican a empresas en US/EU y compiten contra candidatos locales con mejor posicionamiento geográfico. Un CV adaptado al mercado destino vale mucho.
- **Personas en transición de carrera** (junior → mid, o de otro rubro a tech) que más necesitan entender qué pide cada puesto y cómo presentar experiencia adyacente.
- **Pequeños equipos de recruiting** o consultoras de outplacement que atienden 10-50 candidatos a la vez y no pueden personalizar manualmente cada CV.

---

## Cómo se ve el éxito

El proyecto es exitoso si, al final de la búsqueda del autor:

- Se hicieron al menos 30 aplicaciones con el sistema como apoyo
- El 80% de las predicciones de match coincidieron con la decisión humana
- El tiempo promedio de evaluación de un JD bajó de 15 minutos a 2
- Se consiguieron al menos 3 entrevistas atribuibles a la calidad del CV/mensaje adaptado

Métricas secundarias que se pueden medir:
- Costo total por aplicación procesada
- Latencia de respuesta
- Tasa de respuestas positivas vs aplicaciones enviadas
- Calidad percibida de los CVs adaptados (evaluada con un panel de 3-5 personas)

---

## Por qué este proyecto vale la pena como portfolio

Tres razones que lo hacen destacar frente a un chatbot demo:

1. **Lo usa el autor en su propio flujo de trabajo.** No es un proyecto "armado para la entrevista". Está vivo y produce resultados medibles.
2. **Publica sus métricas y su proceso de evaluación.** Casi ningún proyecto GenAI muestra cuánto cuesta, cuánto tarda, y qué tan bien lo hace con datos reales.
3. **Demuestra criterio, no solo ejecución.** Optimiza por honestidad del match, por costo, por control humano. Es ingeniería, no magia.

---

## Estado actual

Borrador inicial. Aún no se ha construido.

Próximos pasos definidos en conversación:
- Validar el alcance con un mentor o con la propia experiencia de uso
- Definir el conjunto mínimo viable (qué entra en la primera versión)
- Construir un primer prototipo con un puesto real

---

*Documento vivo. Se actualiza a medida que el proyecto se valida o pivotea.*
