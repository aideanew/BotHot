# 本地 Markdown 示例 Provider

这个目录是一个完整、可运行的开发者示例。它不会被万能导自动加载，因为目录名以下划线开头。

如果要在桌面端测试它，可以复制一份并去掉下划线：

```text
providers/demo-local-export/
```

然后重启万能导。

## 它演示了什么

- 使用 `provider.json` 声明标准 UI。
- 使用 `actions.py --scan-toc` 返回目录树。
- 使用 `actions.py --export` 导出用户勾选的 Markdown。
- 保留原始目录结构。
- 复制 Markdown 中引用的相对图片和附件。
- 输出 `progress x/y` 进度和最终 JSON 报告。

## 本地命令测试

```powershell
python providers\_demo_local_export\actions.py --source-dir D:\notes --scan-toc
python providers\_demo_local_export\actions.py --source-dir D:\notes --output D:\out --export --copy-resources
```

## 适合怎么借鉴

如果你要接入一个新平台，可以先让平台脚本把远端内容转换成本地 Markdown，再参考这个示例处理目录结构、资源复制、进度日志和最终报告。
