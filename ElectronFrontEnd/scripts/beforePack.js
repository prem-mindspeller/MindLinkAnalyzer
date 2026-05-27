const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

module.exports = async function beforePack(context) {
    const appDir = context.appDir || context.packager?.appDir || process.cwd();
    const command = process.platform === 'win32' ? 'cmd.exe' : 'npm';
    const args = process.platform === 'win32'
        ? ['/d', '/s', '/c', 'npm.cmd run build']
        : ['run', 'build'];
    const result = spawnSync(command, args, {
        cwd: appDir,
        stdio: 'inherit',
        shell: false,
    });

    if (result.status !== 0) {
        const detail = result.error ? `: ${result.error.message}` : '';
        throw new Error(`Renderer build failed before packaging (exit ${result.status}, signal ${result.signal})${detail}`);
    }

    const indexPath = path.join(appDir, 'dist', 'index.html');
    const bundlePath = path.join(appDir, 'dist', 'bundle.js');
    const iconPath = path.join(appDir, 'icon.ico');
    if (!fs.existsSync(indexPath) || !fs.existsSync(bundlePath)) {
        throw new Error('Renderer build did not produce dist/index.html and dist/bundle.js');
    }
    if (!fs.existsSync(iconPath)) {
        throw new Error(`Application icon is missing: ${iconPath}`);
    }

    const backendDir = path.resolve(appDir, '..', 'newBackend', 'dist', 'MindlinkBackend');
    const backendExe = path.join(backendDir, 'MindlinkBackend.exe');
    const mindroveLibDir = path.join(backendDir, '_internal', 'mindrove', 'lib');
    if (!fs.existsSync(backendExe)) {
        throw new Error(`Packaged backend is missing: ${backendExe}`);
    }
    if (!fs.existsSync(mindroveLibDir)) {
        throw new Error(
            `MindRove SDK files are missing from the packaged backend: ${mindroveLibDir}. ` +
            'Rebuild with: python -m PyInstaller MindLinkBackend.spec --distpath newBackend/dist --noconfirm'
        );
    }
};
