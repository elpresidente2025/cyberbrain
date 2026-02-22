// Compatibility wrapper: delegate to deploy.py.
const { spawnSync } = require('child_process');

const args = ['deploy.py', ...process.argv.slice(2)];
const result = spawnSync('python', args, {
  stdio: 'inherit',
  shell: true,
});

process.exit(result.status == null ? 1 : result.status);

