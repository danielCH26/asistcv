<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { EnergyLevel } from '$api/types';

	export let level: EnergyLevel;

	$: labelKey =
		level === 'low' ? 'result.energyLow' : level === 'high' ? 'result.energyHigh' : 'result.energyMedium';
</script>

<span class="energy energy--{level}">
	<span class="energy__dot" aria-hidden="true"></span>
	<span class="energy__label">{$_(labelKey)}</span>
</span>

<style>
	.energy {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-1) var(--space-3);
		border-radius: 999px;
		font-size: var(--text-sm);
		font-weight: 600;
	}

	.energy__dot {
		width: var(--space-2);
		height: var(--space-2);
		border-radius: 50%;
		background: currentColor;
	}

	.energy--low {
		background: var(--color-danger-muted);
		color: var(--score-low-ink);
	}

	.energy--medium {
		background: var(--color-warning-muted);
		color: var(--score-mid-ink);
	}

	.energy--high {
		background: var(--color-success-muted);
		color: var(--score-high-ink);
	}
</style>