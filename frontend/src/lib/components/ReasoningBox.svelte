<script lang="ts">
	import { _ } from 'svelte-i18n';

	export let text: string;
</script>

<section class="reasoning">
	<h3 class="reasoning__heading">{$_('result.reasoning')}</h3>
	<p class="reasoning__body">{text}</p>
</section>

<style>
	/* El razonamiento es la parte que se LEE, no la que se mira: sin tarjeta
	   propia, con una regla a la izquierda que lo separa del resto. */
	.reasoning {
		padding: var(--space-4) 0 var(--space-4) var(--space-5);
		border-left: var(--border-width-thick) solid var(--color-line-strong);
	}

	.reasoning__heading {
		margin: 0 0 var(--space-2);
		font-family: var(--font-mono);
		font-size: var(--text-2xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-ink-muted);
	}

	.reasoning__body {
		margin: 0;
		line-height: var(--leading-relaxed);
		color: var(--color-ink);
		white-space: pre-wrap;
	}
</style>
