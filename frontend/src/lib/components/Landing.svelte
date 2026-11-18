<script lang="ts">
	/**
	 * La portada de eptus: la superficie editorial, clara.
	 *
	 * Existe porque "/" es la herramienta y la herramienta necesita cuenta,
	 * CV y una vacante pegada. Quien llega sin cuenta no entiende nada de eso
	 * en los primeros dos segundos. Esta página cuenta el producto, enséña
	 * los precios en pesos y cierra con una sola acción.
	 *
	 * Los PRECIOS vienen de la API (`GET /v1/billing/plans`): la tabla de COP
	 * vive en el backend (`cop_prices.py`) y la muestra la pasarela que cobra.
	 * Duplicar el número acá sería una segunda fuente de verdad.
	 */
	import { onMount } from 'svelte';
	import { _, json, locale } from 'svelte-i18n';
	import { apiClient } from '$api/client';
	import type { Plan } from '$api/types';

	let plans: Plan[] = [];

	onMount(async () => {
		try {
			plans = await apiClient.plans();
		} catch {
			// Sin catálogo no hay precios: la sección se oculta en vez de
			// mostrar un cero, que sería un precio mentiroso.
			plans = [];
		}
	});

	const SHOWN = ['free', 'job_seeker_monthly', 'recruiter_starter'] as const;

	$: visiblePlans = SHOWN.map((id) => plans.find((p) => p.plan_id === id)).filter(
		(plan): plan is Plan => Boolean(plan)
	);

	function formatCop(value: number): string {
		return new Intl.NumberFormat($locale === 'en' ? 'en-US' : 'es-CO', {
			style: 'currency',
			currency: 'COP',
			maximumFractionDigits: 0
		}).format(value);
	}

	function featuresFor(planId: string): string[] {
		const key =
			planId === 'free'
				? 'marketing.pricing.freeFeatures'
				: planId === 'job_seeker_monthly'
					? 'marketing.pricing.seekerFeatures'
					: 'marketing.pricing.recruiterFeatures';
		// Las listas se leen con `json`: `$_` formatea a string y svelte-i18n
		// avisa (y devuelve nada) cuando el mensaje no es texto.
		const value = $json(key);
		return Array.isArray(value) ? (value as string[]) : [];
	}

	function nameFor(planId: string): string {
		if (planId === 'free') return $_('marketing.pricing.free');
		if (planId === 'job_seeker_monthly') return $_('app.nav.jobSeekerPlan');
		return $_('marketing.pricing.forRecruiters');
	}

	const features = [
		{ key: 'match', title: 'match', body: 'body' },
		{ key: 'adapt', title: 'title', body: 'body' },
		{ key: 'audit', title: 'title', body: 'body' },
		{ key: 'offers', title: 'title', body: 'body' }
	] as const;

	const faqs = ['q1', 'q2', 'q3', 'q4'] as const;
	const steps = ['one', 'two', 'three'] as const;
</script>

