#!/usr/bin/env python3
"""Report the packages available to the Python interpreter executing this file."""
import importlib.util
import json
import sys

packages = {name: importlib.util.find_spec(name) is not None for name in ('openpyxl', 'PIL', 'paddleocr', 'paddle')}
print(json.dumps({'python': sys.executable, 'version': sys.version.split()[0], 'packages': packages,
                  'note': '仅检查当前 Python 是否能找到模块；不代表豆包可访问、模块可正常运行或 OCR 模型已配置。'}, ensure_ascii=False, indent=2))
