#!/usr/bin/env python3
"""Prepare isolated, per-user dependencies for the meter skill."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path

MODELS = {
    "PP-OCRv5_mobile_det_infer": "50446e5d01ac2a73d5319c89513281f6578414c888c602f9af13f93feefffc58",
    "PP-OCRv5_mobile_rec_infer": "566b9512b34e34a9f0db54d87b51fa5a0b9ed2cf1ab7e49728cc0b8b5a64f414",
}
SKILL = Path(__file__).resolve().parent.parent

def execute(args, timeout=1200):
    return subprocess.run([str(x) for x in args], check=True, timeout=timeout)

def can_import(python, modules):
    return subprocess.run([str(python), '-c', ';'.join('import '+x for x in modules)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90).returncode == 0

def prepare_model(root, name, digest):
    archive = SKILL / 'assets' / 'models' / (name + '.tar')
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('技能包内模型缺失或校验失败: ' + name)
    dest = root / 'models' / name
    marker = dest / '.meter-model-sha256'
    required = [dest / 'inference.json', dest / 'inference.pdiparams', dest / 'inference.yml']
    if marker.is_file() and marker.read_text().strip() == digest and all(p.is_file() and p.stat().st_size for p in required):
        return dest
    if dest.exists():
        raise ValueError('模型目录不完整，请移走该目录后重新运行: ' + str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='model-', dir=dest.parent) as tmp:
        with tarfile.open(archive, 'r') as tar:
            for m in tar.getmembers():
                parts = Path(m.name).parts
                if not parts or parts[0] != name or '..' in parts or '\\' in m.name or ':' in m.name or Path(m.name).is_absolute() or not (m.isfile() or m.isdir()):
                    raise ValueError('模型归档含有不支持的路径或链接')
            for m in tar.getmembers():
                target = Path(tmp).joinpath(*Path(m.name).parts)
                if m.isdir(): target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(m) as source, target.open('wb') as output: shutil.copyfileobj(source, output)
        staged = Path(tmp) / name
        if not all((staged / x.name).is_file() for x in required):
            raise ValueError('模型文件不完整: ' + name)
        (staged / '.meter-model-sha256').write_text(digest, encoding='ascii')
        staged.rename(dest)
    return dest

def main():
    p=argparse.ArgumentParser(description='首次自动配置水电表技能，依赖仅安装到独立用户目录。')
    p.add_argument('--root', type=Path, default=Path.home()/'.meter-image-to-table'/'runtime-v06')
    p.add_argument('--core-only', action='store_true', help='只配置基础工具')
    a=p.parse_args()
    root=a.root.expanduser().resolve()
    result={'runtime':str(root),'core_ready':False,'ocr_ready':False,'errors':[]}
    try:
        if sys.version_info < (3, 10): raise ValueError('需要 Python 3.10 或更高版本')
        root.mkdir(parents=True, exist_ok=True)
        env=root/'venv'; python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if not python.is_file(): venv.EnvBuilder(with_pip=True).create(env)
        result['python']=str(python)
        if not can_import(python, ['openpyxl','PIL']):
            execute([python,'-m','pip','install','--disable-pip-version-check','openpyxl==3.1.5','Pillow==11.3.0'])
        if not can_import(python, ['openpyxl','PIL']): raise ValueError('基础依赖安装后无法导入')
        result['core_ready']=True
        if not a.core_only:
            try:
                if not can_import(python, ['paddle','paddleocr']):
                    execute([python,'-m','pip','install','--disable-pip-version-check','paddlepaddle==3.3.1','paddleocr==3.7.0'], timeout=1800)
                if not can_import(python, ['paddle','paddleocr']): raise ValueError('OCR 依赖无法导入')
                for name,digest in MODELS.items(): result[name]=str(prepare_model(root,name,digest))
                result['ocr_ready']=True
            except Exception as e: result['errors'].append('OCR 未配置完成，可使用视觉识别: '+str(e))
    except Exception as e: result['errors'].append('基础环境未配置完成: '+str(e))
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return 0 if result['core_ready'] else 2

if __name__ == '__main__': sys.exit(main())
