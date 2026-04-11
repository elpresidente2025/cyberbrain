#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');
const sourcePath = path.join(repoRoot, 'shared', 'plan-catalog.json');
const targetPaths = [
  path.join(repoRoot, 'functions', 'config', 'plan-catalog.json'),
  path.join(repoRoot, 'frontend', 'src', 'config', 'plan-catalog.json'),
];

function readNormalizedJson(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  return `${JSON.stringify(JSON.parse(raw), null, 2)}\n`;
}

function ensureDirectory(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function main() {
  const normalizedSource = readNormalizedJson(sourcePath);
  const shouldCheckOnly = process.argv.includes('--check');
  const changedTargets = [];

  for (const targetPath of targetPaths) {
    ensureDirectory(targetPath);
    const current = fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null;

    if (current !== normalizedSource) {
      changedTargets.push(path.relative(repoRoot, targetPath));

      if (!shouldCheckOnly) {
        fs.writeFileSync(targetPath, normalizedSource, 'utf8');
      }
    }
  }

  if (shouldCheckOnly && changedTargets.length > 0) {
    console.error(`plan catalog sync required: ${changedTargets.join(', ')}`);
    process.exitCode = 1;
    return;
  }

  if (changedTargets.length === 0) {
    console.log('plan catalog already synced');
    return;
  }

  console.log(`plan catalog synced: ${changedTargets.join(', ')}`);
}

main();
