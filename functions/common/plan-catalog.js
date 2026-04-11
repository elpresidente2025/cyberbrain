'use strict';

const catalog = require('../../shared/plan-catalog.json');

function normalizeString(value) {
  return String(value ?? '').trim().toLowerCase();
}

function parsePositiveInt(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseNonNegativeInt(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

const PLAN_CATALOG = Object.freeze(catalog);
const PAID_PLANS = Object.freeze(Array.isArray(catalog.paidPlans) ? catalog.paidPlans : []);
const DEFAULT_PAID_PLAN = Object.freeze(
  PAID_PLANS.find((plan) => plan.id === catalog.activePlanId) ||
  PAID_PLANS[0] ||
  null
);
const TRIAL_PLAN = Object.freeze(catalog.trial || { id: 'trial', name: '무료 체험', monthlyLimit: 8 });
const TRIAL_MONTHLY_LIMIT = parsePositiveInt(TRIAL_PLAN.monthlyLimit) || 8;
const DEFAULT_PAID_MONTHLY_LIMIT = parsePositiveInt(DEFAULT_PAID_PLAN?.monthlyLimit) || 90;

function getPlanSearchKeys(plan) {
  return [
    plan?.id,
    plan?.name,
    ...(Array.isArray(plan?.legacyNames) ? plan.legacyNames : []),
  ]
    .map(normalizeString)
    .filter(Boolean);
}

function getPlanById(planId) {
  const normalizedPlanId = normalizeString(planId);
  if (!normalizedPlanId) return null;
  return PAID_PLANS.find((plan) => normalizeString(plan.id) === normalizedPlanId) || null;
}

function resolvePaidPlan(value) {
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
}

function getDefaultPaidPlan() {
  return DEFAULT_PAID_PLAN;
}

function getTrialMonthlyLimit() {
  return TRIAL_MONTHLY_LIMIT;
}

function getDefaultPaidPlanMonthlyLimit() {
  return DEFAULT_PAID_MONTHLY_LIMIT;
}

function getUserBillingStatus(user) {
  const status = normalizeString(user?.billing?.status || user?.subscriptionStatus);
  return status || 'trial';
}

function getUserPlanId(user) {
  const explicitPlanId = normalizeString(user?.planId || user?.billing?.planId);
  if (explicitPlanId) {
    return explicitPlanId;
  }

  return resolvePaidPlan(user?.plan || user?.subscription || user?.billing?.planName)?.id || null;
}

function getUserPaidPlan(user) {
  return resolvePaidPlan(
    getUserPlanId(user) ||
    user?.plan ||
    user?.subscription ||
    user?.billing?.planName
  );
}

function getUserMonthlyLimit(user, fallbackLimit = TRIAL_MONTHLY_LIMIT) {
  const explicitMonthlyLimit = parseNonNegativeInt(user?.monthlyLimit);
  if (explicitMonthlyLimit !== null) {
    return explicitMonthlyLimit;
  }

  const billingMonthlyLimit = parseNonNegativeInt(user?.billing?.monthlyLimit);
  if (billingMonthlyLimit !== null) {
    return billingMonthlyLimit;
  }

  const paidPlan = getUserPaidPlan(user);
  if (paidPlan) {
    return parsePositiveInt(paidPlan.monthlyLimit) || DEFAULT_PAID_MONTHLY_LIMIT;
  }

  return fallbackLimit;
}

module.exports = {
  PLAN_CATALOG,
  PAID_PLANS,
  TRIAL_PLAN,
  DEFAULT_PAID_PLAN,
  DEFAULT_PAID_MONTHLY_LIMIT,
  TRIAL_MONTHLY_LIMIT,
  getPlanById,
  resolvePaidPlan,
  getDefaultPaidPlan,
  getTrialMonthlyLimit,
  getDefaultPaidPlanMonthlyLimit,
  getUserBillingStatus,
  getUserPlanId,
  getUserPaidPlan,
  getUserMonthlyLimit,
};
