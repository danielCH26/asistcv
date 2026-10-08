<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { apiClient } from '$api/client';
	import { ApiError, type Plan, type SubscriptionInfo } from '$api/types';
	import { requireSession } from '$stores/session';

	let ready = false;
	let plans: Plan[] = [];
	let subscription: SubscriptionInfo | null = null;
	let loadError = '';

	let selectedPlan: string | null = null;
	let paymentMethod: 'card' | 'pse' = 'card';
	let checkoutBusy = false;
	let checkoutError = '';

	let portalBusy = false;
	let portalError = '';
	let plansSection: HTMLElement | null = null;

	function scrollToPlans() {
		plansSection?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function priceLabel(plan: Plan): string {
		if (plan.price_cents === 0) return $_('billing.free');
		const value = (plan.price_cents / 100).toFixed(0);
		return `${plan.currency.toUpperCase()} ${value} / ${plan.interval}`;
	}

	function usageLabel(): string {
		if (!subscription) return '';
		const matches = subscription.usage['matches_this_month'];
		const limit = subscription.limits['matches_per_month'];
		if (typeof matches !== 'number') return '';
		if (typeof limit !== 'number' || limit <= 0) {
			return $_('billing.usageUnlimited', { values: { used: matches } });
		}
		return $_('billing.usage', { values: { used: matches, limit } });
	}

	onMount(async () => {
		if (!(await requireSession())) return;
		ready = true;
		try {
			plans = await apiClient.plans();
		} catch {
			loadError = $_('billing.loadError');
		}
		try {
			subscription = await apiClient.subscription();
		} catch {
			subscription = null;
		}
	});

	async function startCheckout(planId: string) {
		selectedPlan = planId;
		checkoutBusy = true;
		checkoutError = '';
		try {
			const data = await apiClient.checkout(planId, paymentMethod);
			window.location.href = data.checkout_url;
		} catch (err) {
			checkoutError =
				err instanceof ApiError && err.status === 403
					? $_('billing.emailRequired')
					: $_('billing.checkoutError');
		} finally {
			checkoutBusy = false;
		}
	}

	async function openPortal() {
		portalBusy = true;
		portalError = '';
		try {
			const data = await apiClient.portal();
			window.location.href = data.portal_url;
		} catch (err) {
			portalError = err instanceof ApiError && err.status === 400 ? $_('billing.noCustomer') : $_('billing.portalError');
		} finally {
			portalBusy = false;
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('billing.title')}</title>
</svelte:head>

{#if ready}
	<section class="billing">
		<h1>{$_('billing.heading')}</h1>

		{#if loadError}<p class="billing__error" role="alert">{loadError}</p>{/if}

		{#if subscription}
			<section class="billing__current">
				<h2>{$_('billing.currentHeading')}</h2>
				<p>
					{$_('billing.plan')}: <strong>{subscription.plan_id}</strong>
					· {$_('billing.status')}: <strong>{subscription.status}</strong>
				</p>
				{#if usageLabel()}<p class="billing__usage">{usageLabel()}</p>{/if}
				{#if subscription.overage > 0}
					<p class="billing__usage">{$_('billing.overage', { values: { overage: subscription.overage } })}</p>
				{/if}
				{#if subscription.has_portal_access}
					<button type="button" disabled={portalBusy} on:click={openPortal}>
						{$_('billing.manageCta')}
					</button>
					{#if portalError}<p class="billing__error">{portalError}</p>{/if}
				{:else}
					<p class="billing__no-portal">{$_('billing.noPortal')}</p>
					<button type="button" class="billing__choose-cta" on:click={scrollToPlans}>
						{$_('billing.chooseCta')}
					</button>
				{/if}
			</section>
		{/if}

		<section class="billing__plans" bind:this={plansSection}>
			<h2>{$_('billing.plansHeading')}</h2>
			<div class="billing__method">
				<span>{$_('billing.paymentMethod')}:</span>
				<label>
					<input type="radio" bind:group={paymentMethod} value="card" />
					{$_('billing.card')}
				</label>
				<label>
					<input type="radio" bind:group={paymentMethod} value="pse" />
					{$_('billing.pse')}
				</label>
			</div>

			<div class="billing__grid">
				{#each plans as plan (plan.plan_id)}
					{#if plan.price_cents > 0}
						<article class="plan-card">
							<h3>{plan.name}</h3>
							<p class="plan-card__price">{priceLabel(plan)}</p>
							<ul>
								{#each plan.features as feature}
									<li>{feature}</li>
								{/each}
							</ul>
							<button
								type="button"
								disabled={checkoutBusy}
								on:click={() => startCheckout(plan.plan_id)}
							>
								{checkoutBusy && selectedPlan === plan.plan_id ? $_('billing.redirecting') : $_('billing.subscribeCta')}
							</button>
						</article>
					{/if}
				{/each}
			</div>
			{#if checkoutError}<p class="billing__error" role="alert">{checkoutError}</p>{/if}
		</section>
	</section>
{/if}

<style>
	.billing {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.billing h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.billing h2 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-lg);
		color: var(--color-ink-strong);
	}

	.billing__current,
	.billing__plans {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.billing__current p {
		margin: 0;
	}

	.billing__usage {
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.billing__current button {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		cursor: pointer;
		font-weight: 600;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.billing__current button:hover {
		box-shadow: var(--clay-lifted);
	}

	.billing__current button:focus-visible {
		outline: none;
		box-shadow: var(--clay-raised), var(--clay-focus-ring);
	}

	.billing__current button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.billing__no-portal {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.billing__choose-cta {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.billing__choose-cta:hover {
		box-shadow: var(--clay-lifted);
	}

	.billing__choose-cta:focus-visible {
		outline: none;
		box-shadow: var(--clay-raised), var(--clay-focus-ring);
	}

	.billing__error {
		margin: 0;
		color: var(--error);
		font-size: var(--text-sm);
	}

	.billing__method {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.billing__method label {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		cursor: pointer;
	}

	.billing__grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: var(--space-4);
	}

	.plan-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
		box-shadow: var(--clay-raised);
	}

	.plan-card h3 {
		margin: 0;
		font-size: var(--text-md);
		color: var(--color-ink-strong);
	}

	.plan-card__price {
		margin: 0;
		font-weight: 700;
		color: var(--color-action);
	}

	.plan-card ul {
		margin: 0;
		padding-left: var(--space-4);
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.plan-card button {
		margin-top: auto;
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.plan-card button:hover {
		box-shadow: var(--clay-lifted);
	}

	.plan-card button:focus-visible {
		outline: none;
		box-shadow: var(--clay-raised), var(--clay-focus-ring);
	}

	.plan-card button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		box-shadow: none;
	}
</style>
