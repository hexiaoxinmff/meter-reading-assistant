#!/usr/bin/env python3
"""Export a standalone, local review page and CSV from a batch manifest."""
import argparse
import base64
import csv
import hashlib
import html
import io
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print('缺少 Pillow，不能生成复核图片。', file=sys.stderr)
    raise SystemExit(2)

FIELDS = ['id', 'path', 'status', 'kind', 'location', 'reading', 'period', 'workbook', 'sheet', 'cell', 'reason', 'notes', 'duplicate_candidate']


def main():
    p = argparse.ArgumentParser(description='生成照片与记录并列的离线 HTML 复核页，以及 CSV 明细。')
    p.add_argument('--manifest', required=True)
    p.add_argument('--html', required=True)
    p.add_argument('--csv', required=True)
    a = p.parse_args()
    manifest, out, csvpath = map(lambda x: Path(x).resolve(), (a.manifest, a.html, a.csv))
    if len({manifest, out, csvpath}) != 3 or out.exists() or csvpath.exists() or out.suffix.lower() != '.html' or csvpath.suffix.lower() != '.csv':
        raise ValueError('复核 HTML 和 CSV 必须是不同的新文件')
    with manifest.open(encoding='utf-8-sig') as f:
        data = json.load(f)
    if data.get('version') != 1 or not isinstance(data.get('items'), list):
        raise ValueError('清单版本不支持')
    cards = []
    for item in data['items']:
        try:
            with open(item['path'], 'rb') as source:
                actual = hashlib.sha256(source.read()).hexdigest()
            if not item.get('sha256') or actual != item['sha256']:
                raise ValueError('文件内容与清点时不同')
            with Image.open(item['path']) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                im.thumbnail((640, 640))
                buf = io.BytesIO()
                im.save(buf, 'JPEG', quality=80)
                img = '<img alt="照片缩略图" src="data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode() + '">'
        except (OSError, ValueError):
            img = '<div>图片缺失或内容已变化，未显示；请检查原图。</div>'
        lines = []
        labels = {'id': '编号', 'path': '原图路径', 'status': '状态', 'kind': '水/电', 'location': '位置', 'reading': '读数', 'period': '周期', 'workbook': '台账', 'sheet': '工作表', 'cell': '单元格', 'reason': '待确认原因', 'notes': '说明', 'duplicate_candidate': '疑似重复编号'}
        for k in FIELDS:
            value = item.get(k)
            lines.append('<dt>' + labels[k] + '</dt><dd>' + html.escape(str(value) if value is not None and value != '' else '未知') + '</dd>')
        cards.append('<article>' + img + '<dl>' + ''.join(lines) + '</dl></article>')
    document = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>抄表照片复核清单</title><style>body{font-family:Arial,sans-serif;margin:24px;color:#1b2632}article{display:flex;gap:20px;border:1px solid #bbb;padding:14px;margin:16px 0}img{max-width:42%;object-fit:contain;align-self:start}dl{display:grid;grid-template-columns:110px 1fr;gap:6px;margin:0;overflow-wrap:anywhere}dt{font-weight:bold}dd{margin:0}@media(max-width:700px){article{display:block}img{max-width:100%}}</style><h1>抄表照片复核清单</h1><p>共 ' + str(len(cards)) + ' 张。缩略图仅供检索，读数须以原图和台账复核；本页面不自动写回状态。</p>' + ''.join(cards) + '</html>'
    out.parent.mkdir(parents=True, exist_ok=True)
    csvpath.parent.mkdir(parents=True, exist_ok=True)
    with csvpath.open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        for item in data['items']:
            safe = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in item.items()}
            w.writerow(safe)
    try:
        with out.open('x', encoding='utf-8') as f:
            f.write(document)
    except BaseException:
        csvpath.unlink()
        raise
    print(json.dumps({'html': str(out), 'csv': str(csvpath), 'total': len(cards)}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f'复核页未生成：{e}', file=sys.stderr)
        raise SystemExit(2)
