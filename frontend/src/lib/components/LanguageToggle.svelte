<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { toggleLocale } from '$i18n/index';
</script>

<button type="button" class="lang-toggle" on:click={toggleLocale} aria-label={$_('language.toggle')}>
	<span class="lang-toggle__es">{$_('language.es')}</span>
	<span class="lang-toggle__divider">/</span>
	<span class="lang-toggle__en">{$_('language.en')}</span>
</button>

<style>
	.lang-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
		font-size: 0.85rem;
		cursor: pointer;
	}

	.lang-toggle__divider {
		color: var(--text-muted);
	}
</style>