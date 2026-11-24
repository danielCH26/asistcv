<script lang="ts">
	import type { LegalDoc } from '$i18n/legal';

	/**
	 * Renderizador de documentos legales (Términos, Privacidad, Cookies).
	 *
	 * El contenido vive en `$i18n/legal` por idioma; este componente solo
	 * sabe pintar la estructura: título + versión, intro, secciones numeradas
	 * con párrafos, viñetas y bloques con subtítulo. Se usa sobre la
	 * superficie de marketing (fondo claro), igual que la portada.
	 */
	export let doc: LegalDoc;
</script>

<article class="legal">
	<header class="legal__header">
		<h1>{doc.title}</h1>
		<p class="legal__meta">{doc.meta}</p>
	</header>

	{#each doc.intro as paragraph}
		<p class="legal__intro">{paragraph}</p>
	{/each}

	{#each doc.sections as section, index}
		<section class="legal__section" id={section.id}>
			<h2>
				<span class="legal__num" aria-hidden="true">{index + 1}.</span>
				{section.title}
			</h2>

			{#each section.paragraphs ?? [] as paragraph}
				<p>{paragraph}</p>
			{/each}

			{#if section.bullets}
				<ul>
					{#each section.bullets as bullet}
						<li>{bullet}</li>
					{/each}
				</ul>
			{/if}

			{#each section.blocks ?? [] as block}
				<h3>{block.title}</h3>
				{#each block.paragraphs ?? [] as paragraph}
					<p>{paragraph}</p>
				{/each}
				{#if block.bullets}
					<ul>
						{#each block.bullets as bullet}
							<li>{bullet}</li>
						{/each}
					</ul>
				{/if}
			{/each}
		</section>
	{/each}
</article>

<style>
	/* El ancho de lectura es CONTENT-driven y acotado: un documento legal
	   a 100% del layout de marketing es ilegible. 46rem ≈ 70 caracteres
	   por línea en --text-md. */
	.legal {
		display: block;
		max-width: 46rem;
		margin: 0 auto;
		padding: var(--space-7) 0 var(--space-8);
		color: var(--color-ink);
	}

	.legal__header {
		padding-bottom: var(--space-5);
		border-bottom: var(--border-width) solid var(--color-line);
	}

	.legal h1 {
		margin: 0 0 var(--space-3);
		font-size: var(--text-3xl);
		letter-spacing: var(--tracking-tight);
		color: var(--color-ink-strong);
	}

	.legal__meta {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.legal__intro {
		margin: var(--space-5) 0 0;
		font-size: var(--text-lg);
		line-height: 1.6;
		color: var(--color-ink);
	}

	.legal__section {
		margin-top: var(--space-7);
	}

	.legal__section h2 {
		display: flex;
		gap: var(--space-2);
		align-items: baseline;
		margin: 0 0 var(--space-4);
		font-size: var(--text-xl);
		letter-spacing: var(--tracking-tight);
		color: var(--color-ink-strong);
	}

	.legal__num {
		color: var(--color-ink-muted);
		font-variant-numeric: tabular-nums;
	}

	.legal__section h3 {
		margin: var(--space-5) 0 var(--space-2);
		font-size: var(--text-md);
		color: var(--color-ink-strong);
	}

	.legal p {
		margin: 0 0 var(--space-3);
		font-size: var(--text-md);
		line-height: 1.65;
	}

	.legal ul {
		margin: 0 0 var(--space-3);
		padding-left: var(--space-5);
	}

	.legal li {
		margin: 0 0 var(--space-2);
		font-size: var(--text-md);
		line-height: 1.65;
	}

	.legal li::marker {
		color: var(--color-ink-muted);
	}

	@media (max-width: 640px) {
		.legal {
			padding-top: var(--space-5);
		}

		.legal h1 {
			font-size: var(--text-2xl);
		}
	}
</style>
