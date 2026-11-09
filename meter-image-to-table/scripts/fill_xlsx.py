#!/usr/bin/env python3
"""Write approved numbers into blank XLSX cells with minimal OOXML changes."""
import argparse
import hashlib
import json
import math
import os
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import openpyxl
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
except ImportError:
    print('缺少 openpyxl，不能安全检查台账。', file=sys.stderr)
    raise SystemExit(2)

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def worksheets(z):
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rel = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets = {r.get('Id'): r.get('Target') for r in rel.findall('p:Relationship', NS) if r.get('TargetMode') != 'External'}
    result = {}
    for sh in wb.findall('m:sheets/m:sheet', NS):
        target = targets[sh.get('{%s}id' % NS['r'])]
        path = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
        if not path.startswith('xl/worksheets/') or path not in z.namelist():
            raise ValueError('工作表路径不受支持')
        result[sh.get('name')] = path
    return result


def patch_sheet(content, changes):
    # Restrict editing to ordinary Excel-generated, unprefixed worksheet XML.
    if re.search(rb'<(?:\w+:)?sheetProtection(?:\s|/|>)', content):
        raise ValueError('工作表受保护，不予写入')
    if re.search(rb'<\w+:(?:worksheet|sheetData|row|c)(?:\s|/|>)', content):
        raise ValueError('工作表 XML 使用不支持的命名空间前缀')
    for coordinate, number in changes:
        col, row = coordinate_from_string(coordinate)
        row_pat = rb'<row\b(?=[^>]*\br="' + str(row).encode() + rb'")[^>]*(?:/>|>.*?</row\s*>)'
        found = list(re.finditer(row_pat, content, re.DOTALL))
        if len(found) != 1:
            raise ValueError(f'{coordinate}: 行不存在或不唯一，不写入')
        rm = found[0]
        rowxml = rm.group()
        if rowxml.rstrip().endswith(b'/>'):
            rowxml = rowxml.rstrip()[:-2] + b'></row>'
        cell_pat = rb'<c\b(?=[^>]*\br="' + coordinate.encode() + rb'")[^>]*(?:/>|>.*?</c\s*>)'
        matches = list(re.finditer(cell_pat, rowxml, re.DOTALL))
        if len(matches) > 1:
            raise ValueError(f'{coordinate}: 单元格重复')
        value = str(number).encode('ascii')
        if matches:
            cm = matches[0]
            cell = cm.group()
            tag = cell[:cell.find(b'>') + 1]
            if re.search(rb'\bt="(?!n")[^"]+"', tag) or re.search(rb'<(?:\w+:)?(?:v|f|is)\b', cell):
                raise ValueError(f'{coordinate}: 单元格不为空或类型不受支持')
            if tag.rstrip().endswith(b'/>'):
                replacement = tag.rstrip()[:-2] + b'><v>' + value + b'</v></c>'
            else:
                replacement = tag + b'<v>' + value + b'</v>' + cell[len(tag):]
            rowxml = rowxml[:cm.start()] + replacement + rowxml[cm.end():]
        else:
            new = b'<c r="' + coordinate.encode() + b'"><v>' + value + b'</v></c>'
            cells = list(re.finditer(rb'<c\b(?=[^>]*\br="([A-Z]+)([0-9]+)")[^>]*(?:/>|>.*?</c\s*>)', rowxml, re.DOTALL))
            position = None
            for cm in cells:
                if int(cm.group(2)) != row:
                    raise ValueError(f'{coordinate}: 行内坐标异常')
                if column_index_from_string(cm.group(1).decode()) > column_index_from_string(col):
                    position = cm.start()
                    break
            if position is None:
                position = cells[-1].end() if cells else rowxml.find(b'>') + 1
            rowxml = rowxml[:position] + new + rowxml[position:]
        content = content[:rm.start()] + rowxml + content[rm.end():]
    ET.fromstring(content)
    return content


def main():
    p = argparse.ArgumentParser(description='只向 XLSX 副本的空白格填写明确的数字读数。')
    p.add_argument('original')
    p.add_argument('output')
    p.add_argument('--plan', required=True, help='UTF-8 JSON，与 compare_xlsx.py 的预期变更格式一致')
    args = p.parse_args()
    source, output = Path(args.original).resolve(), Path(args.output).resolve()
    if source.suffix.lower() != '.xlsx' or output.suffix.lower() != '.xlsx' or source == output or output.exists():
        raise ValueError('输入和输出须为不同的 .xlsx，且输出文件不得已存在')
    with Path(args.plan).open(encoding='utf-8-sig') as f:
        plan_data = json.load(f)
    plan = plan_data['changes']
    source_hash = file_hash(source)
    if plan_data.get('source_sha256') and plan_data['source_sha256'] != source_hash:
        raise ValueError('台账与生成计划时不同，请重新核对并生成计划')
    if not isinstance(plan, list) or not plan:
        raise ValueError('填写计划为空')
    wb = openpyxl.load_workbook(source, data_only=False)
    groups, seen = {}, set()
    for item in plan:
        name, coord, value = item['sheet'], item['cell'].upper(), item['after']
        if item.get('before', 'missing') is not None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('仅支持从空白变为有限数字的明确计划')
        if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]*', coord) or (name, coord) in seen or name not in wb:
            raise ValueError(f'工作表或单元格无效或重复：{name}!{coord}')
        seen.add((name, coord))
        ws = wb[name]
        if ws.protection.sheet or ws[coord].value is not None or any(coord in r for r in ws.merged_cells.ranges):
            raise ValueError(f'{name}!{coord} 非空、受保护或在合并区域，不予写入')
        groups.setdefault(name, []).append((coord, value))
    wb.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with zipfile.ZipFile(source) as src:
            if any(n.startswith('_xmlsignatures/') for n in src.namelist()):
                raise ValueError('数字签名工作簿不支持修改')
            mapping = worksheets(src)
            modified = {mapping[name]: patch_sheet(src.read(mapping[name]), changes) for name, changes in groups.items()}
            fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            created = True
            with os.fdopen(fd, 'wb') as stream:
                with zipfile.ZipFile(stream, 'w') as dst:
                    dst.comment = src.comment
                    for info in src.infolist():
                        dst.writestr(info, modified.get(info.filename, src.read(info.filename)))
        if file_hash(source) != source_hash:
            raise ValueError('原文件在处理过程中发生变化')
        check = openpyxl.load_workbook(output, data_only=False)
        for item in plan:
            if check[item['sheet']][item['cell']].value != item['after']:
                raise ValueError(f"结果重读不符：{item['sheet']}!{item['cell']}")
        check.close()
    except BaseException:
        if created and output.exists():
            output.unlink()
        raise
    print(json.dumps({'output': str(output), 'source_sha256': source_hash, 'output_sha256': file_hash(output), 'written': len(plan), 'modified_parts': list(modified), 'note': '公式缓存未重算；需在支持重算的软件中打开复核。'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, ET.ParseError) as e:
        print(f'写入未完成：{e}', file=sys.stderr)
        raise SystemExit(2)