<section class="landing">
	<!-- ===================== HERO ===================== -->
	<header class="hero">
		<p class="eyebrow">{$_('marketing.hero.kicker')}</p>
		<h1>
			{$_('marketing.hero.title')}
			<em>{$_('marketing.hero.accent')}</em>
		</h1>
		<p class="hero__subtitle">{$_('marketing.hero.subtitle')}</p>
		<div class="hero__actions">
			<a class="btn btn--primary" href="/signup">{$_('marketing.hero.ctaPrimary')}</a>
			<a class="btn btn--ghost" href="#planes">{$_('marketing.hero.ctaSecondary')}</a>
		</div>
		<ul class="hero__trust">
			<li>{$_('marketing.hero.trust1')}</li>
			<li>{$_('marketing.hero.trust2')}</li>
			<li>{$_('marketing.hero.trust3')}</li>
		</ul>
	</header>

	<!-- ===================== PASOS ===================== -->
	<section class="section" id="como-funciona">
		<h2 class="section__title">{$_('marketing.steps.heading')}</h2>
		<p class="section__subtitle">{$_('marketing.steps.subtitle')}</p>
		<ol class="steps">
			{#each steps as step, index}
				<li class="steps__item">
					<span class="steps__number">{String(index + 1).padStart(2, '0')}</span>
					<h3>{$_(`marketing.steps.${step}.title`)}</h3>
					<p>{$_(`marketing.steps.${step}.body`)}</p>
				</li>
			{/each}
		</ol>
	</section>

	<!-- ===================== FEATURES ===================== -->
	<section class="section" id="producto">
		<h2 class="section__title">{$_('marketing.features.heading')}</h2>
		<p class="section__subtitle">{$_('marketing.features.subtitle')}</p>
		<div class="features">
			{#each features as feature}
				<article class="features__item">
					<h3>{$_(`marketing.features.${feature.key}.title`)}</h3>
					<p>{$_(`marketing.features.${feature.key}.body`)}</p>
				</article>
			{/each}
		</div>
	</section>

	<!-- ===================== PLANES ===================== -->
	{#if visiblePlans.length > 0}
		<section class="section" id="planes">
			<h2 class="section__title">{$_('marketing.pricing.heading')}</h2>
			<p class="section__subtitle">{$_('marketing.pricing.subtitle')}</p>
			<div class="plans">
				{#each visiblePlans as plan}
					<article class="plans__item" class:plans__item--highlight={plan.plan_id === 'job_seeker_monthly'}>
						<p class="plans__name">{nameFor(plan.plan_id)}</p>
						<p class="plans__amount">
							{plan.price_cop === 0
								? $_('marketing.pricing.free')
								: formatCop(plan.price_cop)}
							{#if plan.price_cop > 0}
								<small>{$_('marketing.pricing.perMonth')}</small>
							{/if}
						</p>
						{#if plan.plan_id === 'job_seeker_monthly'}
							<p class="plans__badge">{$_('marketing.pricing.mostPopular')}</p>
						{/if}
						<ul class="plans__features">
							{#each featuresFor(plan.plan_id) as feature}
								<li>{feature}</li>
							{/each}
						</ul>
						<a class="btn btn--primary plans__cta" href="/signup">
							{plan.price_cop === 0 ? $_('marketing.hero.ctaPrimary') : $_('marketing.pricing.cta')}
						</a>
					</article>
				{/each}
			</div>
		</section>
	{/if}

	<!-- ===================== FAQ ===================== -->
	<section class="section" id="faq">
		<h2 class="section__title">{$_('marketing.faq.heading')}</h2>
		<dl class="faq">
			{#each faqs as faq}
				<div class="faq__item">
					<dt>{$_(`marketing.faq.${faq}`)}</dt>
					<dd>{$_(`marketing.faq.a${faq.slice(1)}`)}</dd>
				</div>
			{/each}
		</dl>
	</section>

	<!-- ===================== CTA FINAL ===================== -->
	<section class="final">
		<h2>{$_('marketing.final.title')}</h2>
		<p>{$_('marketing.final.body')}</p>
		<a class="btn btn--primary" href="/signup">{$_('marketing.final.cta')}</a>
	</section>
</section>

<style>
	.landing {
		display: flex;
		flex-direction: column;
		gap: var(--space-9);
	}

	/* --- Hero --------------------------------------------------------------- */
	.hero {
		padding: var(--space-9) 0 var(--space-8);
		max-width: 46rem;
	}

	.hero h1 {
		margin: var(--space-4) 0 var(--space-5);
		font-size: var(--text-display-lg);
		line-height: 1.02;
		letter-spacing: var(--tracking-tighter);
		font-weight: 600;
		color: var(--color-ink-strong);
	}

	.hero h1 em {
		font-style: normal;
		color: var(--color-action);
	}

	.hero__subtitle {
		margin: 0 0 var(--space-6);
		font-size: var(--text-lg);
		line-height: var(--leading-relaxed);
		color: var(--color-ink-muted);
		max-width: 38rem;
	}

	.hero__actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		margin-bottom: var(--space-5);
	}

	.hero__trust {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-5);
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.hero__trust li {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.hero__trust li::before {
		content: '';
		width: 5px;
		height: 5px;
		border-radius: var(--radius-circle);
		background: var(--color-action);
	}

	/* --- Secciones ---------------------------------------------------------- */
	.section {
		padding-top: var(--space-7);
		border-top: var(--border-width) solid var(--color-line);
	}

	.section__title {
		margin: 0;
		font-size: var(--text-3xl);
		line-height: var(--leading-tight);
		letter-spacing: var(--tracking-tighter);
		font-weight: 600;
		color: var(--color-ink-strong);
	}

	.section__subtitle {
		margin: var(--space-3) 0 var(--space-6);
		font-size: var(--text-lg);
		color: var(--color-ink-muted);
		max-width: 40rem;
	}

	/* --- Pasos -------------------------------------------------------------- */
	.steps {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: var(--space-6);
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.steps__item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-4);
		border-top: var(--border-width-thick) solid var(--color-ink-strong);
	}

	.steps__number {
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		letter-spacing: var(--tracking-wide);
		color: var(--color-action);
	}

	.steps__item h3 {
		margin: 0;
		font-size: var(--text-lg);
		letter-spacing: var(--tracking-tight);
		color: var(--color-ink-strong);
	}

	.steps__item p {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
	}

	/* --- Features ----------------------------------------------------------- */
	.features {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: var(--space-5);
	}

	.features__item {
		padding: var(--space-5);
		background: var(--color-surface);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card-lg);
		box-shadow: var(--clay-raised);
	}

	.features__item h3 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-md);
		letter-spacing: var(--tracking-tight);
		color: var(--color-ink-strong);
	}

	.features__item p {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
	}

	/* --- Planes ------------------------------------------------------------- */
	.plans {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 0;
		border-top: var(--border-width) solid var(--color-line);
	}

	.plans__item {
		display: flex;
		flex-direction: column;
		padding: var(--space-5) var(--space-6);
		border-left: var(--border-width) solid var(--color-line);
	}

	.plans__item:first-child {
		border-left: none;
		padding-left: 0;
	}

	.plans__item--highlight {
		background: var(--color-surface);
		border-radius: var(--radius-card-lg);
		border-left: none;
		box-shadow: var(--clay-raised);
	}

	.plans__name {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-ink-muted);
	}

	.plans__amount {
		margin: var(--space-3) 0 var(--space-2);
		font-size: var(--text-4xl);
		font-weight: 600;
		letter-spacing: var(--tracking-tighter);
		color: var(--color-ink-strong);
	}

	.plans__amount small {
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--color-ink-muted);
		letter-spacing: 0;
	}

	.plans__badge {
		margin: 0 0 var(--space-3);
		font-size: var(--text-2xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-action);
	}

	.plans__features {
		margin: var(--space-3) 0 var(--space-5);
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.plans__features li {
		padding-left: var(--space-4);
		position: relative;
	}

	.plans__features li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.55em;
		width: 4px;
		height: 4px;
		border-radius: var(--radius-circle);
		background: var(--color-line-strong);
	}

	.plans__cta {
		margin-top: auto;
		align-self: flex-start;
	}

	/* --- FAQ ---------------------------------------------------------------- */
	.faq {
		margin: 0;
		display: flex;
		flex-direction: column;
	}

	.faq__item {
		display: grid;
		grid-template-columns: minmax(220px, 1fr) 2fr;
		gap: var(--space-5);
		padding: var(--space-4) 0;
		border-bottom: var(--border-width) solid var(--color-line);
	}

	.faq__item dt {
		font-weight: 600;
		color: var(--color-ink-strong);
	}

	.faq__item dd {
		margin: 0;
		color: var(--color-ink-muted);
		line-height: var(--leading-relaxed);
	}

	/* --- CTA final ---------------------------------------------------------- */
	.final {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-3);
		padding: var(--space-8) var(--space-6);
		background: var(--color-surface);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-panel);
	}

	.final h2 {
		margin: 0;
		font-size: var(--text-3xl);
		letter-spacing: var(--tracking-tighter);
		color: var(--color-ink-strong);
	}

	.final p {
		margin: 0 0 var(--space-3);
		color: var(--color-ink-muted);
		max-width: 36rem;
	}

	@media (max-width: 640px) {
		.hero {
			padding-top: var(--space-7);
		}

		.hero h1 {
			font-size: var(--text-display);
		}

		.faq__item {
			grid-template-columns: 1fr;
			gap: var(--space-2);
		}

		.plans__item {
			border-left: none;
			padding-left: 0;
			padding-right: 0;
		}
	}
</style>
