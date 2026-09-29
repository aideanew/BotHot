# 标准导入 Provider 模板

这个模板用于接入“本地 Markdown 导入到某个平台”的场景。

下划线开头的目录不会被万能导自动加载。复制本目录后，把目录名改成你的平台 ID，例如：

```text
providers/your-import-provider/
```

## 适合什么场景

- 本地 Markdown 批量导入到目标平台。
- 需要先扫描本地目录，再让用户勾选部分文件。
- 需要上传本地图片或附件。
- 需要生成导入报告，方便任务中心展示失败项。

## 你需要改什么

- `provider.json`：改平台名称、能力声明、字段和动作。
- `README.md`：写清楚登录方式、权限要求、限制和测试结果。
- `actions.py`：把示例里的“复制到模拟目标目录”替换成真实平台 API。

## 返回报告建议

导入完成后，最后输出 JSON：

```json
{
  "provider": "your-import-provider",
  "mode": "import",
  "totalDocs": 10,
  "importedDocs": 9,
  "skippedDocs": 0,
  "failureCount": 1,
  "failures": [
    {
      "relativePath": "docs/broken.md",
      "error": "目标平台返回超时"
    }
  ],
  "reportFile": "输出目录/00-导入报告.json"
}
```

如果平台支持只重试失败项，请在 `provider.json` 中声明：

```json
{
  "capabilities": {
    "retryFailures": true
  },
  "retryFailures": {
    "arg": "--retry-failures",
    "label": "只重试失败项"
  }
}
```

校验器会检查 `retryFailures.arg` 是否存在。

## 提交 PR 前

- 运行 `python scripts/validate_providers.py`。
- 运行 `python scripts/quality_check.py`。
- README 写明是否支持目录结构、图片、附件、批量、断点续跑和失败重试。
- 不提交 Cookie、Token、账号密码或私人测试数据。
