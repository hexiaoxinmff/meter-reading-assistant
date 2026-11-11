#!/usr/bin/env python3
"""Compare independently verified labels with predictions in CSV files."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


def load(path, required):
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('CSV 缺少字段：' + ', '.join(sorted(required)))
        rows = {}
        for row in reader:
            key = row['id'].strip()
            if not key or key in rows:
                raise ValueError('编号为空或重复：' + key)
            rows[key] = {k: (v or '').strip() for k, v in row.items()}
        return rows


def same_number(a, b):
    try:
        x, y = Decimal(a), Decimal(b)
        return x.is_finite() and y.is_finite() and x == y
    except InvalidOperation:
        return False


def main():
    parser = argparse.ArgumentParser(description='按独立人工标准答案计算识别结果；不修改源文件。')
    parser.add_argument('--truth', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    truth = load(args.truth, {'id', 'type', 'confirmed', 'reading', 'location'})
    pred = load(args.predictions, {'id', 'status', 'reading', 'location'})
    if set(pred) - set(truth):
        raise ValueError('预测编号不在标准答案中：' + ', '.join(sorted(set(pred) - set(truth))))
    groups = defaultdict(Counter)
    for key, t in truth.items():
        c = groups[t['type'] or '未分类']
        c['总数'] += 1
        if t['confirmed'] not in {'是', '否'}:
            raise ValueError('confirmed 只能填 是 或 否：' + key)
        p = pred.get(key, {})
        if not p:
            c['缺少预测'] += 1
        status = p.get('status', '')
        if status not in {'已识别', '待确认', '无法读取', '未处理', ''}:
            raise ValueError('未知预测状态：' + key)
        if t['confirmed'] == '否':
            c['标准未确认'] += 1
            continue
        if not t['reading'] or not t['location']:
            raise ValueError('已确认标准答案必须包含读数和位置：' + key)
        c['标准已确认'] += 1
        if status == '已识别':
            c['已识别'] += 1
            c['读数正确'] += same_number(t['reading'], p.get('reading', ''))
            c['位置正确'] += t['location'] == p.get('location', '')
            c['读数和位置均正确'] += same_number(t['reading'], p.get('reading', '')) and t['location'] == p.get('location', '')
        else:
            c['未自动识别'] += 1
    result = {'说明': '准确率分母为标准已确认且预测状态为已识别的照片；覆盖率分母为标准已确认照片。未确认标准不计正确率。位置采用规范名称精确比较。', '分组': {}}
    total = Counter()
    for name, counts in sorted(groups.items()):
        total.update(counts)
        result['分组'][name] = dict(counts)
    result['合计'] = dict(total)
    n, identified = total['标准已确认'], total['已识别']
    result['合计']['覆盖率'] = identified / n if n else None
    for label in ('读数正确', '位置正确', '读数和位置均正确'):
        result['合计'][label + '率'] = total[label] / identified if identified else None
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, csv.Error) as exc:
        raise SystemExit('评估失败：' + str(exc))

