<script lang="ts">
	/**
	 * Marca de eptus: la "e" geométrica (anillo + barra, con la boca abierta
	 * abajo a la derecha).
	 *
	 * El SVG va inline y con `currentColor` para heredar el color del texto:
	 * así la misma marca funciona en el tema claro y en el oscuro sin dos
	 * versiones que mantener. Es decorativa — el nombre de la marca va en el
	 * texto que la acompaña — así que se oculta a los lectores de pantalla.
	 */
	export let size = 24;
</script>

<svg
	class="logo"
	width={size}
	height={size}
	viewBox="0 0 32 32"
	fill="none"
	stroke="currentColor"
	stroke-width="4.5"
	stroke-linecap="round"
	aria-hidden="true"
	focusable="false"
>
	<path d="M25.5 16 A9.5 9.5 0 1 0 22.72 22.72" />
	<path d="M6.5 16 H25.5" />
</svg>

<style>
	.logo {
		display: block;
		flex: none;
	}
</style>
