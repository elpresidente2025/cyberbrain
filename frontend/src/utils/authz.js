export const normalizeRole = (role) => String(role ?? '').trim().toLowerCase();

export const isAdminRole = (role) => normalizeRole(role) === 'admin';

export const isTesterRole = (role) => normalizeRole(role) === 'tester';

export const hasLegacyTesterFlag = (user) => user?.isTester === true;

const parseMonthlyLimit = (value) => {
  const normalized = Number.parseInt(value, 10);
  return Number.isFinite(normalized) && normalized > 0 ? normalized : null;
};

export const getPlanName = (user) => {
  if (!user || typeof user !== 'object') return null;
  const plan = typeof user.plan === 'string' ? user.plan.trim() : '';
  return plan || null;
};

export const getSubscriptionStatus = (user) => {
  const status = typeof user?.subscriptionStatus === 'string'
    ? user.subscriptionStatus.trim().toLowerCase()
    : '';
  return status || null;
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
  if (monthlyLimit && monthlyLimit > 8) return true;

  return Boolean(getPlanName(user));
};

export const getMonthlyLimit = (user, fallbackLimit = 8) => {
  if (hasAdminOrTesterAccess(user)) {
    return 90;
  }

  const monthlyLimit = parseMonthlyLimit(user?.monthlyLimit);
  if (monthlyLimit) {
    return monthlyLimit;
  }

  if (isPaidSubscriber(user)) {
    return 90;
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
