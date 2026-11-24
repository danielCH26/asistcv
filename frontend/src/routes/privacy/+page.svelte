<script lang="ts">
	import { locale } from 'svelte-i18n';
	import LegalPage from '$components/LegalPage.svelte';
	import { getLegalDoc } from '$i18n/legal';

	// Documento reactivo al idioma activo; sin sesión ni locale resuelto
	// (ej. render directo en tests) cae a español por el helper.
	$: doc = getLegalDoc('privacy', $locale);
</script>

<svelte:head>
	<title>eptus · {doc.title}</title>
</svelte:head>

<LegalPage {doc} />
