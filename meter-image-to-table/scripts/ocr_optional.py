#!/usr/bin/env python3
"""Optional PaddleOCR 3.x local-model adapter; never interprets meter readings."""
import argparse
import importlib.util
import json
import os
import shutil
import tempfile
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='使用已安装的 PaddleOCR 和本地模型辅助识别文字，不自动填写台账。')
    p.add_argument('image')
    p.add_argument('--det-model-dir', required=True)
    p.add_argument('--rec-model-dir', required=True)
    p.add_argument('--det-model-name', default='PP-OCRv5_mobile_det')
    p.add_argument('--rec-model-name', default='PP-OCRv5_mobile_rec')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    image, det, rec, out = map(lambda x: Path(x).expanduser().resolve(), (a.image, a.det_model_dir, a.rec_model_dir, a.output))
    if not image.is_file() or not det.is_dir() or not rec.is_dir() or not any(det.iterdir()) or not any(rec.iterdir()):
        raise ValueError('图片或本地检测/识别模型目录不存在或为空')
    if out.exists() or out == image:
        raise ValueError('输出文件已存在或与原图相同')
    if importlib.util.find_spec('paddleocr') is None or importlib.util.find_spec('paddle') is None:
        raise ValueError('PaddleOCR 或 PaddlePaddle 未安装；可继续使用视觉识别流程')
    # Explicit model paths prevent use of default downloaded models. This flag disables source probing.
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    from paddleocr import PaddleOCR
    # Some Windows Paddle runtimes cannot open Unicode paths. Stage only these inputs
    # in a private temporary directory; original files are never changed.
    with tempfile.TemporaryDirectory(prefix='meter_ocr_') as tmp:
        root = Path(tmp)
        if not str(root).isascii():
            raise ValueError('系统临时目录路径含非 ASCII 字符，无法安全暂存 OCR 模型')
        def stage(path, name):
            if str(path).isascii():
                return path
            target = root / name
            if path.is_dir():
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)
            return target
        ocr_det = stage(det, 'det')
        ocr_rec = stage(rec, 'rec')
        ocr_image = stage(image, 'image' + image.suffix.lower())
        pipeline = PaddleOCR(text_detection_model_name=a.det_model_name, text_detection_model_dir=str(ocr_det),
                             text_recognition_model_name=a.rec_model_name, text_recognition_model_dir=str(ocr_rec),
                             use_doc_orientation_classify=False, use_doc_unwarping=False,
                             use_textline_orientation=False, enable_mkldnn=False)
        results = []
        for result in pipeline.predict(str(ocr_image)):
            obj = result.json
            if callable(obj):
                obj = obj()
            if isinstance(obj, dict) and isinstance(obj.get('res'), dict):
                obj['res']['input_path'] = str(image)
            results.append(obj if isinstance(obj, dict) else str(obj))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump({'image': str(image), 'results': results, 'note': '仅供辅助；不得据此单独认定表盘读数或直接写入台账。'}, f, ensure_ascii=False, indent=2, default=str)
    print(f'已生成辅助文字识别结果：{out}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'可选 OCR 未完成：{e}', file=sys.stderr)
        raise SystemExit(2)
