<script lang="ts">
	import '../app.css';
	import { setupI18n } from '$i18n/index';
	import LanguageToggle from '$components/LanguageToggle.svelte';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';

	setupI18n();

	$: pathname = $page.url.pathname;
</script>

<div class="app-shell">
	<header class="app-shell__header">
		<a class="app-shell__brand" href="/">
			<span class="app-shell__logo">CV</span>
			<span class="app-shell__title">
				<strong>{$_('app.title')}</strong>
				<small>{$_('app.tagline')}</small>
			</span>
		</a>

		<nav class="app-shell__nav">
			<a class="app-shell__link" class:is-active={pathname === '/'} href="/">{$_('app.nav.home')}</a>
			<a
				class="app-shell__link"
				class:is-active={pathname.startsWith('/history')}
				href="/history">{$_('app.nav.history')}</a
			>
		</nav>

		<LanguageToggle />
	</header>

	<main class="app-shell__main">
		<slot />
	</main>

	<footer class="app-shell__footer">
		<small>AsistCV · Sprint 1 PR-D1</small>
	</footer>
</div>

<style>
	.app-shell {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
	}

	.app-shell__header {
		display: flex;
		align-items: center;
		gap: 1.5rem;
		padding: 1rem 1.5rem;
		background: var(--surface);
		border-bottom: 1px solid var(--border);
	}

	.app-shell__brand {
		display: inline-flex;
		align-items: center;
		gap: 0.65rem;
		color: var(--text-strong);
	}

	.app-shell__brand:hover {
		text-decoration: none;
	}

	.app-shell__logo {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		background: var(--text-strong);
		color: var(--surface);
		border-radius: 6px;
		font-weight: 700;
		font-size: 0.85rem;
	}

	.app-shell__title {
		display: flex;
		flex-direction: column;
		line-height: 1.1;
	}

	.app-shell__title strong {
		font-size: 1rem;
	}

	.app-shell__title small {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.app-shell__nav {
		display: flex;
		gap: 0.75rem;
		margin-left: auto;
		margin-right: 1rem;
	}

	.app-shell__link {
		padding: 0.4rem 0.75rem;
		border-radius: 6px;
		color: var(--text);
		font-size: 0.9rem;
	}

	.app-shell__link:hover {
		background: var(--surface-alt);
		text-decoration: none;
	}

	.app-shell__link.is-active {
		background: var(--accent);
		color: var(--accent-contrast);
	}

	.app-shell__main {
		flex: 1;
		width: 100%;
		max-width: 880px;
		margin: 0 auto;
		padding: 2rem 1.5rem;
	}

	.app-shell__footer {
		text-align: center;
		padding: 1rem;
		color: var(--text-muted);
		border-top: 1px solid var(--border);
	}

	@media (max-width: 640px) {
		.app-shell__header {
			flex-wrap: wrap;
		}

		.app-shell__nav {
			order: 3;
			margin-left: 0;
			margin-right: 0;
			width: 100%;
		}
	}
</style>