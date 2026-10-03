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
		width: var(--space-6);
		height: var(--space-6);
		background: var(--color-ink-strong);
		color: var(--color-surface);
		border-radius: var(--radius-control);
		font-weight: 700;
		font-size: var(--text-sm);
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
		/* The nav is the one part of the shell whose width is CONTENT-driven:
		   it grows with the number of links (3 logged out, 6 for a recruiter)
		   and with the label length of the active locale. Below 640px it is
		   given `width: 100%` on its own row, and 6 links do not fit a 327px
		   row -- they overflowed the page sideways. Letting the links wrap
		   inside the nav is what keeps that row from becoming a scrollbar.
		   The links keep their own padding and gap; only their line breaking
		   changes. */
		flex-wrap: wrap;
		gap: var(--space-3);
		margin-left: auto;
		margin-right: var(--space-4);
	}

	/* A nav link is a destination, not a control the person operates, so it
	   stays flat. The accent fill on .is-active is the state, not the material. */
	.app-shell__link {
		padding: var(--space-2) 0.75rem;
		border-radius: var(--radius-control);
		color: var(--color-ink);
		font-size: var(--text-sm);
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
		padding: var(--space-2) 0.75rem;
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-size: var(--text-sm);
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

	/* -------------------------------------------------------------------------
	   Header wrap threshold.

	   880px stays a LITERAL on purpose: var() in a media condition silently
	   drops the whole block. See the note on --breakpoint-sm in app.css.

	   This was 640px, which was measured to be the WORST possible place for it.
	   The header is a single `nowrap` flex row above the threshold, so the layout
	   gets worse the instant it stops wrapping -- and then stays broken.

	   MEASURED (Chromium, 900px tall viewport, recruiter session = 6 nav links,
	   the widest nav the app can produce; overflow = documentElement.scrollWidth
	   - clientWidth, i.e. real sideways page scroll):

	     viewport   375    640    700    768    800    819    820    860    880
	     EN (px)     0     194    135     66     35     15      0      0      0
	     ES (px)     0     230    171    102     71     51     51      0      0

	   Two separate defects, and 640px sat exactly on the seam between them:

	   1. The one-row header needs 820px in English and 860px in Spanish
	   ("Auditoría gratis" / "Mi perfil" are wider than their English
	   counterparts). Above 640px nothing wrapped, so from 641px to 859px the
	   page scrolled sideways -- up to 230px of it. The nav labels did not stay
	   on one line either: they wrapped inside the nav, taking the header from
	   67px to 89px tall.

	   2. Below 640px the nav was given `width: 100%` on its own row, but 6
	   links need 444px and the row is only 327px at a 375px viewport, so it
	   overflowed again. `flex-wrap: wrap` on .app-shell__nav fixes that half.

	   880px, not 820px or 860px: the requirement above is CONTENT-dependent, so
	   pinning the threshold to the exact measured pixel would regress the moment
	   a nav item is added or 	   a locale ships with longer labels -- and the whole
	   scale is rem-based, so it also moves with the reader's browser font
	   size. 880px is --layout-content-max: below the measure, the viewport is
	   narrower than the content column and the header stacks; above it there is
	   guaranteed room. It clears the measured worst case (860px ES) with margin.

	   640px is NOT removed. It stays the breakpoint for the two-column grids
	   that collapse to one column; only the shell's header needed the wider one.
	   -------------------------------------------------------------------------- */
	@media (max-width: 880px) {
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
