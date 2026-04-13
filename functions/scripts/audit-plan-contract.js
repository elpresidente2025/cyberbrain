'use strict';

const { db } = require('../utils/firebaseAdmin');

function getStringField(data, field) {
  const value = data?.[field];
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized || null;
}

function getMonthlyLimit(data) {
  const value = Number.parseInt(data?.monthlyLimit, 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

async function main() {
  const json = process.argv.includes('--json');
  const snapshot = await db.collection('users').get();

  const counts = {
    totalUsers: snapshot.size,
    planOnly: 0,
    subscriptionOnly: 0,
    bothSame: 0,
    bothDifferent: 0,
    neither: 0,
    activeWithoutPlan: 0,
    planWithoutActiveStatus: 0,
    monthlyLimitWithoutPlan: 0,
    subscriptionFieldPresent: 0,
  };

  const samples = {
    mismatchedPlan: [],
    subscriptionOnly: [],
    activeWithoutPlan: [],
  };

  snapshot.forEach((doc) => {
    const data = doc.data() || {};
    const plan = getStringField(data, 'plan');
    const subscription = getStringField(data, 'subscription');
    const subscriptionStatus = getStringField(data, 'subscriptionStatus');
    const monthlyLimit = getMonthlyLimit(data);

    if (subscription) {
      counts.subscriptionFieldPresent += 1;
    }

    if (plan && subscription) {
      if (plan === subscription) {
        counts.bothSame += 1;
      } else {
        counts.bothDifferent += 1;
        if (samples.mismatchedPlan.length < 10) {
          samples.mismatchedPlan.push({ uid: doc.id, plan, subscription });
        }
      }
    } else if (plan) {
      counts.planOnly += 1;
    } else if (subscription) {
      counts.subscriptionOnly += 1;
      if (samples.subscriptionOnly.length < 10) {
        samples.subscriptionOnly.push({ uid: doc.id, subscription });
      }
    } else {
      counts.neither += 1;
    }

    if (subscriptionStatus === 'active' && !plan) {
      counts.activeWithoutPlan += 1;
      if (samples.activeWithoutPlan.length < 10) {
        samples.activeWithoutPlan.push({
          uid: doc.id,
          subscriptionStatus,
          monthlyLimit,
        });
      }
    }

    if (plan && subscriptionStatus !== 'active') {
      counts.planWithoutActiveStatus += 1;
    }

    if (monthlyLimit && monthlyLimit > 8 && !plan) {
      counts.monthlyLimitWithoutPlan += 1;
    }
  });

  const payload = { counts, samples };

  if (json) {
    console.log(JSON.stringify(payload, null, 2));
    return;
  }

  console.log('=== Plan Contract Audit ===');
  Object.entries(counts).forEach(([key, value]) => {
    console.log(`${key}: ${value}`);
  });

  if (samples.mismatchedPlan.length > 0) {
    console.log('\n[mismatched plan/subscription]');
    samples.mismatchedPlan.forEach((sample) => console.log(sample));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
