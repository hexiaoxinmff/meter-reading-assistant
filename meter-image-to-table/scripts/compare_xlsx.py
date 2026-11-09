#!/usr/bin/env python3
"""Read-only XLSX comparison against an explicit list of expected cell edits."""
import argparse
import json
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print('缺少 openpyxl，无法运行只读比对；请使用可用的表格工具检查。', file=sys.stderr)
    raise SystemExit(2)


def note(cell):
    return (cell.comment.text, cell.comment.author) if cell.comment else None


def main():
    p = argparse.ArgumentParser(description='只读比较原表和结果，核对指定单元格的变更。')
    p.add_argument('original')
    p.add_argument('result')
    p.add_argument('--expected', required=True, help='UTF-8 JSON：{"changes":[{"sheet":"示例","cell":"B2","before":null,"after":123.45}]}')
    p.add_argument('--full', action='store_true', help='输出全部差异，默认每类最多显示50项')
    args = p.parse_args()
    with Path(args.expected).open('r', encoding='utf-8-sig') as f:
        entries = json.load(f)['changes']
    expected = {}
    for e in entries:
        key = (e['sheet'], e['cell'].upper())
        if key in expected or 'before' not in e or 'after' not in e:
            raise ValueError('预期改动有重复或缺少 before/after')
        expected[key] = (e['before'], e['after'])
    before = openpyxl.load_workbook(args.original, data_only=False)
    after = openpyxl.load_workbook(args.result, data_only=False)
    report = {'sheet_order_equal': before.sheetnames == after.sheetnames, 'changes': [],
              'unexpected_changes': [], 'missing_expected': [], 'format_changes': [],
              'structure_changes': [], 'limitations': '只检查列出的单元格属性及工作表结构；不验证页面视觉、宏、图表、外链或全部文件元数据。'}
    observed = set()
    for name in before.sheetnames:
        if name not in after:
            report['structure_changes'].append({'sheet': name, 'item': '工作表缺失'})
            continue
        x, y = before[name], after[name]
        checks = {'合并区域': str(x.merged_cells) == str(y.merged_cells),
                  '数据验证': str(x.data_validations) == str(y.data_validations),
                  '冻结窗格': x.freeze_panes == y.freeze_panes,
                  '工作表可见性': x.sheet_state == y.sheet_state,
                  '行尺寸': [(k, str(v)) for k, v in x.row_dimensions.items()] == [(k, str(v)) for k, v in y.row_dimensions.items()],
                  '列尺寸': [(k, str(v)) for k, v in x.column_dimensions.items()] == [(k, str(v)) for k, v in y.column_dimensions.items()]}
        for label, ok in checks.items():
            if not ok:
                report['structure_changes'].append({'sheet': name, 'item': label})
        for row, col in sorted(set(x._cells) | set(y._cells)):
            c, d = x.cell(row, col), y.cell(row, col)
            key = (name, c.coordinate)
            if (c.value, c.data_type) != (d.value, d.data_type):
                item = {'sheet': name, 'cell': c.coordinate, 'before': c.value, 'after': d.value}
                report['changes'].append(item)
                observed.add(key)
                if key not in expected or expected[key] != (c.value, d.value) or (c.value == d.value and c.data_type != d.data_type):
                    report['unexpected_changes'].append(item)
            for attr in ('font', 'fill', 'border', 'alignment', 'number_format', 'protection'):
                if str(getattr(c, attr)) != str(getattr(d, attr)):
                    report['format_changes'].append({'sheet': name, 'cell': c.coordinate, 'item': attr})
            if note(c) != note(d):
                report['format_changes'].append({'sheet': name, 'cell': c.coordinate, 'item': '批注'})
    for key in expected.keys() - observed:
        report['missing_expected'].append({'sheet': key[0], 'cell': key[1]})
    report['pass'] = (report['sheet_order_equal'] and not any(report[k] for k in
        ('unexpected_changes', 'missing_expected', 'format_changes', 'structure_changes')))
    report['counts'] = {k: len(report[k]) for k in ('changes', 'unexpected_changes', 'missing_expected', 'format_changes', 'structure_changes')}
    if not args.full:
        report['truncated'] = any(n > 50 for n in report['counts'].values())
        for k in report['counts']:
            report[k] = report[k][:50]
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'比对未完成：{exc}', file=sys.stderr)
        raise SystemExit(2)
