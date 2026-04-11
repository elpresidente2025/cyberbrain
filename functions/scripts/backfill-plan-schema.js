'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const {
  getDefaultPaidPlan,
  getTrialMonthlyLimit,
  getUserBillingStatus,
  getUserMonthlyLimit,
  resolvePaidPlan,
} = require('../common/plan-catalog');

const APPLY = process.argv.includes('--apply');
const JSON_OUTPUT = process.argv.includes('--json');
const batchSizeArg = process.argv.find((arg) => arg.startsWith('--batch-size='));
const BATCH_SIZE = batchSizeArg ? Number.parseInt(batchSizeArg.split('=')[1], 10) : 400;

const DEFAULT_PAID_PLAN = getDefaultPaidPlan();
const TRIAL_MONTHLY_LIMIT = getTrialMonthlyLimit();

function parseNonNegativeInt(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function mainSample(samples, payload) {
  if (samples.length >= 10) return;
  samples.push(payload);
}

async function run() {
  const snapshot = await db.collection('users').get();

  let batch = db.batch();
  let pending = 0;

  const result = {
    mode: APPLY ? 'apply' : 'dry-run',
    totalUsers: snapshot.size,
    scanned: 0,
    updatedUsers: 0,
    inferredPaidPlanUsers: 0,
    planIdBackfilled: 0,
    planNameNormalized: 0,
    billingStatusBackfilled: 0,
    billingPlanBackfilled: 0,
    billingLimitBackfilled: 0,
    monthlyLimitSynced: 0,
    subscriptionStatusSynced: 0,
    samples: [],
  };

  for (const doc of snapshot.docs) {
    result.scanned += 1;

    const user = doc.data() || {};
    const updateData = {};

    const explicitMonthlyLimit = parseNonNegativeInt(user.monthlyLimit);
    const effectiveMonthlyLimit = getUserMonthlyLimit(user, TRIAL_MONTHLY_LIMIT);
    const billingStatus = getUserBillingStatus(user);
    const resolvedPlan = resolvePaidPlan(user);
    const inferredPlan = resolvedPlan ||
      ((billingStatus === 'active' || effectiveMonthlyLimit > TRIAL_MONTHLY_LIMIT) ? DEFAULT_PAID_PLAN : null);

    if (!resolvedPlan && inferredPlan) {
      result.inferredPaidPlanUsers += 1;
    }

    if (inferredPlan && user.planId !== inferredPlan.id) {
      updateData.planId = inferredPlan.id;
      result.planIdBackfilled += 1;
    }

    if (inferredPlan && user.plan !== inferredPlan.name) {
      updateData.plan = inferredPlan.name;
      result.planNameNormalized += 1;
    }

    if (user.subscriptionStatus !== billingStatus) {
      updateData.subscriptionStatus = billingStatus;
      result.subscriptionStatusSynced += 1;
    }

    if (explicitMonthlyLimit !== effectiveMonthlyLimit) {
      updateData.monthlyLimit = effectiveMonthlyLimit;
      result.monthlyLimitSynced += 1;
    }

    if (user?.billing?.status !== billingStatus) {
      updateData['billing.status'] = billingStatus;
      result.billingStatusBackfilled += 1;
    }

    if (inferredPlan) {
      if (user?.billing?.planId !== inferredPlan.id) {
        updateData['billing.planId'] = inferredPlan.id;
        result.billingPlanBackfilled += 1;
      }

      if (user?.billing?.planName !== inferredPlan.name) {
        updateData['billing.planName'] = inferredPlan.name;
        result.billingPlanBackfilled += 1;
      }

      if (parseNonNegativeInt(user?.billing?.monthlyLimit) !== inferredPlan.monthlyLimit) {
        updateData['billing.monthlyLimit'] = inferredPlan.monthlyLimit;
        result.billingLimitBackfilled += 1;
      }
    } else if (parseNonNegativeInt(user?.billing?.monthlyLimit) !== effectiveMonthlyLimit) {
      updateData['billing.monthlyLimit'] = effectiveMonthlyLimit;
      result.billingLimitBackfilled += 1;
    }

    if (Object.keys(updateData).length === 0) {
      continue;
    }

    updateData.updatedAt = admin.firestore.FieldValue.serverTimestamp();
    updateData['billing.updatedAt'] = admin.firestore.FieldValue.serverTimestamp();

    result.updatedUsers += 1;
    mainSample(result.samples, {
      uid: doc.id,
      billingStatus,
      inferredPlanId: inferredPlan?.id || null,
      updateKeys: Object.keys(updateData),
    });

    if (APPLY) {
      batch.update(doc.ref, updateData);
      pending += 1;

      if (pending >= BATCH_SIZE) {
        await batch.commit();
        batch = db.batch();
        pending = 0;
      }
    }
  }

  if (APPLY && pending > 0) {
    await batch.commit();
  }

  if (JSON_OUTPUT) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  console.log('=== Backfill Plan Schema ===');
  Object.entries(result).forEach(([key, value]) => {
    if (key === 'samples') return;
    console.log(`${key}: ${value}`);
  });

  if (result.samples.length > 0) {
    console.log('\n[samples]');
    result.samples.forEach((sample) => console.log(sample));
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
