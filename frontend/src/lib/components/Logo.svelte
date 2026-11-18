<script lang="ts">
	/**
	 * Marca de eptus: "la pieza que encaja".
	 *
	 * Un marco (cuadrado con una esquina abierta en cuarto de circulo) y la
	 * pieza —un circulo mas chico que el hueco— todavia por colocar. Es la
	 * metafora del producto: tu perfil por encajar en la vacante.
	 *
	 * Dos tonos a proposito: el marco usa `currentColor` (la tinta del tema) y
	 * la pieza el color de marca. La marca es decorativa —el nombre va en el
	 * texto que la acompaña— asi que se oculta a los lectores de pantalla.
	 */
	export let size = 26;
</script>

<svg
	class="logo"
	width={size}
	height={size}
	viewBox="0 0 32 32"
	fill="none"
	stroke="currentColor"
	stroke-width="3.6"
	aria-hidden="true"
	focusable="false"
>
	<!-- Marco con la esquina superior derecha abierta (cuarto de circulo concavo). -->
	<path d="M21.5 3.5 H3.5 V28.5 H28.5 V10.5 A7 7 0 0 0 21.5 3.5 Z" />
	<!-- La pieza: todavia sin encajar. -->
	<circle cx="21.5" cy="10.5" r="5.2" fill="var(--color-action)" stroke="none" />
</svg>

<style>
	.logo {
		display: block;
		flex: none;
	}
</style>
