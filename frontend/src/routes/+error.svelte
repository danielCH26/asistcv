<script lang="ts">
	import { page } from '$app/stores';
	import { isAuthenticated } from '$stores/session';

	$: status = $page.status;
	$: is404 = status === 404;
	$: is500 = status >= 500;

	$: heading = is404
		? '404 — Página no encontrada'
		: is500
			? '500 — Error del servidor'
			: `${status} — Error`;

	$: message = is404
		? 'La página que buscás no existe o fue movida.'
		: is500
			? 'Algo salió mal en el servidor. Reintentá en unos minutos.'
			: $page.error?.message ?? 'Ocurrió un error inesperado.';

	$: showHome = isAuthenticated;
	$: homeHref = isAuthenticated ? '/profile' : '/';
</script>

<div class="error-page">
	<div class="error-page__card">
		<span class="error-page__status" aria-hidden="true">{status}</span>

		<h1 class="error-page__heading">
			{#if is404}
				Página no encontrada
			{:else if is500}
				Error del servidor
			{:else}
				Algo salió mal
			{/if}
		</h1>

		<p class="error-page__message">{message}</p>

		<div class="error-page__actions">
			<a href={homeHref} class="error-page__cta">
				Volver al inicio
			</a>
		</div>
	</div>
</div>

<style>
	.error-page {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 60vh;
		padding: var(--space-6);
	}

	.error-page__card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-4);
		max-width: 24rem;
		text-align: center;
		padding: var(--space-8) var(--space-6);
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-panel);
		box-shadow: var(--clay-raised);
	}

	.error-page__status {
		font-size: var(--text-6xl);
		font-weight: 700;
		color: var(--text-muted);
		line-height: 1;
		font-variant-numeric: tabular-nums;
		letter-spacing: -0.04em;
	}

	.error-page__heading {
		margin: 0;
		font-size: var(--text-xl);
		font-weight: 600;
		color: var(--text-strong);
	}

	.error-page__message {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--text-muted);
		line-height: var(--leading-relaxed);
	}

	.error-page__actions {
		margin-top: var(--space-2);
	}

	.error-page__cta {
		display: inline-flex;
		padding: var(--space-2) var(--space-5);
		background: var(--accent);
		color: var(--accent-contrast);
		border-radius: var(--radius-card);
		font-size: var(--text-sm);
		font-weight: 600;
		text-decoration: none;
		transition: background var(--duration-fast) var(--ease-standard);
	}

	.error-page__cta:hover {
		background: var(--accent-hover);
		text-decoration: none;
	}

	.error-page__cta:focus-visible {
		outline: 2px solid var(--focus-ring);
		outline-offset: 2px;
	}
</style>
