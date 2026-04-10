export const normalizeRole = (role) => String(role ?? '').trim().toLowerCase();

export const isAdminRole = (role) => normalizeRole(role) === 'admin';

export const hasLegacyAdminFlag = (user) => user?.isAdmin === true;

export const hasAdminAccess = (user) => {
  if (!user) return false;
  return isAdminRole(user.role) || hasLegacyAdminFlag(user);
};

export const isTesterUser = (user) => user?.isTester === true;

export const hasAdminOrTesterAccess = (user) => {
  return hasAdminAccess(user) || isTesterUser(user);
};

export const normalizeAuthUser = (user) => {
  if (!user || typeof user !== 'object') {
    return user;
  }

  const normalizedRole = normalizeRole(user.role);
  const legacyAdmin = hasLegacyAdminFlag(user);

  return {
    ...user,
    role: normalizedRole || (legacyAdmin ? 'admin' : null),
    isAdmin: normalizedRole === 'admin' || legacyAdmin
  };
};
