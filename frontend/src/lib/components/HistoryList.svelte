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
			</tr>
		{/each}
	</tbody>
</table>

<style>
	.history-list {
		width: 100%;
		/* `separate` + zero spacing, NOT `collapse`.
		   A `<table>` is not a block container, so `overflow: hidden` does not
		   give it a clipping context: under `border-collapse: collapse` the
		   radius and the overflow are both ignored for the CELLS, and the
		   `th` background paints a square corner straight over the rounded
		   one. Verified in Chromium at a 40px radius -- the collapse version
		   renders a hard 90-degree corner, the separate version renders the
		   curve. `separate` makes the table a real box that `overflow: hidden`
		   can clip; `border-spacing: 0` keeps the rows visually flush, so
		   this costs no spacing token.
		   Keep the radius in sync with the collapse mode: reverting to
		   `collapse` silently brings the square corner back. */
		border-collapse: separate;
		border-spacing: 0;
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card-lg);
		overflow: hidden;
	}

	.history-list th {
		text-align: left;
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: var(--tracking-wide);
		color: var(--color-ink-muted);
		padding: var(--space-2) var(--space-4);
		background: var(--color-surface-alt);
		border-bottom: 1px solid var(--color-line);
	}

	.history-list td {
		padding: var(--space-3) var(--space-4);
		border-bottom: 1px solid var(--color-line);
		font-size: var(--text-sm);
	}

	.history-list tr:last-child td {
		border-bottom: none;
	}

	.history-list__cell--id {
		font-variant-numeric: tabular-nums;
		color: var(--color-ink-muted);
		width: 4ch;
	}

	.history-list__score {
		display: inline-block;
		min-width: var(--space-7);
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-pill);
		color: var(--color-on-score-fill);
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
</style>