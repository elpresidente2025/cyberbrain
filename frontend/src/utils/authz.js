import {
  DEFAULT_PAID_MONTHLY_LIMIT,
  TRIAL_MONTHLY_LIMIT,
  getBillingStatus as getNormalizedBillingStatus,
  getUserPlanId as getCatalogPlanId,
  resolvePaidPlanFromUser,
} from '../config/planCatalog';

export const normalizeRole = (role) => String(role ?? '').trim().toLowerCase();

export const isAdminRole = (role) => normalizeRole(role) === 'admin';

export const isTesterRole = (role) => normalizeRole(role) === 'tester';

export const hasLegacyTesterFlag = (user) => user?.isTester === true;

const parseMonthlyLimit = (value) => {
  const normalized = Number.parseInt(value, 10);
  return Number.isFinite(normalized) && normalized >= 0 ? normalized : null;
};

export const getPlanId = (user) => getCatalogPlanId(user);

export const getPlanName = (user) => {
  if (!user || typeof user !== 'object') return null;
  const resolvedPlan = resolvePaidPlanFromUser(user);
  if (resolvedPlan) {
    return resolvedPlan.name;
  }
  const plan = typeof user.plan === 'string' ? user.plan.trim() : '';
  return plan || null;
};

export const getSubscriptionStatus = (user) => {
  return getNormalizedBillingStatus(user);
};

export const hasAdminAccess = (user) => {
  if (!user) return false;
  return isAdminRole(user.role);
};

export const isTesterUser = (user) => {
  if (!user) return false;
  return isTesterRole(user.role) || hasLegacyTesterFlag(user);
};

export const hasAdminOrTesterAccess = (user) => {
  return hasAdminAccess(user) || isTesterUser(user);
};

export const isPaidSubscriber = (user) => {
  if (!user || typeof user !== 'object') return false;
  if (getSubscriptionStatus(user) === 'active') return true;

  const monthlyLimit = parseMonthlyLimit(user.monthlyLimit);
  if (monthlyLimit !== null && monthlyLimit > TRIAL_MONTHLY_LIMIT) return true;

  return Boolean(resolvePaidPlanFromUser(user) || getPlanName(user));
};

export const getMonthlyLimit = (user, fallbackLimit = TRIAL_MONTHLY_LIMIT) => {
  if (hasAdminOrTesterAccess(user)) {
    return DEFAULT_PAID_MONTHLY_LIMIT;
  }

  const monthlyLimit = parseMonthlyLimit(user?.monthlyLimit);
  if (monthlyLimit !== null) {
    return monthlyLimit;
  }

  const billingMonthlyLimit = parseMonthlyLimit(user?.billing?.monthlyLimit);
  if (billingMonthlyLimit !== null) {
    return billingMonthlyLimit;
  }

  const paidPlan = resolvePaidPlanFromUser(user);
  if (paidPlan?.monthlyLimit) {
    return paidPlan.monthlyLimit;
  }

  if (isPaidSubscriber(user)) {
    return DEFAULT_PAID_MONTHLY_LIMIT;
  }

  return fallbackLimit;
};

export const normalizeAuthUser = (user) => {
  if (!user || typeof user !== 'object') {
    return user;
  }

  const normalizedRole = normalizeRole(user.role);
  const legacyTester = hasLegacyTesterFlag(user);

  let role = normalizedRole || null;
  if (!role) {
    if (legacyTester) {
      role = 'tester';
    }
  }

  return {
    ...user,
    role,
    isAdmin: isAdminRole(role),
    isTester: isTesterRole(normalizedRole) || legacyTester
  };
};
