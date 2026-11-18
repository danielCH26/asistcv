<script lang="ts">
	import '../app.css';
	import { setupI18n } from '$i18n/index';
	import LanguageToggle from '$components/LanguageToggle.svelte';
	import Logo from '$components/Logo.svelte';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';
	import { isAuthenticated, isRecruiter, logout, sessionEmail } from '$stores/session';
	import { initClerk } from '$lib/clerk';
	import { onMount } from 'svelte';

	setupI18n();

	onMount(() => {
		void initClerk();
	});

	$: pathname = $page.url.pathname;

	/**
	 * Dos superficies.
	 *
	 * La PORTADA (marketing) es clara y editorial: es donde se convierte.
	 * La APP es oscura e instrumentada: es donde se trabaja.
	 *
	 * La portada aparece cuando la persona NO tiene cuenta: si ya la tiene,
	 * "/" es la herramienta y tiene que verse como la herramienta. El funnel
	 * anónimo de auditoría (3 al día, sin registro) va en la misma superficie
	 * clara, porque es la puerta de entrada sin compromiso.
	 */
	$: isMarketing =
		pathname === '/login' ||
		pathname === '/signup' ||
		pathname === '/audit' ||
		(pathname === '/' && !$isAuthenticated);

	const year = new Date().getFullYear();
</script>

