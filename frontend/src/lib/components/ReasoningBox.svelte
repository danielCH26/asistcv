<script lang="ts">
	import { _ } from 'svelte-i18n';

	export let text: string;
</script>

<section class="reasoning">
	<h3 class="reasoning__heading">{$_('result.reasoning')}</h3>
	<p class="reasoning__body">{text}</p>
</section>

<style>
	.reasoning {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card-lg);
		padding: var(--space-4) var(--space-5);
		box-shadow: var(--clay-raised);
	}

	.reasoning__heading {
		margin: 0 0 var(--space-2);
		font-size: var(--text-sm);
		text-transform: uppercase;
		letter-spacing: var(--tracking-wide);
		color: var(--color-ink-muted);
	}

	.reasoning__body {
		margin: 0;
		line-height: var(--leading-relaxed);
		color: var(--color-ink);
		white-space: pre-wrap;
	}
</style>