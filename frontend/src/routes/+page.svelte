<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import JdForm from '$components/JdForm.svelte';
	import MatchResult from '$components/MatchResult.svelte';
	import { analysisStore } from '$stores/analysis';
	import { profileStore } from '$stores/profile';
	import { apiClient } from '$api/client';
	import { isAuthenticated } from '$stores/session';
	import { ApiError, type SubscriptionInfo } from '$api/types';

	let subscription: SubscriptionInfo | null = null;
	// 'unknown' | 'none' | 'some'. Si el usuario tiene un CV, el perfil se arma
	// solo a partir de ese CV en el primer match: no hay que anunciarle que
	// "no tiene perfil" cuando en realidad ya tiene el CV con el que crearlo.
	let cvState: 'unknown' | 'none' | 'some' = 'unknown';
	let setupError = '';

	onMount(async () => {
		if (!get(isAuthenticated)) return;
		try {
			subscription = await apiClient.subscription();
		} catch {
			subscription = null;
		}
		try {
			cvState = (await apiClient.listCvs()).length > 0 ? 'some' : 'none';
		} catch {
			cvState = 'none';
		}
	});

	function usageLabel(): string {
		if (!subscription) return '';
		const matches = subscription.usage['matches_this_month'];
		const limit = subscription.limits['matches_per_month'];
		if (typeof matches !== 'number') return '';
		if (typeof limit !== 'number' || limit <= 0) {
			return $_('billing.usageUnlimited', { values: { used: matches } });
		}
		return $_('billing.usage', { values: { used: matches, limit } });
	}

	/**
	 * Garantiza un Profile propio para el contexto del match; lo crea desde el
	 * CV del usuario si falta (issue #132).
	 *
	 * Antes esto vivía en /profile (`ensureProfile`) y se perdió al mover el
	 * match a la home (#109): `profileStore` se quedaba en null y el submit
	 * salía con un `return` silencioso, así que "Analizar" no hacía nada para
	 * ningún usuario nuevo — ni request, ni error, ni spinner.
	 *
	 * La API ya expone POST /v1/profiles con ownership real (`owner_user_id`),
	 * así que el perfil se arma desde el CV que el usuario ya cargó.
	 */
	async function ensureProfile(): Promise<number> {
		const current = get(profileStore);
		if (current !== null) {
			try {
				await apiClient.getProfile(current);
				return current;
			} catch {
				// 404 = no existe o pertenece a otro usuario. En ambos casos el id
				// cacheado es inservible: olvidarlo evita volver a apuntar al
				// perfil de alguien más (issue #85).
				profileStore.forget();
			}
		}

		const cvs = await apiClient.listCvs();
		const first = cvs[0];
		if (!first) {
			throw new ApiError($_('home.cvRequired'), 409, 'no_cv', 'NO_CV');
		}

		const detail = await apiClient.getCv(first.id);
		const structured = detail.structured ?? {};
		const created = await apiClient.createProfile({
			name:
				typeof structured.full_name === 'string' && structured.full_name
					? structured.full_name
					: 'CV',
			headline: null,
			experience: { items: structured.experience ?? [] },
			skills: { items: structured.skills ?? [] },
			preferences: { location: structured.location ?? null }
		});
		profileStore.set(created.id);
		return created.id;
	}

	async function handleSubmit(event: CustomEvent<{ jdText: string }>) {
		setupError = '';
		try {
			const profileId = await ensureProfile();
			await analysisStore.submit(event.detail.jdText, profileId);
		} catch (err) {
			// El store de análisis se ocupa de sus propios errores; aquí llega
			// el fallo de preparar el perfil (p. ej. que no haya CV todavía).
			setupError = err instanceof ApiError ? err.message : $_('error.title');
		}
	}

	function retry() {
		analysisStore.reset();
		setupError = '';
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('app.tagline')}</title>
</svelte:head>

<section class="home">
	<header class="home__intro">
		<h1>{$_('home.heading')}</h1>
		<p>{$_('home.intro')}</p>
		{#if $profileStore !== null}
			<p class="home__profile">
				{$_('home.profileLabel')}: <strong>#{$profileStore}</strong>
			</p>
		{:else if !$isAuthenticated || cvState === 'none'}
			<p class="home__profile" data-testid="home-no-profile">
				{$_('home.profileMissing')}
				<a href="/profile">{$_('home.profileMissingCta')}</a>
			</p>
		{/if}
		{#if $isAuthenticated && usageLabel()}
			<p class="home__usage">{usageLabel()}</p>
		{/if}
	</header>

	<JdForm on:submit={handleSubmit} loading={$analysisStore.status === 'loading'} />

	{#if $analysisStore.status === 'loading'}
		<section class="home__loading" aria-live="polite">
			<div class="home__spinner" aria-hidden="true"></div>
			<h2>{$_('loading.title')}</h2>
			<p>{$_('loading.subtitle')}</p>
			<small>{$_('loading.detail')}</small>
		</section>
	{/if}

	{#if $analysisStore.status === 'error'}
		<section class="home__error" role="alert">
			<h2>{$_('error.title')}</h2>
			<p>{$analysisStore.error}</p>
			<button type="button" on:click={retry}>{$_('error.retry')}</button>
		</section>
	{/if}

	{#if setupError}
		<section class="home__error" role="alert" data-testid="home-setup-error">
			<h2>{$_('error.title')}</h2>
			<p>{setupError}</p>
			<a class="home__setup-cta" href="/profile">{$_('home.profileMissingCta')}</a>
		</section>
	{/if}

	{#if $analysisStore.status === 'done' && $analysisStore.result}
		<MatchResult analysis={$analysisStore.result} />
		<a class="home__adapt-cta" href="/adapt">{$_('home.adaptCta')}</a>
	{/if}
</section>

<style>
	.home {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
	}

	.home__intro h1 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.home__intro p {
		margin: 0 0 var(--space-2);
		color: var(--color-ink-muted);
	}

	/* Match → adapt is the product's natural next step: the CTA rides the
	   result with the primary control treatment (control, so clay). El CTA de
	   setup comparte tratamiento porque es el mismo tipo de acción. */
	.home__adapt-cta,
	.home__setup-cta {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) solid transparent;
		border-radius: var(--radius-control);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		font-size: var(--text-sm);
		text-decoration: none;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.home__adapt-cta:hover,
	.home__setup-cta:hover {
		text-decoration: none;
		box-shadow: var(--clay-lifted);
	}

	.home__adapt-cta:focus-visible,
	.home__setup-cta:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.home__profile {
		font-size: var(--text-sm);
	}

	.home__usage {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	/* Status panels, not controls. Flat. */
	.home__loading,
	.home__error {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-5);
		border-radius: var(--radius-panel);
		text-align: center;
	}

	.home__loading {
		background: var(--color-surface);
		border: var(--border-width) solid var(--color-line);
	}

	.home__error {
		background: var(--color-danger-muted);
		color: var(--color-danger);
		border: var(--border-width) solid var(--color-danger);
	}

	.home__spinner {
		width: var(--space-6);
		height: var(--space-6);
		border-radius: var(--radius-circle);
		border: var(--border-width-heavy) solid var(--color-line);
		border-top-color: var(--color-action);
		animation: spin 0.9s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* A control: clay. */
	.home__error button {
		margin-top: var(--space-2);
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) solid var(--color-danger);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-danger);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.home__error button:hover {
		box-shadow: var(--clay-lifted);
	}

	.home__error button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}
</style>
