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
		gap: 0.5rem;
		padding: 0.35rem 0.75rem;
		border-radius: 999px;
		font-size: 0.85rem;
		font-weight: 600;
	}

	.energy__dot {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: currentColor;
	}

	.energy--low {
		background: rgba(239, 68, 68, 0.12);
		color: var(--score-low);
	}

	.energy--medium {
		background: rgba(234, 179, 8, 0.15);
		color: var(--score-mid);
	}

	.energy--high {
		background: rgba(16, 185, 129, 0.15);
		color: var(--score-high);
	}
</style>