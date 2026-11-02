// macOS: no Apple certificate, so give the app a free ad-hoc signature after packaging.
// Without any signature, Apple Silicon Macs report a downloaded Electron app as "damaged".
const { execFileSync } = require('node:child_process');
const path = require('node:path');

exports.default = async function (context) {
  if (context.electronPlatformName !== 'darwin') return;
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', app], { stdio: 'inherit' });
  execFileSync('codesign', ['--verify', '--deep', '--strict', app], { stdio: 'inherit' });
};
