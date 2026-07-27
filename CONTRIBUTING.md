# 参与贡献

欢迎提交安装、验证、文档和完整动作行方面的改进。本仓库是非官方、非商业同人项目；提交前请先阅读 [NOTICE.md](NOTICE.md)。

## 基本要求

1. 不提交下载的官方立绘、截图、视频或其他原始第三方素材。
2. 不对已通过验证的最终图集重复执行去色或 despill。
3. 标准状态出错时返修完整动作行；Look 出错时返修完整八帧方向行，不能直接拼补最终单格。
4. 保持 `pet/changli/pet.json` 与 `spritesheet.webp` 同时更新。
5. 更新图集时同步更新 `workflow/pet_request.json` 中的发布 SHA-256 和所有相关 QA 证据。

## 本地检查

安装 Python 依赖后运行：

```powershell
python -m pip install -r requirements-dev.txt
python workflow/tools/validate_release.py
```

Windows 安装脚本可在隔离目录中测试：

```powershell
$env:CODEX_HOME = Join-Path $env:TEMP "changli-codex-test"
.\install.ps1 -SkipBackup
```

提交的 PR 必须通过 GitHub Actions 中的 `Validate release` 与 `Test Windows installer`。

完整视觉制作和返修规则见 [docs/PRODUCTION_WORKFLOW.md](docs/PRODUCTION_WORKFLOW.md)。
