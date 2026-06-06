const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_NAME = 'ai-zemax-optical-design';
const srcDir = __dirname;
const destDir = path.join(os.homedir(), '.claude', 'skills', SKILL_NAME);

function copyDir(src, dest) {
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(destPath, { recursive: true });
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

console.log(`\n📦 Installing "${SKILL_NAME}" skill...\n`);

// Ensure destination exists
fs.mkdirSync(destDir, { recursive: true });

// Copy SKILL.md
const skillMd = path.join(srcDir, 'SKILL.md');
if (fs.existsSync(skillMd)) {
  fs.copyFileSync(skillMd, path.join(destDir, 'SKILL.md'));
  console.log('  ✓ SKILL.md');
}

// Copy subdirectories
const dirs = ['agents', 'scripts', 'references', 'examples', 'tests'];
for (const dir of dirs) {
  const src = path.join(srcDir, dir);
  const dest = path.join(destDir, dir);
  if (fs.existsSync(src)) {
    fs.mkdirSync(dest, { recursive: true });
    copyDir(src, dest);
    console.log(`  ✓ ${dir}/`);
  }
}

console.log(`\n✅ Skill installed to: ${destDir}`);
console.log('   Restart Claude Code to use it.\n');
