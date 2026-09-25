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
		gap: 1.75rem;
	}

	.billing h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.billing h2 {
		margin: 0 0 0.5rem;
		font-size: 1.15rem;
		color: var(--text-strong);
	}

	.billing__current,
	.billing__plans {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.billing__current p {
		margin: 0;
	}

	.billing__usage {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.billing__current button {
		align-self: flex-start;
		padding: 0.5rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: transparent;
		color: var(--text);
		cursor: pointer;
		font-weight: 600;
	}

	.billing__current button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.billing__no-portal {
		margin: 0;
		font-size: 0.9rem;
		color: var(--text-muted);
	}

	.billing__choose-cta {
		align-self: flex-start;
		padding: 0.5rem 1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.billing__error {
		margin: 0;
		color: var(--error);
		font-size: 0.9rem;
	}

	.billing__method {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.billing__method label {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		cursor: pointer;
	}

	.billing__grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 1rem;
	}

	.plan-card {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 1.1rem;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--surface);
	}

	.plan-card h3 {
		margin: 0;
		font-size: 1.05rem;
		color: var(--text-strong);
	}

	.plan-card__price {
		margin: 0;
		font-weight: 700;
		color: var(--accent);
	}

	.plan-card ul {
		margin: 0;
		padding-left: 1.1rem;
		color: var(--text-muted);
		font-size: 0.85rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.plan-card button {
		margin-top: auto;
		padding: 0.5rem 1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.plan-card button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
