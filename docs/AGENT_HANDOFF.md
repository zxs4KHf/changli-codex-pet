# 长离 Codex 桌宠：Agent 交接文档

更新：2026-07-20（Asia/Shanghai）

## 当前结论

项目的可安装 v2 桌宠已经完成，且已安装到本机 Codex。当前需要继续验证和修复的不是图集格式，而是 **Look（16 个视线方向）的运行时事件链**。

已确认：

- `spriteVersionNumber: 2` 已正确写入，图集尺寸为 `1536 × 2288`，即 8 列 × 11 行、每格 `192 × 208`。
- 图集第 9、10 行包含完整 16 个 Look 帧；三份图集均通过 `validate_atlas.py --require-v2`。
- 当前 Codex 桌宠渲染代码确实监听 `avatar-overlay-computer-use-cursor-changed`，并且只有 v2 图集会把事件坐标换算成 16 个 Look 帧。
- 内置浏览器的 CUA（Browser Computer Use）已反复执行坐标移动、点击、滚动，但用户观察到桌宠没有 Look 变化。
- 这说明浏览器 CUA 坐标控制**不会**向桌宠覆盖层发出该原生 Computer Use 游标事件；不能把它当作 Look 的验证手段。

## 已完成的右向奔跑修复

用户确认的视觉问题属实：旧图集中 `running-right`（第 1 行）与 `running-left`（第 2 行）是同向重复，而不是左右相反。

已完成修复：

- 保留已正确的 `running-left`。
- 将第 2 行的每一个 `192 × 208` 帧单独水平镜像到第 1 行；逐帧镜像会保留跑步帧序，不能整行镜像。
- 更新了工作区成品、仓库发布包和已安装包。
- 重新生成仓库发布验证和联系表。

修复脚本：

- `workflow/tools/mirror_running_left_to_right.py`

该脚本额外清除了透明像素的隐藏 RGB，并以 WebP `exact=True` 保存；否则验证器会因透明区 RGB 残留拒绝图集。

## 关键路径

仓库根目录：

```text
C:\Users\14841\OneDrive\文档\长离桌宠
```

发布包（Git 应提交）：

```text
pet\changli\pet.json
pet\changli\spritesheet.webp
```

本机已安装包（Codex 实际读取）：

```text
C:\Users\14841\.codex\pets\changli\pet.json
C:\Users\14841\.codex\pets\changli\spritesheet.webp
```

完整工作区与 QA：

```text
制作工作区\常离-v2桌宠\final\spritesheet-extended.webp
制作工作区\常离-v2桌宠\final\validation-extended.json
制作工作区\常离-v2桌宠\final\validation-installed.json
制作工作区\常离-v2桌宠\qa\look-directions.png
制作工作区\常离-v2桌宠\qa\direction-semantics.json
制作工作区\常离-v2桌宠\qa\look-continuity.json
制作工作区\常离-v2桌宠\qa\contact-sheet-extended.png
```

仓库 QA 与预览：

```text
workflow\qa\validation-release.json
docs\images\contact-sheet.png
docs\images\look-directions.png
```

仓库远端：

```text
https://github.com/zxs4KHf/changli-codex-pet.git
```

## 运行时 Look 机制：已核实的代码证据

当前桌面端解包文件位于临时目录：

```text
%TEMP%\codex-asar-extracted\webview\assets\avatar-overlay-page-BKdM4ckd.js
%TEMP%\codex-asar-extracted\webview\assets\avatar-overlay-native-frame-jkMYd7yi.js
%TEMP%\codex-asar-extracted\webview\assets\avatar-overlay-pill-material.module-CGH-uIc-.js
```

相关实现行为：

1. 桌宠覆盖层监听 `avatar-overlay-computer-use-cursor-changed`，接收 `point`。
2. Look 帧计算函数只在 `spriteVersionNumber === 2` 时返回结果。
3. 它按桌宠中心到游标的角度，使用 `22.5°` 步长映射 16 个方向：第 9 行是 `000–157.5`，第 10 行是 `180–337.5`。
4. 指针进入拖拽状态时 Look 会被暂时禁用；否则 Look 可覆盖 idle / running / waving 的显示帧。

