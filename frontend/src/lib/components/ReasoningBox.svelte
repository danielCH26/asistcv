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
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 1rem 1.25rem;
	}

	.reasoning__heading {
		margin: 0 0 0.5rem;
		font-size: 0.95rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.reasoning__body {
		margin: 0;
		line-height: 1.6;
		color: var(--text);
		white-space: pre-wrap;
	}
</style>