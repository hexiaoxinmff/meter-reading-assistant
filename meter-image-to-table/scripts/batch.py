#!/usr/bin/env python3
"""Create and maintain an explicit, resumable photograph inventory."""
import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff', '.heic'}
STATUSES = {'未处理', '待填写', '已填写', '原表已有相同值', '重复照片', '待确认', '无法读取'}
FIELDS = {'status', 'kind', 'location', 'reading', 'period', 'workbook', 'sheet', 'cell', 'reason', 'notes'}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    with path.open(encoding='utf-8-sig') as f:
        data = json.load(f)
    if data.get('version') != 1 or not isinstance(data.get('items'), list):
        raise ValueError('清单格式或版本不支持')
    return data


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False, suffix='.tmp') as f:
        temp = f.name
        try:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        except BaseException:
            os.unlink(temp)
            raise
    try:
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def inventory(paths):
    result = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            raise ValueError(f'输入路径不存在：{p}')
        if p.is_dir():
            result.extend(sorted((q.resolve() for q in p.rglob('*') if q.is_file() and q.suffix.lower() in EXTENSIONS), key=lambda q: str(q).casefold()))
        elif p.is_file() and p.suffix.lower() in EXTENSIONS:
            result.append(p)
        else:
            raise ValueError(f'不是支持的图片文件或文件夹：{p}')
    return result


def check(data):
    problems = []
    for item in data['items']:
        p = Path(item['path'])
        try:
            if digest(p) != item['sha256']:
                problems.append({'id': item['id'], 'problem': '文件内容已变化'})
        except OSError as e:
            problems.append({'id': item['id'], 'problem': str(e)})
    return problems


def main():
    ap = argparse.ArgumentParser(description='照片清点、断点续处理及数量对账；不识别读数。')
    subs = ap.add_subparsers(dest='cmd', required=True)
    a = subs.add_parser('init', help='从指定文件和文件夹建立新清单')
    a.add_argument('--manifest', required=True)
    a.add_argument('inputs', nargs='+')
    a = subs.add_parser('set', help='使用 JSON 更新单张照片的状态和结果')
    a.add_argument('--manifest', required=True)
    a.add_argument('--id', required=True)
    a.add_argument('--data', required=True, help='包含 status、reading 等字段的 UTF-8 JSON 文件')
    a = subs.add_parser('set-many', help='一次保存多张照片的识别记录，整批检查后写入')
    a.add_argument('--manifest', required=True)
    a.add_argument('--data', required=True, help='UTF-8 JSON 数组，每项包含 id 和允许的字段')
    a = subs.add_parser('summary', help='核验原照片并统计状态')
    a.add_argument('--manifest', required=True)
    a = subs.add_parser('plan', help='从明确待填写项目生成一份台账的填写计划')
    a.add_argument('--manifest', required=True)
    a.add_argument('--workbook', required=True)
    a.add_argument('--output', required=True)
    args = ap.parse_args()
    path = Path(args.manifest).expanduser().resolve()
    if args.cmd == 'init':
        if path.exists():
            raise ValueError('清单已存在；请使用该清单续跑或指定新文件名')
        files = inventory(args.inputs)
        if not files:
            raise ValueError('没有找到支持的图片')
        items, first = [], {}
        for n, p in enumerate(files, 1):
            identifier = f'P{n:05d}'
            try:
                h = digest(p)
                duplicate = first.get(h)
                first.setdefault(h, identifier)
                items.append({'id': identifier, 'path': str(p), 'sha256': h, 'duplicate_candidate': duplicate, 'status': '未处理'})
            except OSError as e:
                items.append({'id': identifier, 'path': str(p), 'sha256': None, 'duplicate_candidate': None, 'status': '无法读取', 'reason': str(e)})
        save(path, {'version': 1, 'items': items})
        print(json.dumps({'manifest': str(path), 'total': len(items), 'duplicate_candidates': sum(bool(x['duplicate_candidate']) for x in items)}, ensure_ascii=False))
        return 0
    data = load(path)
    if args.cmd in {'set', 'set-many'}:
        with Path(args.data).open(encoding='utf-8-sig') as f:
            updates = json.load(f)
        if args.cmd == 'set':
            if not isinstance(updates, dict):
                raise ValueError('单张更新必须是 JSON 对象')
            updates = [dict(updates, id=args.id)]
        if not isinstance(updates, list) or not updates:
            raise ValueError('批量更新必须是非空 JSON 数组')
        seen = set()
        for update in updates:
            if not isinstance(update, dict) or not set(update) <= FIELDS | {'id'} or not update.get('id') or ('status' in update and update['status'] not in STATUSES):
                raise ValueError('更新字段或状态不合法')
            ident = update['id']
            if ident in seen:
                raise ValueError('批量更新包含重复编号')
            seen.add(ident)
            matches = [x for x in data['items'] if x['id'] == ident]
            if len(matches) != 1:
                raise ValueError('照片编号不存在或不唯一')
            item = matches[0]
            if item['sha256'] is None or digest(Path(item['path'])) != item['sha256']:
                raise ValueError('照片不可读取或内容改变，不能保存结果')
            item.update({k: v for k, v in update.items() if k != 'id'})
        save(path, data)
        print(json.dumps({'updated': len(updates), 'ids': sorted(seen)}, ensure_ascii=False))
        return 0
    if args.cmd == 'plan':
        workbook = Path(args.workbook).expanduser().resolve()
        target = Path(args.output).expanduser().resolve()
        if target.exists() or target in {path, workbook}:
            raise ValueError('计划输出须为不同的新文件')
        changes, seen = [], set()
        for item in data['items']:
            if item['status'] != '待填写':
                continue
            if not item.get('workbook'):
                raise ValueError(f"{item['id']} 缺少台账路径")
            if Path(item['workbook']).expanduser().resolve() != workbook:
                continue
            if not item.get('sha256') or digest(Path(item['path'])) != item['sha256']:
                raise ValueError(f"{item['id']} 照片缺失或内容变化，不能生成计划")
            reading = item.get('reading')
            if isinstance(reading, bool) or not isinstance(reading, (int, float)) or not math.isfinite(reading) or not item.get('sheet') or not item.get('cell'):
                raise ValueError(f"{item['id']} 缺少明确的数字、工作表或单元格")
            key = (item['sheet'], item['cell'].upper())
            if key in seen:
                raise ValueError(f'{key} 有多张待填写照片，先核实冲突')
            seen.add(key)
            changes.append({'sheet': key[0], 'cell': key[1], 'before': None, 'after': reading})
        if not changes:
            raise ValueError('这份台账没有待填写项目')
        workbook_hash = digest(workbook)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as f:
            json.dump({'source_sha256': workbook_hash, 'changes': changes}, f, ensure_ascii=False, indent=2)
        print(json.dumps({'plan': str(target), 'changes': len(changes)}, ensure_ascii=False))
        return 0
    counts = {s: 0 for s in sorted(STATUSES)}
    for x in data['items']:
        counts[x['status']] += 1
    problems = check(data)
    print(json.dumps({'total': len(data['items']), 'counts': counts, 'duplicate_candidates': sum(bool(x.get('duplicate_candidate')) for x in data['items']), 'file_problems': problems}, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f'处理未完成：{e}', file=sys.stderr)
        raise SystemExit(2)
