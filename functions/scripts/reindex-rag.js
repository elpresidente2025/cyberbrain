'use strict';

/**
 * Rebuild RAG embeddings for users.
 * Usage:
 *   node functions/scripts/reindex-rag.js            # all users
 *   node functions/scripts/reindex-rag.js 100        # first 100 users
 */

const { admin, db } = require('../utils/firebaseAdmin');
const { rebuildIndexes } = require('../services/rag/indexer');

async function main() {
  const limitArg = parseInt(process.argv[2], 10);
  const limit = Number.isFinite(limitArg) && limitArg > 0 ? limitArg : null;

  console.log('Starting RAG reindexing...');

  const biosSnap = await db.collection('bios').get();
  let uids = biosSnap.docs.map((doc) => doc.id);

  if (limit) {
    uids = uids.slice(0, limit);
    console.log(`Applying limit: ${uids.length} users`);
  }

  if (uids.length === 0) {
    console.log('No bios found. Nothing to reindex.');
    return;
  }

  console.log(`Reindexing ${uids.length} users...`);
  const { success, failed } = await rebuildIndexes(uids);

  console.log(`Reindex complete. success=${success}, failed=${failed}`);
  await admin.app().delete();
  process.exit(0);
}

main().catch((error) => {
  console.error('Reindex failed:', error);
  process.exit(1);
});
