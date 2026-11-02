"""Offline, read-only release verification and reproducible ZIP construction."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.5.2'
SKILL_NAME = 'visual-director-system-v1-5-2'
DIRECTORIES = {'adapters', 'docs', 'knowledge', 'references', 'schemas', 'scripts', 'tests'}
TOP_FILES = {'.gitignore', 'SKILL.md', 'README.md', 'LICENSE', 'RELEASE_NOTES.md', 'RELEASE-MANIFEST.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(root):
    rows = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            continue
        require(not path.is_symlink(), '发行目录不允许符号链接: ' + relative.as_posix())
        if not path.is_file():
            continue
        name = relative.as_posix()
        require(relative.parts[0] in DIRECTORIES or name in TOP_FILES, '非发行组件: ' + name)
        require(name in TOP_FILES or path.suffix in {'.md', '.py', '.json'}, '非发行文件类型: ' + name)
        require(not any(part in {'__pycache__', '.venv', 'venv', 'tasks', 'snapshots', 'logs', 'reports'} for part in relative.parts), '运行数据或缓存混入: ' + name)
        require(path.name not in {'preferences.json', 'preferences.json.bak', 'CURRENT', '.writer.lock', '.prefs.lock'}, '个人运行数据混入: ' + name)
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        patterns = (r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{30,}', r'sk-[A-Za-z0-9]{24,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'(?i)C:\\Users\\[^<>\s\\]+\\')
        require(not any(re.search(pattern, text) for pattern in patterns), '疑似凭据或个人绝对路径，需人工检查文件: ' + name)
        rows[name] = hashlib.sha256(raw).hexdigest()
    return rows


def verify(root=ROOT):
    root = Path(root).resolve()
    files = inventory(root)
    require(TOP_FILES <= set(files), '缺少入口、授权或发行元数据')
    manifest = json.loads((root / 'RELEASE-MANIFEST.json').read_text(encoding='utf-8'))
    require(manifest.get('version') == VERSION and manifest.get('skill_name') == SKILL_NAME, '发行版本或技能名不一致')
    expected = {name: value for name, value in files.items() if name != 'RELEASE-MANIFEST.json'}
    require(manifest.get('files') == expected, '发行清单与文件实际内容不一致；不能带错配清单发行')
    entry = (root / 'SKILL.md').read_text(encoding='utf-8')
    require(entry.startswith('---\n'), '缺少技能入口frontmatter')
    header = entry.split('---', 2)[1]
    require(re.search(r'^name: ' + re.escape(SKILL_NAME) + r'$', header, re.M), 'SKILL技能名不一致')
    require(re.search(r'^description: .+', header, re.M), '入口缺少description')
    registry = json.loads((root / 'adapters/registry.json').read_text(encoding='utf-8'))
    require(registry.get('version') == VERSION, 'Adapter产品版本不一致')
    for name in ('contracts.py', 'prefs.py'):
        module = ast.parse((root / 'scripts' / name).read_text(encoding='utf-8'))
        values = [node.value.value for node in module.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
        require(values == [VERSION], '工具产品版本不一致: ' + name)
    return {'result': 'pass', 'scope': 'local-package-structure-version-hashes-and-basic-sensitive-data-scan', 'version': VERSION, 'files': len(files), 'semantic_and_image_quality': 'not_verified'}


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    report = verify(root)
    require(not output.is_relative_to(root), 'ZIP须放在源码目录之外')
    require(not output.exists(), '目标ZIP已存在，拒绝覆盖')
    require(output.parent.is_dir(), 'ZIP父目录不存在')
    files = inventory(root)
    temporary = output.parent / ('.release-' + uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in files:
                info = zipfile.ZipInfo(SKILL_NAME + '/' + name, date_time=(2026, 11, 2, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (root / name).read_bytes())
        with zipfile.ZipFile(temporary) as archive:
            require(archive.testzip() is None, 'ZIP CRC校验失败')
            actual = {name[len(SKILL_NAME) + 1:]: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
            require(actual == files, 'ZIP与目录内容不一致')
        require(inventory(root) == files, '打包过程中源文件发生变化')
        # Exclusive creation avoids replacing a file produced by another process.
        with output.open('xb') as handle:
            handle.write(temporary.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        return {**report, 'archive': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='strict')
    parser = argparse.ArgumentParser(description='视觉导演系统 V1.5.2 本地发行校验/打包；不联网、不上传GitHub')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify')
    builder = commands.add_parser('build')
    builder.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = verify() if args.command == 'verify' else build(ROOT, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'result': 'fail', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
