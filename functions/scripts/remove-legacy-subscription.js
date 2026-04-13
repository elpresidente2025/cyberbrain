'use strict';

const { admin, db } = require('../utils/firebaseAdmin');

const APPLY = process.argv.includes('--apply');
const JSON_OUTPUT = process.argv.includes('--json');
const BATCH_LIMIT = 400;

function getStringField(data, field) {
  const value = data?.[field];
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized || null;
}

async function main() {
  const snapshot = await db.collection('users').get();

  let batch = db.batch();
  let pending = 0;
  const result = {
    mode: APPLY ? 'apply' : 'dry-run',
    totalUsers: snapshot.size,
    scanned: 0,
    updatedUsers: 0,
    copiedPlanFromSubscription: 0,
    removedSubscriptionField: 0,
    mismatchedPlanCount: 0,
    samples: [],
  };

  for (const doc of snapshot.docs) {
    result.scanned += 1;

    const data = doc.data() || {};
    const plan = getStringField(data, 'plan');
    const subscription = getStringField(data, 'subscription');

    if (!subscription) {
      continue;
    }

    const updateData = {
      subscription: admin.firestore.FieldValue.delete(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    };

    result.removedSubscriptionField += 1;

    if (!plan) {
      updateData.plan = subscription;
      result.copiedPlanFromSubscription += 1;
    } else if (plan !== subscription) {
      result.mismatchedPlanCount += 1;
    }

    result.updatedUsers += 1;
    if (result.samples.length < 10) {
      result.samples.push({
        uid: doc.id,
        plan,
        subscription,
        action: !plan ? 'copy-plan-and-delete-subscription' : 'delete-subscription',
      });
    }

    if (APPLY) {
      batch.update(doc.ref, updateData);
      pending += 1;
      if (pending >= BATCH_LIMIT) {
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

  console.log('=== Remove Legacy Subscription ===');
  Object.entries(result).forEach(([key, value]) => {
    if (key === 'samples') return;
    console.log(`${key}: ${value}`);
  });

  if (result.samples.length > 0) {
    console.log('\n[samples]');
    result.samples.forEach((sample) => console.log(sample));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
