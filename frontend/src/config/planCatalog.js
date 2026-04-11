import catalog from '../../../shared/plan-catalog.json';

const normalizeString = (value) => String(value ?? '').trim().toLowerCase();

const parsePositiveInt = (value) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

export const PLAN_CATALOG = Object.freeze(catalog);
export const PAID_PLANS = Object.freeze(Array.isArray(catalog.paidPlans) ? catalog.paidPlans : []);
export const DEFAULT_PAID_PLAN = Object.freeze(
  PAID_PLANS.find((plan) => plan.id === catalog.activePlanId) ||
  PAID_PLANS[0] ||
  null
);
export const TRIAL_PLAN = Object.freeze(catalog.trial || { id: 'trial', name: '무료 체험', monthlyLimit: 8 });
export const TRIAL_MONTHLY_LIMIT = parsePositiveInt(TRIAL_PLAN.monthlyLimit) || 8;
export const DEFAULT_PAID_MONTHLY_LIMIT = parsePositiveInt(DEFAULT_PAID_PLAN?.monthlyLimit) || 90;

const getPlanSearchKeys = (plan) => [
  plan?.id,
  plan?.name,
  ...(Array.isArray(plan?.legacyNames) ? plan.legacyNames : []),
]
  .map(normalizeString)
  .filter(Boolean);

export const getPlanById = (planId) => {
  const normalizedPlanId = normalizeString(planId);
  if (!normalizedPlanId) return null;
  return PAID_PLANS.find((plan) => normalizeString(plan.id) === normalizedPlanId) || null;
};

export const resolvePaidPlan = (value) => {
  if (!value) return null;

  if (typeof value === 'object') {
    return (
      resolvePaidPlan(value.planId) ||
      resolvePaidPlan(value.id) ||
      resolvePaidPlan(value.plan) ||
      resolvePaidPlan(value.name) ||
      resolvePaidPlan(value.billing?.planId) ||
      resolvePaidPlan(value.billing?.planName) ||
      null
    );
  }

  const normalizedValue = normalizeString(value);
  if (!normalizedValue) return null;

  return PAID_PLANS.find((plan) => getPlanSearchKeys(plan).includes(normalizedValue)) || null;
};

export const getBillingStatus = (user) => {
  const status = normalizeString(user?.billing?.status || user?.subscriptionStatus);
  return status || 'trial';
};

export const getUserPlanId = (user) => {
  const explicitPlanId = normalizeString(user?.planId || user?.billing?.planId);
  if (explicitPlanId) {
    return explicitPlanId;
  }

  return resolvePaidPlan(user?.plan || user?.subscription || user?.billing?.planName)?.id || null;
};

export const resolvePaidPlanFromUser = (user) => resolvePaidPlan(
  getUserPlanId(user) ||
  user?.plan ||
  user?.subscription ||
  user?.billing?.planName
);