这证明 16 个方向的素材格式和渲染逻辑均存在。当前未证实的是 Windows 原生 Computer Use 是否把真实桌面游标点送到了上述事件。

## 为什么此前测试没有触发 Look

此前操作使用的是内置浏览器的 `tab.cua.move/click/scroll`。它能控制浏览器页面，但不会产生桌宠所监听的 `avatar-overlay-computer-use-cursor-changed` 原生覆盖层事件；用户已在多轮慢速移动和点击期间确认没有变化。

因此不要再用浏览器 CUA 来判定 Look 是否可用。

此外，本机 `C:\Users\14841\.codex\config.toml` 中当前启用的是 Browser 插件；本任务会话的可用工具列表也没有独立的 Computer Use 工具。虽然配置含有 CUA 原生管道和 `codex-computer-use.exe` 路径，但这不等于 Computer Use 插件的 server/skill 已启用并注入当前任务。

## 下一位 Agent 的首要任务：真实 Computer Use 验证

先请用户在 Codex/ChatGPT 桌面端完成以下 UI 操作：

1. 打开 **Plugins > Computer Use**。
2. 如出现安装按钮，安装 Computer Use 插件。
3. 打开它的 **server** 与 **skill** 开关，选择 **Try now**。
4. 在 **Settings > Computer Use** 确认 Windows Computer Use 已允许，并保持目标窗口在前台。
5. 重新打开一个任务，明确要求使用 `@Computer` 或 Computer Use，而不是内置 Browser。

随后让原生 Computer Use 在桌面前台慢速移动鼠标到桌宠四周、停留并点击一个无副作用位置。观察 Look：

- 若触发：问题解决。将此限制写入 README：Look 仅在原生 Computer Use 游标事件中触发，普通鼠标与内置浏览器 CUA 不触发。
- 若仍不触发：继续检查桌宠覆盖层是否实际接收到 `avatar-overlay-computer-use-cursor-changed`；不要重画 Look 素材，也不要把 Browser CUA 测试当作失败证据。

官方手册的要点：Windows 上 Computer Use 必须运行在可见的活动桌面；需要安装并启用 Computer Use 插件。手册也只说明宠物能跟随任务状态，没有承诺普通鼠标会驱动 Look。

## 图集状态映射

| 行 | 状态 | 帧数 | 当前状态 |
| --- | --- | ---: | --- |
| 0 | idle | 6 | 已安装 |
| 1 | running-right | 8 | 已由 running-left 逐帧镜像修复 |
| 2 | running-left | 8 | 用户确认正确，保持不动 |
| 3 | waving | 4 | 已安装 |
| 4 | jumping | 5 | 已安装 |
| 5 | failed | 8 | 已安装 |
| 6 | waiting | 6 | 已安装 |
| 7 | running | 6 | 已安装 |
| 8 | review | 6 | 已安装 |
| 9 | Look `000–157.5` | 8 | 已安装，待运行时事件验证 |
| 10 | Look `180–337.5` | 8 | 已安装，待运行时事件验证 |

## 验证命令

使用桌面线程的 bundled Python，不要使用裸 `python`：

```powershell
$py = 'C:\Users\14841\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$validator = 'C:\Users\14841\.codex\skills\hatch-pet\scripts\validate_atlas.py'
& $py $validator '.\pet\changli\spritesheet.webp' --json-out '.\workflow\qa\validation-release.json' --require-v2
```

当前三份图集都已验证通过：

- 工作区成品：`制作工作区\常离-v2桌宠\final\spritesheet-extended.webp`
- 仓库发布包：`pet\changli\spritesheet.webp`
- 已安装包：`C:\Users\14841\.codex\pets\changli\spritesheet.webp`

每次修改发布包后都应：

1. 验证仓库与已安装包。
2. 比较两者 SHA-256，确保完全一致。
3. 在 Codex 设置页 Refresh Pets，必要时 tuck/wake 一次或重启桌宠覆盖层。
4. 再做真实 Computer Use 测试。

## 注意事项

## 2026-07-20：Look 与 Windows Computer Use 的已确认阻塞

本节取代上文「未证实」的运行时判断：问题已经可以拆分为两个独立的 Codex Desktop Windows 缺陷，而不是图集、`pet.json` 或 16 个 Look 素材的问题。

