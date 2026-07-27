# 更新公告

## 2026-07-27 — 发布工程化与安装可靠性

- 新增自包含发布校验器，统一检查 manifest、v2 图集、透明度、绿色边缘、74 个非空单元格（73 帧动画/方向 + neutral）、左右跑镜像、发布哈希与 QA 门槛。
- 新增 GitHub Actions，在 Linux 上验证发布包，并在 Windows 隔离环境测试安装脚本。
- 安装脚本增加 manifest 校验、分阶段复制、复制前后 SHA-256 校验、幂等安装和旧版本备份。
- 新增贡献指南与发布检查清单，明确完整动作行返修、一次去色和版权素材边界。
- 本次只增强工程流程，没有修改已通过视觉 QA 的桌宠图集。

## 2026-07-27 — 成熟去绿边流程与完整 QA 发布

### 已完成

- 将本机已验证的右向奔跑修复正式同步到仓库发布包；第 1 行八帧均为第 2 行同序帧的精确水平镜像。
- 对已有 v2 图集执行一次修复性局部去绿边：修改 19,614 个轮廓 RGB 像素，其中 18,437 个完成颜色去污染。
- 完整保留 Alpha、动作位置、帧序和真实绿色饰品；没有全局删除绿色色系。
- 仓库图集与本机安装图集 SHA-256 统一为 `5BC49E16AEA040C5D5101ED4FC8DCB174942079ECD98B18EAE091BBD2B2220FC`。
- 新增九行动画 GIF、三份隔离方向盲测、严格多数合并结果、盲测校验、视觉 QA 和成熟生产流程文档。

### 验证结果

- 1536×2288、RGBA WebP、8×11、`spriteVersionNumber: 2`；
- 透明 RGB 残留 0；
- 图集结构错误 0、警告 0；
- 四个基准方向盲测硬门槛全部通过；
- 保留部分中间方向较弱及首尾连续性变化作为非阻塞提醒。

当前成品已经通过验收，不应继续重复去色。后续若优化方向动画，应完整重做对应八帧方向行。

## 2026-07-21 — 右向拖拽修复与运行时限制说明

### 已修复

- 修复 `running-right`（第 1 行）与 `running-left`（第 2 行）曾使用相同朝向素材的问题。
- 保留已正确的左向跑步帧，并对每个 `192 × 208` 单元格单独水平镜像，生成同帧序的右向跑步动画；不会反转跑步循环的节奏。
- 更新发布图集、动作总览图与结构验证报告。
- 新增 `workflow/tools/mirror_running_left_to_right.py`，用于可复现地修复同类方向镜像问题。
- 已验证安装包为 `1536 × 2288`、RGBA WebP、8 列 × 11 行，并且 `spriteVersionNumber: 2` 图集验证通过。

### 16 个 Look 方向：素材完成，但当前无法可靠触发

图集第 9、10 行包含 16 个顺时针视线方向：

```text
000, 022.5, 045, 067.5, 090, 112.5, 135, 157.5,
180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5
```

它们是 Look（视线）帧，不是移动帧。`000` 为向上、`090` 为屏幕右侧、`180` 为向下、`270` 为屏幕左侧；其余帧用于平滑过渡。

当前 Codex Desktop 的桌宠覆盖层只会在收到内部 `avatar-overlay-computer-use-cursor-changed` 事件时选择这些帧。项目已确认：物理鼠标、内置 Browser Use，以及本地 Computer Use 的 SendInput/UI Automation 操作都不会稳定发送该事件。因此不应通过重画素材、增加 sprites 或修改 `pet.json` 来尝试修复；这些方向素材会保留，等待 Codex 修复事件链后直接可用。

该现象已有公开反馈：[openai/codex#33224](https://github.com/openai/codex/issues/33224)。该 issue 标注为 `bug`、`pets`、`windows-os`，并有 macOS 复现报告；截至本公告日期仍处于 Open 状态。

### Codex Computer Use 的已知 Windows 限制

Windows 上原生 Computer Use 控制 Chrome/Edge 时，可能在首次读取浏览器窗口状态前中止，并提示无法以足够置信度确定当前 URL。该问题与桌宠 Look 是两个独立的问题：

- 浏览器 URL 检测失败会阻止原生 Computer Use 在 Chromium 浏览器内继续操作；
- 即使本地 Computer Use 能操作计算器等非浏览器应用，它也不等于桌宠内部的 Look 虚拟光标事件；
- 浏览器自动化应优先使用 Codex 内置 Browser Use 或 Chrome 控制；它们更适合浏览器任务，但同样不会触发 Look。

公开跟踪：[openai/codex#25271](https://github.com/openai/codex/issues/25271)。截至本公告日期，该 issue 仍处于 Open 状态。

### 安装更新

更新后请在 Codex / ChatGPT Desktop 中执行：

1. 打开 **Settings > Pets**，选择 **Refresh**。
2. 先切换到其他宠物，再选回“长离”。
3. 使用 `/pet` 收起后重新唤醒；若仍显示旧动画，完全退出并重新打开桌面应用。

官方 Pets 文档：<https://learn.chatgpt.com/docs/pets>