{#if isMarketing}
	<div class="marketing">
		<header class="marketing__header">
			<a class="marketing__brand" href="/">
				<span class="marketing__logo"><Logo size={24} /></span>
				<strong>{$_('app.title')}</strong>
			</a>

			<nav class="marketing__nav">
				<a href="/audit">{$_('marketing.nav.audit')}</a>
				<a href="/#planes">{$_('marketing.nav.pricing')}</a>
			</nav>

			<div class="marketing__actions">
				<LanguageToggle />
				<a class="marketing__login" href="/login">{$_('marketing.nav.login')}</a>
				<a class="btn btn--primary" href="/signup">{$_('marketing.nav.signup')}</a>
			</div>
		</header>

		<main class="marketing__main">
			<slot />
		</main>

		<footer class="marketing__footer">
			<div class="marketing__footer-grid">
				<div class="marketing__footer-brand">
					<span class="marketing__logo marketing__logo--footer"><Logo size={22} /></span>
					<p>{$_('app.tagline')}</p>
					<small>{$_('marketing.footer.madeIn')}</small>
				</div>

				<div class="marketing__footer-col">
					<h3>{$_('marketing.footer.product')}</h3>
					<a href="/">{$_('marketing.footer.match')}</a>
					<a href="/adapt">{$_('marketing.footer.adapt')}</a>
					<a href="/audit">{$_('marketing.footer.audit')}</a>
					<a href="/job-offers">{$_('marketing.footer.offers')}</a>
				</div>

				<div class="marketing__footer-col">
					<h3>{$_('marketing.footer.account')}</h3>
					<a href="/login">{$_('marketing.footer.login')}</a>
					<a href="/signup">{$_('marketing.footer.signup')}</a>
					<a href="/#planes">{$_('marketing.footer.pricing')}</a>
				</div>

				<div class="marketing__footer-col">
					<h3>{$_('marketing.footer.legal')}</h3>
					<a href="/privacy">{$_('marketing.footer.privacy')}</a>
					<a href="/terms">{$_('marketing.footer.terms')}</a>
					<a href="mailto:hola@eptus.com">{$_('marketing.footer.contact')}</a>
				</div>
			</div>

			<p class="marketing__footer-rights">
				{$_('marketing.footer.rights', { values: { year } })}
			</p>
		</footer>
	</div>
{:else}
	<div class="app-shell" data-surface="app">
		<header class="app-shell__header">
			<a class="app-shell__brand" href="/">
				<span class="app-shell__logo"><Logo size={24} /></span>
				<span class="app-shell__title">
					<strong>{$_('app.title')}</strong>
					<small>{$_('app.tagline')}</small>
				</span>
			</a>

			<nav class="app-shell__nav">
				<a class="app-shell__link" class:is-active={pathname === '/'} href="/">{$_('app.nav.home')}</a>
				<a
					class="app-shell__link"
					class:is-active={pathname.startsWith('/adapt')}
					href="/adapt">{$_('app.nav.jobAdapt')}</a
				>
				<a
					class="app-shell__link"
					class:is-active={pathname.startsWith('/history')}
					href="/history">{$_('app.nav.history')}</a
				>
				<a
					class="app-shell__link"
					class:is-active={pathname.startsWith('/job-offers')}
					href="/job-offers">{$_('app.nav.jobOffers')}</a
				>
				<a
					class="app-shell__link"
					class:is-active={pathname.startsWith('/audit')}
					href="/audit">{$_('app.nav.audit')}</a
				>
			</nav>

			<div class="app-shell__actions">
				{#if $isRecruiter}
					<a
						class="app-shell__link app-shell__link--quiet"
						class:is-active={pathname.startsWith('/recruiter')}
						href="/recruiter">{$_('app.nav.recruiter')}</a
					>
				{/if}
				<a
					class="app-shell__link app-shell__link--quiet"
					class:is-active={pathname.startsWith('/billing')}
					href="/billing">{$_('app.nav.billing')}</a
				>
				<a
					class="app-shell__link app-shell__link--quiet"
					class:is-active={pathname.startsWith('/profile')}
					href="/profile">{$_('app.nav.profile')}</a
				>
				<LanguageToggle />
				{#if $isAuthenticated}
					<button
						type="button"
						class="app-shell__session"
						title={$sessionEmail ?? ''}
						on:click={() => logout()}>{$_('app.nav.logout')}</button
					>
				{:else}
					<!-- Una persona sin sesión puede caer en cualquier ruta de la app
					     (un enlace compartido, un historial). Sin estos dos enlaces
					     no tenía ninguna forma de entrar. -->
					<a class="app-shell__link app-shell__link--quiet" href="/login"
						>{$_('marketing.nav.login')}</a
					>
					<a class="btn btn--primary app-shell__cta" href="/signup"
						>{$_('marketing.nav.signup')}</a
					>
				{/if}
			</div>
		</header>

		<main class="app-shell__main">
			<slot />
		</main>

		<footer class="app-shell__footer">
			<span>eptus</span>
			<span class="app-shell__footer-tag">{$_('marketing.footer.madeIn')}</span>
			<span class="app-shell__footer-tag">
				{$_('marketing.footer.rights', { values: { year } })}
			</span>
		</footer>
	</div>
{/if}

<style>
	/* =====================================================================
	   PORTADA — la superficie editorial, clara
	   ===================================================================== */
	.marketing {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
		background: var(--color-canvas);
	}

	.marketing__header {
		display: flex;
		align-items: center;
		gap: var(--space-6);
		padding: var(--space-4) var(--space-6);
		border-bottom: var(--border-width) solid var(--color-line);
		background: var(--color-canvas);
	}

	.marketing__brand {
		display: inline-flex;
		align-items: center;
		gap: var(--space-3);
		color: var(--color-ink-strong);
		font-size: var(--text-lg);
		letter-spacing: var(--tracking-tight);
	}

	.marketing__brand:hover {
		text-decoration: none;
	}

	.marketing__logo {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: var(--color-ink-strong);
	}

	.marketing__nav {
		display: flex;
		gap: var(--space-5);
		margin-left: var(--space-6);
	}

	.marketing__nav a {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.marketing__nav a:hover {
		color: var(--color-ink-strong);
		text-decoration: none;
	}

	.marketing__actions {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		margin-left: auto;
	}

	.marketing__login {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--color-ink-strong);
	}

	.marketing__main {
		flex: 1;
		width: 100%;
		max-width: var(--layout-marketing-max);
		margin: 0 auto;
		padding: 0 var(--space-6);
	}

	.marketing__footer {
		margin-top: var(--space-9);
		padding: var(--space-8) var(--space-6) var(--space-6);
		border-top: var(--border-width) solid var(--color-line);
		background: var(--color-surface);
	}

	.marketing__footer-grid {
		display: grid;
		grid-template-columns: 2fr repeat(3, 1fr);
		gap: var(--space-6);
		max-width: var(--layout-marketing-max);
		margin: 0 auto;
	}

	.marketing__footer-brand p {
		margin: var(--space-3) 0 var(--space-1);
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.marketing__footer-brand small {
		color: var(--color-ink-muted);
		font-size: var(--text-xs);
	}

	.marketing__logo--footer {
		color: var(--color-ink-strong);
	}

	.marketing__footer-col {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.marketing__footer-col h3 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-2xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-ink-muted);
	}

	.marketing__footer-col a {
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.marketing__footer-rights {
		max-width: var(--layout-marketing-max);
		margin: var(--space-7) auto 0;
		padding-top: var(--space-5);
		border-top: var(--border-width) solid var(--color-line);
		font-size: var(--text-xs);
		color: var(--color-ink-muted);
	}

	@media (max-width: 880px) {
		.marketing__header {
			flex-wrap: wrap;
			gap: var(--space-4);
		}

		.marketing__nav {
			order: 3;
			width: 100%;
			margin-left: 0;
		}

		.marketing__footer-grid {
			grid-template-columns: 1fr 1fr;
		}
	}

	@media (max-width: 640px) {
		.marketing__main {
			padding: 0 var(--space-4);
		}

		.marketing__header,
		.marketing__footer {
			padding-left: var(--space-4);
			padding-right: var(--space-4);
		}

		.marketing__footer-grid {
			grid-template-columns: 1fr;
		}
	}

	/* =====================================================================
	   APP — la superficie instrumentada, oscura
	   ===================================================================== */
	.app-shell {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
		background: var(--color-canvas);
		color: var(--color-ink);
	}

	.app-shell__header {
		display: flex;
		align-items: center;
		gap: var(--space-5);
		padding: var(--space-3) var(--space-6);
		background: var(--color-canvas);
		border-bottom: var(--border-width) solid var(--color-line);
	}

	.app-shell__brand {
		display: inline-flex;
		align-items: center;
		gap: var(--space-3);
		color: var(--color-ink-strong);
	}

	.app-shell__brand:hover {
		text-decoration: none;
	}

	.app-shell__logo {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--space-5);
		height: var(--space-5);
		/* El marco de la marca usa la tinta (estructura); la pieza lleva el
		   color de marca, y el token ya se invierte solo en la app. */
		color: var(--color-ink-strong);
	}

	.app-shell__title {
		display: flex;
		flex-direction: column;
		line-height: var(--leading-tight);
	}

	.app-shell__title strong {
		font-size: var(--text-md);
		letter-spacing: var(--tracking-tight);
	}

	.app-shell__title small {
		font-size: var(--text-2xs);
		color: var(--color-ink-muted);
	}

	.app-shell__nav {
		display: flex;
		gap: var(--space-1);
		margin-left: var(--space-4);
	}

	.app-shell__link {
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-control);
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.app-shell__link:hover {
		background: var(--color-surface-alt);
		color: var(--color-ink);
		text-decoration: none;
	}

	/* El activo NO se rellena: en una superficie oscura un bloque de color
	   compite con el contenido. El activo se marca con el color de marca y
	   una línea de acento abajo. */
	.app-shell__link.is-active {
		color: var(--color-ink-strong);
		background: var(--color-surface-alt);
	}

	.app-shell__link--quiet {
		color: var(--color-ink-muted);
	}

	.app-shell__actions {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-left: auto;
	}

	.app-shell__session {
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--color-surface);
		color: var(--color-ink);
		font-size: var(--text-sm);
		cursor: pointer;
		transition: border-color var(--duration-fast) var(--ease-standard);
	}

	.app-shell__session:hover {
		border-color: var(--color-line-strong);
	}

	.app-shell__session:focus-visible {
		outline: none;
		box-shadow: var(--clay-focus-ring);
	}

	.app-shell__cta {
		padding: var(--space-2) var(--space-3);
		font-size: var(--text-sm);
	}

	.app-shell__main {
		flex: 1;
		width: 100%;
		max-width: var(--layout-content-max);
		margin: 0 auto;
		padding: var(--space-7) var(--space-5);
	}

	.app-shell__footer {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-4) var(--space-6);
		border-top: var(--border-width) solid var(--color-line);
		color: var(--color-ink-muted);
		font-size: var(--text-xs);
	}

	.app-shell__footer-tag {
		color: var(--color-ink-muted);
	}

	@media (max-width: 880px) {
		.app-shell__header {
			flex-wrap: wrap;
			gap: var(--space-3);
			padding: var(--space-3) var(--space-4);
		}

		.app-shell__nav {
			order: 3;
			width: 100%;
			margin-left: 0;
			overflow-x: auto;
		}

		.app-shell__actions {
			margin-left: auto;
		}

		.app-shell__main {
			padding: var(--space-5) var(--space-4);
		}
	}
</style>
