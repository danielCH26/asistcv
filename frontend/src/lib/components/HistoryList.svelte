<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { AnalysisSummary } from '$api/types';

	export let items: AnalysisSummary[] = [];
	export let onSelect: ((id: number) => void) | undefined = undefined;

	function formatDate(value: string): string {
		try {
			const date = new Date(value);
			if (Number.isNaN(date.getTime())) return value;
			return new Intl.DateTimeFormat(undefined, {
				dateStyle: 'medium',
				timeStyle: 'short'
			}).format(date);
		} catch {
			return value;
		}
	}
</script>

<table class="history-list">
	<thead>
		<tr>
			<th class="history-list__col history-list__col--id">#</th>
			<th class="history-list__col history-list__col--score">{$_('history.scoreShort', { values: { score: '' } })}</th>
			<th class="history-list__col">{$_('history.heading')}</th>
			<th class="history-list__col history-list__col--action"></th>
		</tr>
	</thead>
	<tbody>
		{#each items as item (item.id)}
			<tr>
				<td class="history-list__cell history-list__cell--id">{item.id}</td>
				<td class="history-list__cell history-list__cell--score">
					{#if item.score !== null && item.score !== undefined}
						<span class="history-list__score" data-bucket={item.score < 50 ? 'low' : item.score < 75 ? 'mid' : 'high'}>
							{item.score}
						</span>
					{:else}
						—
					{/if}
				</td>
				<td class="history-list__cell history-list__cell--date">{formatDate(item.created_at)}</td>
				<td class="history-list__cell history-list__cell--action">
					{#if onSelect}
						<button type="button" class="history-list__action" on:click={() => onSelect?.(item.id)}>
							{$_('history.view')}
						</button>
					{/if}
				</td>
			</tr>
		{/each}
	</tbody>
</table>

<style>
	.history-list {
		width: 100%;
		border-collapse: collapse;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 10px;
		overflow: hidden;
	}

	.history-list th {
		text-align: left;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		padding: 0.6rem 1rem;
		background: var(--surface-alt);
		border-bottom: 1px solid var(--border);
	}

	.history-list td {
		padding: 0.7rem 1rem;
		border-bottom: 1px solid var(--border);
		font-size: 0.9rem;
	}

	.history-list tr:last-child td {
		border-bottom: none;
	}

	.history-list__cell--id {
		font-variant-numeric: tabular-nums;
		color: var(--text-muted);
		width: 4ch;
	}

	.history-list__score {
		display: inline-block;
		min-width: 2.5rem;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		color: #fff;
		font-weight: 600;
		text-align: center;
		font-variant-numeric: tabular-nums;
	}

	.history-list__score[data-bucket='low'] {
		background: var(--score-low);
	}

	.history-list__score[data-bucket='mid'] {
		background: var(--score-mid);
	}

	.history-list__score[data-bucket='high'] {
		background: var(--score-high);
	}

	.history-list__col--action,
	.history-list__cell--action {
		text-align: right;
		width: 8rem;
	}

	.history-list__action {
		background: transparent;
		border: 1px solid var(--accent);
		color: var(--accent);
		padding: 0.3rem 0.75rem;
		border-radius: 6px;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.history-list__action:hover {
		background: var(--accent);
		color: var(--accent-contrast);
	}
</style>