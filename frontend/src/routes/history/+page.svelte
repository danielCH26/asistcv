<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import HistoryList from '$components/HistoryList.svelte';
	import { historyStore } from '$stores/history';
	import { profileStore } from '$stores/profile';
	import { get } from 'svelte/store';

	let pageIndex = 0;
	const pageSize = 20;

	async function refresh() {
		const profileId = get(profileStore);
		await historyStore.load({ limit: pageSize, offset: pageIndex * pageSize, profileId });
	}

	function retry() {
		historyStore.reset();
		void refresh();
	}

	function nextPage() {
		pageIndex += 1;
		void refresh();
	}

	function prevPage() {
		if (pageIndex > 0) {
			pageIndex -= 1;
			void refresh();
		}
	}

	function viewDetail(id: number) {
		void goto(`/history/${id}`);
	}

	onMount(refresh);
</script>

<svelte:head>
	<title>AsistCV · {$_('history.heading')}</title>
</svelte:head>

<section class="history">
	<header class="history__intro">
		<h1>{$_('history.heading')}</h1>
		<p>{$_('history.intro')}</p>
	</header>

	{#if $historyStore.status === 'loading' && $historyStore.items.length === 0}
		<p>{$_('history.loading')}</p>
	{/if}

	{#if $historyStore.status === 'error'}
		<div class="history__error" role="alert">
			<p>{$historyStore.error ?? $_('history.errorLoad')}</p>
			<button type="button" on:click={retry}>{$_('history.retry')}</button>
		</div>
	{/if}

	{#if $historyStore.status === 'done' && $historyStore.items.length === 0}
		<p class="history__empty">{$_('history.empty')}</p>
	{/if}

	{#if $historyStore.items.length > 0}
		<HistoryList items={$historyStore.items} onSelect={viewDetail} />

		<nav class="history__pagination">
			<button type="button" on:click={prevPage} disabled={pageIndex === 0}>
				{$_('history.prev')}
			</button>
			<span class="history__page-label">
				{$_('history.page', { values: { page: pageIndex + 1 } })}
			</span>
			<button
				type="button"
				on:click={nextPage}
				disabled={$historyStore.items.length < pageSize}
			>
				{$_('history.next')}
			</button>
		</nav>
	{/if}
</section>

<style>
	.history {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.history__intro h1 {
		margin: 0 0 0.4rem;
		color: var(--text-strong);
	}

	.history__intro p {
		margin: 0;
		color: var(--text-muted);
	}

	.history__empty {
		text-align: center;
		padding: 2rem;
		background: var(--surface);
		border: 1px dashed var(--border);
		border-radius: 10px;
		color: var(--text-muted);
	}

	.history__error {
		padding: 1rem 1.25rem;
		background: var(--error-bg);
		color: var(--error);
		border: 1px solid var(--error);
		border-radius: 8px;
	}

	.history__pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
	}

	.history__pagination button {
		padding: 0.4rem 0.9rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
		cursor: pointer;
	}

	.history__pagination button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.history__page-label {
		font-size: 0.85rem;
		color: var(--text-muted);
	}
</style>