"""Assemble on Linux with a verified launcher, or compile the launcher on macOS."""
import argparse
import hashlib
import plistlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--launcher', type=Path)
args=parser.parse_args()
version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
app=args.output/'ai 军师 jev 改进版.app'
if app.exists():
    raise SystemExit(f'Refusing to overwrite existing bundle: {app}')
resources=app/'Contents/Resources';code=resources/'app';binary=app/'Contents/MacOS/vles-chat'
code.mkdir(parents=True);binary.parent.mkdir(parents=True)
for folder in ('src','tests','packaging'):
    shutil.copytree(ROOT/folder,code/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('pyproject.toml','uv.lock','README.md','.python-version','LICENSE','NOTICE','start.command'):
    shutil.copy2(ROOT/name,code/name)
shutil.copy2(ROOT/'packaging/launcher.zsh', resources/'launcher.zsh')
if args.launcher:
    shutil.copy2(args.launcher,binary)
elif sys.platform=='darwin':
    subprocess.run(['xcrun','clang','-std=c11','-Os','-Wall','-Wextra','-Werror','-arch','arm64','-mmacosx-version-min=13.0',str(ROOT/'packaging/launcher.c'),'-o',str(binary)],check=True)
else:
    raise SystemExit('Non-macOS builds require --launcher pointing to the verified upstream native launcher.')
if binary.read_bytes()[:4] != bytes.fromhex('cffaedfe'):
    raise SystemExit('Launcher must be a 64-bit Mach-O binary.')
binary.chmod(0o755);(resources/'launcher.zsh').chmod(0o755)
(code/'start.command').chmod(0o755)
info={
 'CFBundleName':'ai 军师 jev 改进版','CFBundleDisplayName':'ai 军师 jev 改进版','CFBundleIdentifier':'com.vles.chathelper',
 'CFBundleVersion':version,'CFBundleShortVersionString':version,'CFBundlePackageType':'APPL',
 'CFBundleExecutable':'vles-chat','CFBundleIconFile':'AppIcon','LSMinimumSystemVersion':'13.0',
 'LSArchitecturePriority':['arm64'],'LSUIElement':True,'NSHighResolutionCapable':True,
 'NSScreenCaptureUsageDescription':'读取你选中的微信聊天窗口，在本机识别文字。',
 'NSAppleEventsUsageDescription':'仅在点击填入时将所选候选文字写入聊天输入框。',
}
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
icon=ROOT/'packaging/AppIcon.icns'
if icon.exists():shutil.copy2(icon,resources/'AppIcon.icns')
if sys.platform=='darwin':
    subprocess.run(['/usr/bin/codesign','--force','--sign','-','--timestamp=none',str(app)],check=True)
    subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True)
print(app)
