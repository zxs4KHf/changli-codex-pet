# Codex 桌宠成熟制作与修复流程

本项目按 `hatch-pet` v2 合约生产：8 列 × 11 行、每格 192×208、最终图集 1536×2288，并设置 `spriteVersionNumber: 2`。

## 核心原则

1. 先固定角色身份参考、动作语义、色键和版本，再生成动作。
2. 九组标准动作按完整动作行生成或返修，不能拿其他状态凑帧。
3. 方向动画先确认 `000/090/180/270` 四个基准，再生成两个完整的八帧方向行；不能拼补单个方向格。
4. 色键必须远离角色固有配色。长离含有发饰中的绿色细节，未来生成优先使用纯蓝 `#0000FF`，避免把真实绿色误当背景。
5. 去色键只针对轮廓污染：保持 Alpha 不变，用邻近角色色重建受污染的边缘 RGB。禁止全局删除绿色像素。
6. 每个最终成品只允许一次确定性的边缘处理；报告和图集验证通过后，不再重复去色。
7. 发布前必须保留联系表、逐行动画、16 方向图、三票盲测、连续性报告和安装版校验。

## 候选隔离与 A/B

- 稳定发布图集冻结不动；新行先进入独立候选目录，只有联系表、GIF 和普通显示尺寸 A/B 全面胜出才替换。
- 结构检查通过不等于视觉通过。脸型、眼睛大小、头身比、线条软硬、饱和度、服装简化或发型变化都属于身份/风格硬失败。
- 组件提取会把大尺寸生成姿态缩放到单元格安全区。需要对齐既有图集时，可以按稳定版同状态的中位高度和脚底基线做确定性归一化；但归一化只能修几何，不能掩盖身份或画风漂移。
- 在隔离测试目录运行 `extract_strip_frames.py` 时，必须复制 `pet_request.json` 或显式传入 `--chroma-key`。缺失时脚本会回退到绿色键，导致蓝幕素材被误判。
- 当前内置生成通道一次最多附带五张参考图。优先顺序是：布局 guide、canonical base、已批准标准联系表、同状态/idle 稳定行，以及该阶段的批准依赖（四基准或上一条 Look 行）。

## 图像通道恢复

- 内置图像通道优先；模型冷却时不要反复重试同一根因。
- CLI 备用只使用 imagegen 自带 `scripts/image_gen.py`，要求本机有效的 `OPENAI_API_KEY`。密钥不得写进命令、文档、日志或仓库。
- 如果本机代理导致 TLS 握手超时，先做不带密钥的直连探测。仅在单次 CLI 子进程内清空代理变量，不修改系统代理；确认网络后再发正式请求。
- CLI、内置通道或素材额度阻塞时，保留完整恢复点并停止在依赖边界；禁止用单格拼补、仿射旋转或程序变形伪造完整 Look 行。

## 候选恢复体检

候选目录可以位于任意盘符。恢复前使用 bundled Python 运行只读 doctor：

```powershell
python .\workflow\tools\candidate_resume_doctor.py `
  --run-dir 'D:\Codex桌宠\changli-v1.1-candidate' `
  --json-out 'D:\Codex桌宠\changli-v1.1-candidate\qa\candidate-checkpoint.json' `
  --expect-next look-row-9
```

报告只记录候选内相对路径、下一可执行任务、提示词和参考图角色、尺寸及 SHA-256；不会复制、生成、去色或修改图集。换盘符或用户名后重新运行即可重建 checkpoint。任何外部路径、非标准依赖边、缺失输入、错误行尺寸、错误四基准顺序或超过当前参考图限制都会阻止继续。

`look-row-10` 只有在 row 9 的注册图、注册比例、最终格边缘报告、八方向语义报告和连续性报告全部通过后才会解锁；仅把 `imagegen-jobs.json` 的 row 9 改成 complete 不足以跨越此门禁。

## 确定性工具安全规则

- `normalize_standard_scale.py` 默认使用 `--output-root` 事务写入新帧。它会先预检整批素材；原地模式必须传入工作区外的 `--backup-root`，写入失败会从不可变备份恢复整批源帧。
- `mirror_running_left_to_right.py` 默认要求 `--output`。原地修复必须同时提供 `--in-place --backup`，并建议使用 `--expected-source-sha256` 锁定输入。
- 两个工具都拒绝越界、错误尺寸、错误源哈希和隐式覆盖，并写 before/after 哈希报告。

## Codex 运行时需求边界

- 官方 Pets 文档定义了 Running、Needs input、Ready、Blocked 四种活动状态，并说明选择宠物只改变外观，不改变任务执行方式：<https://learn.chatgpt.com/docs/pets?surface=app>。
- 官方文档目前只明确说明 macOS 的 Computer Use 画中画窗口可以附着到已唤醒的宠物；没有承诺 Windows、普通鼠标或内置浏览器光标会驱动 16 个 Look 帧。
- 官方 Computer Use 文档说明 Windows 在活动桌面前台运行并会移动指针：<https://learn.chatgpt.com/docs/computer-use>。这不等同于桌宠内部 Look 事件契约。
- 因此素材验收与运行时触发验收必须分开：16 帧可以通过图集 QA，但是否播放属于 Codex 应用运行时测试，不能靠增加 sprites 或改 `pet.json` 推断成功。

## 本次长离修复

- 以已完成右跑镜像修复的 v2 图集作为输入，不改变帧数、Alpha、单元格位置或动作顺序。
- 对最终轮廓执行一次修复性去绿边处理，共修改 19,614 个边缘 RGB 像素，其中 18,437 个完成颜色去污染。
- Alpha 掩膜与修复前逐像素相同，完全透明区域的隐藏 RGB 为 0。
- `running-right` 的八格仍是 `running-left` 同序帧的精确水平镜像。
- 三份隔离方向盲测确认四个基准方向通过；接近正面或侧面的部分中间角度保留为非阻塞警告。

## 发布门槛

以下项目必须同时通过：

- `validate_atlas.py --require-v2`：零错误、零警告；
- 去色报告 `ok: true` 且 `alpha_preserved: true`；
- 九行动作结构检查无错误；
- 四个方向基准盲测通过；
- 联系表和逐行动画无身份漂移、裁切、方向反转或明显跳帧；
- 仓库发布图集、本机安装图集 SHA-256 完全一致。

仓库自带的聚合校验命令：

```powershell
python -m pip install -r requirements-dev.txt
python workflow/tools/validate_release.py
```

它不依赖本机安装 `hatch-pet`，因此贡献者和 GitHub Actions 都能复现最关键的发布门槛。

## 未来返修策略

当前方向行有三项轻微连续性提醒：`045→067.5` 中心移动偏大、`157.5` 存在透明行候选、`337.5→000` 首尾尺寸变化偏大。它们未造成基准方向错误或可见反转。

若以后重新生成，必须整行重做 row 9 或 row 10，并重新执行三票盲测；不能直接修改最终图集中的单格。新的生成素材应使用纯蓝色键，避免再次引入绿色边缘。

当前 v1.1 的详细恢复点见 `docs/V1.1_CANDIDATE_STATUS.md`。
