# 水电表照片填表助手 v1.2（试用版）

识别水电表照片并匹配 Excel 台账，首次创建结果表，后续备份后更新同一结果表；原始台账单独备份。支持按平台实际能力使用，不能保证兼容所有平台。

## 安装与使用

下载仓库并按当前客户端支持的方式导入 `meter-image-to-table` 文件夹。参见[同事使用说明](meter-image-to-table/references/同事使用说明.md)和[跨平台适配](meter-image-to-table/references/跨平台适配.md)。本地脚本需 Python 3.10+ 和相应权限；OCR 为可选辅助，不清楚的读数与匹配需人工确认。

WorkBuddy 小批量试用中，用户报告已验证 v1.2 加载、部分 WPS 前缀台账填写及续填；不代表全部文件或平台兼容。识图准确率、WPS 界面显示等仍需进一步验证。仓库不包含测试照片或业务台账。

模型许可见 `meter-image-to-table/assets/models/PaddleOCR-LICENSE.txt`。
