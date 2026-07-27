# 发布检查清单

## 图集与 manifest

- [ ] `pet.json` 的 id、显示名、路径和 `spriteVersionNumber: 2` 正确。
- [ ] 图集为透明 RGBA WebP，尺寸 1536×2288。
- [ ] 74 个非空单元格均有效（73 帧动画/方向 + neutral），未使用单元格完全透明。
- [ ] 透明像素隐藏 RGB 为 0，绿色键边缘污染为 0。
- [ ] `running-right` 八帧是 `running-left` 同序帧的精确水平镜像。
- [ ] `workflow/pet_request.json` 中的发布 SHA-256 已更新。

## 视觉 QA

- [ ] 九条标准动作 GIF 已复审。
- [ ] 16 个方向语义没有 `fail`。
- [ ] 三份隔离盲测已重新运行并合并。
- [ ] 四个基准方向硬门槛全部通过。
- [ ] 连续性警告已人工判断并记录。
- [ ] 独立最终视觉 QA 为 `pass`。

## 自动化与安装

- [ ] `python workflow/tools/validate_release.py` 通过。
- [ ] Windows 隔离安装测试通过，重复安装保持幂等。
- [ ] GitHub Actions 的 `Validate release` 与 `Test Windows installer` 通过。
- [ ] 仓库包和实际安装包 SHA-256 一致。

## 发布与文档

- [ ] README 预览、版本说明和安装步骤与当前成品一致。
- [ ] CHANGELOG 记录改动和保留警告。
- [ ] NOTICE 和版权归属声明仍然完整。
- [ ] 通过 PR 合并到受保护的 `main`。
