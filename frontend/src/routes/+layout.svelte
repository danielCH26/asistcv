<script lang="ts">
	import '../app.css';
	import { setupI18n } from '$i18n/index';
	import LanguageToggle from '$components/LanguageToggle.svelte';
	import { page } from '$app/stores';
	import { _ } from 'svelte-i18n';
	import { isAuthenticated, isRecruiter, logout, session, startSessionRefresh } from '$stores/session';

	setupI18n();
	startSessionRefresh();

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
			<a class="app-shell__link" class:is-active={pathname === '/audit'} href="/audit">{$_('app.nav.audit')}</a>
			<a
				class="app-shell__link"
				class:is-active={pathname.startsWith('/history')}
				href="/history">{$_('app.nav.history')}</a
			>
			{#if $isAuthenticated}
				<a
					class="app-shell__link"
					class:is-active={pathname === '/profile'}
					href="/profile">{$_('app.nav.profile')}</a
				>
				{#if $isRecruiter}
					<a
						class="app-shell__link"
						class:is-active={pathname === '/recruiter'}
						href="/recruiter">{$_('app.nav.recruiter')}</a
					>
				{/if}
				<a
					class="app-shell__link"
					class:is-active={pathname === '/billing'}
					href="/billing">{$_('app.nav.billing')}</a
				>
			{/if}
		</nav>

		<div class="app-shell__actions">
			<LanguageToggle />
			{#if $isAuthenticated}
				<button
					type="button"
					class="app-shell__session"
					title={$session?.user.email}
					on:click={() => logout()}>{$_('app.nav.logout')}</button
				>
			{:else}
				<a class="app-shell__link" href="/login">{$_('app.nav.login')}</a>
				<a class="app-shell__link app-shell__signup" href="/signup">{$_('app.nav.signup')}</a>
			{/if}
		</div>
	</header>

	<main class="app-shell__main">
		<slot />
	</main>

	<footer class="app-shell__footer">
		<small>AsistCV · Sprint 2</small>
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
		gap: var(--space-5);
		padding: var(--space-4) var(--space-5);
		background: var(--color-surface);
		border-bottom: var(--border-width) solid var(--color-line);
	}

	.app-shell__brand {
		display: inline-flex;
		align-items: center;
		gap: 0.65rem;
		color: var(--color-ink-strong);
	}

	.app-shell__brand:hover {
		text-decoration: none;
	}

	.app-shell__logo {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--space-6);
		height: var(--space-6);
		background: var(--color-ink-strong);
		color: var(--color-surface);
		border-radius: var(--radius-control);
		font-weight: 700;
		font-size: 0.85rem;
	}

	.app-shell__title {
		display: flex;
		flex-direction: column;
		line-height: var(--leading-tight);
	}

	.app-shell__title strong {
		font-size: var(--text-md);
	}

	.app-shell__title small {
		font-size: var(--text-xs);
		color: var(--color-ink-muted);
	}

	.app-shell__nav {
		display: flex;
		gap: var(--space-3);
		margin-left: auto;
		margin-right: var(--space-4);
	}

	/* A nav link is a destination, not a control the person operates, so it
	   stays flat. The accent fill on .is-active is the state, not the material. */
	.app-shell__link {
		padding: 0.4rem 0.75rem;
		border-radius: var(--radius-control);
		color: var(--color-ink);
		font-size: 0.9rem;
	}

	.app-shell__link:hover {
		background: var(--color-surface-alt);
		text-decoration: none;
	}

	.app-shell__link.is-active {
		background: var(--color-action);
		color: var(--color-on-action);
	}

	.app-shell__actions {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.app-shell__signup {
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
	}

	/* A real <button>: control, so clay. */
	.app-shell__session {
		padding: 0.4rem 0.75rem;
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-size: 0.9rem;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.app-shell__session:hover {
		box-shadow: var(--clay-lifted);
	}

	.app-shell__session:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.app-shell__main {
		flex: 1;
		width: 100%;
		max-width: var(--layout-content-max);
		margin: 0 auto;
		padding: var(--space-6) var(--space-5);
	}

	.app-shell__footer {
		text-align: center;
		padding: var(--space-4);
		color: var(--color-ink-muted);
		border-top: var(--border-width) solid var(--color-line);
	}

	/* 640px stays a LITERAL on purpose: var() in a media condition silently
	   drops the whole block. See the note on --breakpoint-sm in app.css. */
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
