# 长离 Codex 桌宠：Agent 交接文档

更新：2026-07-28（Asia/Shanghai）

## 当前发布状态

- 发布图集：`pet/changli/spritesheet.webp`
- 安装图集：`%USERPROFILE%\.codex\pets\changli\spritesheet.webp`
- 当前 SHA-256：`5BC49E16AEA040C5D5101ED4FC8DCB174942079ECD98B18EAE091BBD2B2220FC`
- 格式：RGBA WebP，1536×2288，8×11，单元格 192×208，`spriteVersionNumber: 2`
- 验证：零错误、零警告、透明 RGB 残留 0

发布版已经同时包含：

1. `running-right` / `running-left` 同序逐帧镜像修复；
2. Alpha 保持不变的局部去绿边修复；
3. 九行动作 QA、16 方向语义、三票盲测和连续性报告。

## 不要重复执行的操作

- 不要再次对当前发布图集运行去色或 despill。当前报告已经通过，重复处理会增加真实角色颜色被改写的风险。
- 不要单格修补 Look。方向需要返修时，完整重做 row 9 或 row 10。
- 不要再次镜像整条横向条带。左右跑必须逐格镜像，以保留帧序。

## 已知非阻塞警告

- `045→067.5` 的转头/中心移动比相邻步大；
- `157.5` 有一个透明行候选，视觉上位于衣摆负空间；
- `337.5→000` 首尾尺寸和中心变化较大，但没有方向反转；
- 部分中间角度在无标签、正常显示尺寸下单轴不够明显，四个基准方向均通过盲测硬门槛。

用户采用“流畅、没有明显问题”的实用验收标准。以上警告只在未来图像生成资源充足时作为整行重绘候选。

## Look 运行时限制

16 个 Look 帧已经存在并通过素材 QA，但当前 Codex Desktop 没有把普通物理鼠标、Browser Use 或本地 SendInput/UI Automation 稳定桥接到桌宠监听的 `avatar-overlay-computer-use-cursor-changed` 事件。

- Look 事件问题：<https://github.com/openai/codex/issues/33224>
- Windows Chromium Computer Use URL 检测问题：<https://github.com/openai/codex/issues/25271>

这是应用运行时限制，不应通过增加 sprites、修改 `pet.json` 或重画方向素材规避。

## 关键 QA 文件

- `workflow/qa/validation-release.json`
- `workflow/qa/chroma-despill-extended.json`
- `workflow/qa/review.json`
- `workflow/qa/previews/`
- `workflow/qa/direction-semantics.json`
- `workflow/qa/direction-blind-verdicts-1.json` 至 `-3.json`
- `workflow/qa/direction-blind-validation.json`
- `workflow/qa/blind-review-resolution.json`
- `workflow/qa/look-continuity.json`
- `workflow/qa/final-visual-qa.json`
- `workflow/qa/run-summary.json`

完整生产约束见 `docs/PRODUCTION_WORKFLOW.md`。

## v1.1 候选

v1.1 已完成标准行动作 A/B、Look 机制和四基准方向，但完整 row 9 受图像模型冷却与无效 CLI 凭据阻塞。稳定版未被替换。继续开发前先阅读 `docs/V1.1_CANDIDATE_STATUS.md`，不要重做已拒绝的标准动作，也不要单格拼补 Look。

## 发布前复核命令

使用 Codex bundled Python：

```powershell
$py = 'C:\Users\14841\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$validator = 'C:\Users\14841\.codex\skills\hatch-pet\scripts\validate_atlas.py'
& $py $validator '.\pet\changli\spritesheet.webp' --chroma-key '#00FF00' --require-v2
Get-FileHash -Algorithm SHA256 '.\pet\changli\spritesheet.webp'
Get-FileHash -Algorithm SHA256 "$HOME\.codex\pets\changli\spritesheet.webp"
```

两个哈希必须一致。修改后在 Codex 的 `Settings > Pets` 中 Refresh、切换宠物并重新选择长离。
