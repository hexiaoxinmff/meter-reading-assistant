#!/usr/bin/env python3
"""Update an existing result workbook after immutable backup and validation."""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''): h.update(part)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument('result'); p.add_argument('--original',required=True); p.add_argument('--plan',required=True); p.add_argument('--backup-dir',required=True); a=p.parse_args()
    result=Path(a.result).resolve(); original=Path(a.original).resolve(); backup_dir=Path(a.backup_dir).resolve()
    if not result.is_file() or not original.is_file() or result == original or os.path.samefile(result,original): raise ValueError('结果文件与原台账必须是不同且存在的文件')
    before=sha(result); orig=sha(original)
    with open(a.plan, encoding='utf-8-sig') as f: plan=json.load(f)
    if plan.get('source_sha256') != before: raise ValueError('计划未绑定当前结果表或结果表已变化，请重新核对')
    backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/(result.stem+'_'+uuid.uuid4().hex+'.xlsx')
    with result.open('rb') as src, backup.open('xb') as dst: shutil.copyfileobj(src,dst)
    if sha(backup)!=before or sha(result)!=before: raise ValueError('备份核验失败或结果表已变化；未更新结果表')
    fd,tempname=tempfile.mkstemp(prefix='.meter-update-',suffix='.xlsx',dir=result.parent); os.close(fd); os.unlink(tempname); temp=Path(tempname)
    try:
        scripts=Path(__file__).resolve().parent
        subprocess.run([sys.executable,str(scripts/'fill_xlsx.py'),str(backup),str(temp),'--plan',a.plan],check=True)
        check=subprocess.run([sys.executable,str(scripts/'compare_xlsx.py'),str(backup),str(temp),'--expected',a.plan],capture_output=True,text=True,encoding='utf-8',check=True)
        audit=json.loads(check.stdout)
        if not audit.get('pass'): raise ValueError('修改前后核对未通过')
        if sha(result)!=before or sha(original)!=orig: raise ValueError('操作期间结果表或原台账发生变化；未更新')
        os.replace(temp,result)
        print(json.dumps({'result':str(result),'backup':str(backup),'backup_sha256':before,'result_sha256':sha(result),'original_sha256':orig,'compare_pass':True},ensure_ascii=False))
    finally:
        if temp.exists(): temp.unlink()

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,subprocess.CalledProcessError,KeyError) as e:
        print('更新未完成：'+str(e),file=sys.stderr); sys.exit(2)