1. GitHub [#33224](https://github.com/openai/codex/issues/33224) 记录了同一个 v2 Pet Look 缺陷：物理鼠标位置没有被送进 Look 所监听的 `avatar-overlay-computer-use-cursor-changed` 事件；只有原生 Computer Use 的虚拟光标会走这条事件链。因此，普通鼠标和内置浏览器的 Browser Use/CUA 控制都不会驱动 Look。
2. GitHub [#25271](https://github.com/openai/codex/issues/25271) 记录了 Windows 上原生 Computer Use 控制 Chromium 浏览器的另一条阻塞：即使 Chrome 已打开，也会在「无法以足够置信度确定当前浏览器 URL」的安全检查处停止。这与本项目实测的报错逐字一致，故浏览器内无法启动原生 CU 虚拟光标，也就无法将它作为 #33224 的临时 Look 验证手段。
3. 本轮已在全新打开的 Windows Calculator 窗口执行原生 Computer Use 的四次坐标点击测试，验证其可以绕过 Chrome URL 阻塞并正常注入原生鼠标输入。观察 Look 是否变化仍需由用户在桌面端确认；该测试没有改动项目文件或浏览器数据。

处置结论：不要重画 Look 素材，也不要尝试通过 `pet.json`、额外 sprites 或脚本为原生桌宠接入鼠标事件。当前可用策略是：浏览器操作继续使用 Browser Use/Chrome 控制；Look 功能等待 #33224 修复。原生 Computer Use 在非浏览器应用中可作验证路径，但浏览器内仍受 #25271 阻塞。

### 更正：计算器测试并未验证 Look

上文「计算器四次坐标点击」只能证明 `computer-use` 插件可向 Windows 应用注入普通鼠标输入，不能证明它向桌宠覆盖层发送了 Look 事件。该插件技能明确说明其底层使用 SendInput/UI Automation；而当前桌宠渲染器只在收到 app 专用消息 `avatar-overlay-computer-use-cursor-changed` 时才计算 Look。实测中桌宠仍保持 idle，故本版本的本地 Computer Use 插件没有把该消息桥接给覆盖层。该事件没有公开的 `pet.json`、插件或脚本入口；不能靠增加 sprites 启用。

因此 #33224 还应被理解为：物理鼠标肯定不驱动 Look，且报告者观察到的「Computer Use 虚拟光标」路径与本地 `sky`/SendInput 自动化并非已验证为同一种运行时路径。当前项目没有可靠的、用户可配置的 Look 触发方法。

### 2026-07-21：左右奔跑素材与运行时映射复核

- 已安装图集、仓库图集、工作区成品 SHA-256 完全一致：`64FD97F3624458EC6D22A2892CD129F187019BBC305C2DBC6C44504AAED2A97A`。
- 逐帧验证：第 1 行每格均为第 2 行同序帧的水平镜像。视觉上第 1 行朝屏幕右方，第 2 行朝屏幕左方。
- 当前 Codex 覆盖层代码在拖拽横向位移 `>= 4` 时选择 `running-right`，位移 `<= -4` 时选择 `running-left`；其动画表映射为 `running-right -> row 1`、`running-left -> row 2`。
- 因而若用户向右拖拽仍看到左向动作，排查方向应是覆盖层没有重新载入当前图集或选中的不是 `changli` 包，而不是再次镜像素材。官方 Pets 文档要求新增/更新自定义宠物后在 Settings > Pets 使用 Refresh 再选择宠物；实际验证时还应 Tuck Away/Wake 一次，必要时完全退出并重开桌面应用。

- `imagegen-jobs.json` 是历史制作记录，含有 Windows 非 ASCII 路径转义损坏，PowerShell `ConvertFrom-Json` 不能可靠解析；不要把它当作下一轮自动化的唯一输入。
- 用户接受“流畅、无明显问题”的实用质量标准；不要为细小的审美差异重做整套图集。
- 保留现有版权声明：角色与游戏相关权利归库洛游戏所有；项目为非官方、非商业同人项目。参见 `NOTICE.md` 与 README。
- 不要实现独立桌宠或离火状态系统；用户已明确决定继续基于 Codex 原生桌宠。
