#!/usr/bin/env python3
"""Prepare a rotated or cropped copy to help inspect a meter photograph."""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print('缺少 Pillow，不能生成辅助查看图片。', file=sys.stderr)
    raise SystemExit(2)


def main():
    p = argparse.ArgumentParser(description='旋转、裁剪或放大照片副本；不识别或修改原图。')
    p.add_argument('source')
    p.add_argument('output')
    p.add_argument('--rotate', type=int, choices=[0, 90, 180, 270], default=0, help='顺时针旋转角度')
    p.add_argument('--crop', type=int, nargs=4, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'), help='旋转后的像素坐标')
    p.add_argument('--scale', type=float, default=1.0, help='缩放倍数，0.1 至 4')
    a = p.parse_args()
    src, dest = Path(a.source).resolve(), Path(a.output).resolve()
    if src == dest or dest.exists() or dest.suffix.lower() not in {'.png', '.jpg', '.jpeg'} or not 0.1 <= a.scale <= 4:
        raise ValueError('输出须为新的 PNG/JPEG，缩放倍数须为 0.1 至 4')
    with Image.open(src) as image:
        image = ImageOps.exif_transpose(image)
        if a.rotate:
            image = image.rotate(-a.rotate, expand=True)
        if a.crop:
            left, top, right, bottom = a.crop
            if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                raise ValueError(f'裁剪区域超出图片尺寸 {image.size}')
            image = image.crop(a.crop)
        if a.scale != 1:
            image = image.resize((max(1, round(image.width * a.scale)), max(1, round(image.height * a.scale))), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as f:
            if dest.suffix.lower() in {'.jpg', '.jpeg'}:
                image.convert('RGB').save(f, format='JPEG', quality=95)
            else:
                image.save(f, format='PNG')
    print(f'辅助图片：{dest}；尺寸：{image.size}。必须回看原图，插值不能恢复不可见数字。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as e:
        print(f'图片处理未完成：{e}', file=sys.stderr)
        raise SystemExit(2)
