# 生平短片工厂 · 使用说明

> 输入一个人物名（或企业名），输出一条 1080×1920 竖屏生平短片；也支持「100 种人生体验」这类纯文字卡片的清单视频。
> 剧本 / 生图 / 生视频由 WorkBuddy 完成，配音 / 字幕 / 合成在本地完成。

**文档约定**：本项目只维护两份文档 —— 本文件（使用说明）与 [CHANGELOG.md](CHANGELOG.md)（变更记录）。
新增或改动任何东西，说明写进 README，变更写进 CHANGELOG，不另外新建文档。

---

## 一、快速开始

```bash
cd /Users/lingmf/Downloads/workbuddy/bio-video-studio
./run.sh
```

脚本会：检查虚拟环境 → 检查并安装依赖（fastapi / uvicorn / edge-tts / imageio-ffmpeg）→ 启动服务并自动打开浏览器。

| 启动方式 | 命令 | 适用场景 |
|----------|------|----------|
| 前台启动 | `./run.sh` | 手动用一下，关掉终端即停 |
| 守护启动 | `<PY> start_daemon.py` | 长期挂着 / 交给 WorkBuddy 调用（`--no-browser`，日志落 `logs/server.log`） |

`<PY>` = `/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python`

**端口**：默认 **7799**（7788 已被其它项目占用），可用 `STUDIO_PORT=xxxx` 覆盖。
守护启动会打印 `pid=<x> port=<y> ready=True`，**以打印出来的 port 为准**。

健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:7799/api/health
# {"ok":true,"ffmpeg":true,"ffmpeg_path":"...","pending_tasks":1}
```

---

## 二、五步出片

网页上有五个步骤按钮，前三个下单给 WorkBuddy，后两个本地执行：

| # | 步骤 | 谁来做 | 说明 |
|---|------|--------|------|
| 1 | 写分镜剧本 | WorkBuddy | 8–12 镜，每镜含旁白 + 生图提示词 + 运镜提示词 |
| 2 | 批量生图 | WorkBuddy | 1024×1536，存 `images/01.png …` |
| 3 | 批量生视频 | WorkBuddy | 按「生视频方式」走本地渲染或视频大模型 |
| 4 | 一键配音 | 本地 | edge-tts 生成旁白 MP3 + 自动生成 ASS 字幕（**需联网**） |
| 5 | 渲染成片 | 本地 | 合成片头、烧录字幕、混 BGM，输出 MP4 + 封面 |

操作路径：

1. 打开 http://127.0.0.1:7799 ，输入人物名 →「新建短片」
2. 依次点 1 / 2 / 3，每点一次页面会出现提示卡 → 点「复制提示词」贴给 WorkBuddy 执行
3. WorkBuddy 跑完素材后，回到网页点 4「一键配音」、5「渲染成片」
4. 成片在 `projects/<人物>/output/`，页面可直接预览 / 下载 / 打开所在文件夹

> 中途想重做某一条：分镜卡片上有重置按钮，清掉素材后重新点对应步骤即可。

### 生视频方式（第 3 步，设置行的红色下拉框）

| 选项 | 单条积分 | 12 条全片合计 | 适用 |
|------|---------|--------------|------|
| HyperFrames 本地渲染（默认 `hf`） | 0 | **0** | 原生 30fps，时长与配音精确对齐；本地 ffmpeg 做出推近 / 拉远 / 缓慢漂移（带缓动），适合绝大多数运镜 |
| 视频大模型（`ai`） | 50–100 | **600–1200** | 需要真实物理运动（车在开、人在走、航拍俯冲）才值得用 |
| 混合（`mix`） | 仅大模型那几条计费 | **通常 0–300** | 自动挑镜：只把「真实物理运动」镜头（开车 / 行走 / 航拍…）丢给模型，其余本地渲染 |

计费口径不同：`ai` 按条计费；`mix` 是整片合计，且**由程序按运镜提示词自动判断哪些镜需要模型**（不是手动挑 4–5 条）。
选好的路线会随任务入队；排队提示卡会显示**预估积分**，复制给 WorkBuddy 的提示词也会明确写出"第 X 镜用模型 / 其余本地，不要消耗积分"，避免模型擅自把全部镜头都生一遍。

> 想彻底 0 积分：直接用 `hf`。本地渲染现在已不是单调推近，而是按每镜运镜提示词做推 / 拉 / 漂移 + 缓动，画面足够"活"。
> 只有确实要"真东西在动"的镜头（车流、人群、航拍俯冲）才切 `mix` 或 `ai`。

---

## 三、其它设置

| 设置项 | 位置 | 说明 |
|--------|------|------|
| **画面（横屏/竖屏）** | 设置行第一个「画面」 | **项目级**，决定合成画布、字幕字号与边距。<br>`竖屏 9:16`＝1080×1920（默认，发短视频）；`横屏 16:9`＝1920×1080（企业宣传片 / 大屏 / 手机横屏）。<br>改完点「保存设置」；横屏成片文件名自动带 `_16x9`，不会覆盖竖屏成片 |
| **字幕（开/关）** | 设置行「字幕」 | **项目级**。`启用`＝把旁白文案生成 ASS 并烧进画面（默认）；`不启用`＝**透传视频原画面**，适合素材已自带字幕、或不需要字幕的场景，避免双层字幕叠字。关掉后 `subs/*.ass` 不再生成/使用 |
| **旁白音色 `不使用`** | 「旁白音色」第一项 | 画面自带配音（AI 视频自带说话声）时选它：**跳过 TTS**，合成时保留每条视频的原声音轨；此时镜头时长优先取分镜 `duration`（剧本写的 8/10/14 秒），不再按旁白字数估算 |
| 音色 | 设置行「旁白音色」 | 默认 `zh-CN-YunjianNeural`（浑厚男声）。另有 Yunxi / Xiaoxiao / Yunyang 等 |
| 语速 | 设置行 | `+0%` 起调。**换音色或语速会清空已配的旁白音频**（顺便重配，避免一条片子混两种音色） |
| 底部裁切 | 设置行「底部裁切」 | 先裁掉画面底部 N 像素（去固定水印条）再铺满画布；`0` = 不裁。注意：**会跳动/半透明的平台水印裁不干净**，见第十一节 |
| BGM | 「上传 BGM」 | 支持 mp3/wav/m4a/aac；音量滑杆默认 0.18 |
| 保存设置 | 设置行末尾 | 改完记得点，否则不落库 |

> 画面比例只影响**合成**。出图/出视频阶段要按同一比例出素材（横屏就出 16:9 素材），否则会被裁成中间一块。

改完设置后若页面没变化，**强制刷新**（CSS/JS 有版本号缓存）。

---

## 四、命令行速查

`studio.py` 是给 WorkBuddy 驱动流水线用的，手动排查也方便：

```bash
<PY> studio.py pending                       # 列出待处理任务（可按 --type script/images/videos 过滤）
<PY> studio.py claim <task_id>               # 领取任务（标记 running）
<PY> studio.py set-script <pid> -f s.json    # 写入剧本（自动把 script 任务标记 done）
<PY> studio.py attach <pid> -i 1 --image X.png    # 挂载图片到第 1 镜
<PY> studio.py attach <pid> -i 1 --video Y.mp4    # 挂载视频
<PY> studio.py attach <pid> --bgm b.mp3      # 挂 BGM
<PY> studio.py done <task_id>                # 完成任务
<PY> studio.py status <pid>                  # 查看各分镜素材齐不齐
<PY> studio.py render <pid>                  # 命令行直接渲染（--no-title / --no-bgm）
<PY> studio.py probe <file>                  # 查视频时长
```

`videos` 类任务用 `pending` 查时会多带一个顶层 `route` 字段，即生视频路线。

---

## 五、目录结构

```
bio-video-studio/
  app.py              # Web 服务（FastAPI）
  studio.py           # 命令行工具
  start_daemon.py     # 守护启动
  run.sh / run.bat    # 一键启动（macOS / Windows）
  core/               # config 配置 · store 存储 · jobs 任务 · tts 配音 · compose 合成 · render 渲染
  web/                # 前端（原生 HTML/CSS/JS）
  tasks/queue.jsonl   # 任务队列
  projects/<人物>/
    project.json      # 元数据 + 分镜剧本
    script.json       # 剧本源文件
    images/ videos/ audio/ subs/ clips/
    output/           # 最终成片 + 封面
```

---

## 六、技术栈

- 后端：Python 3.13 + FastAPI（本机专属虚拟环境 `biostudio`）
- 任务队列：JSONL 文件队列（`tasks/queue.jsonl`）
- 视频合成：ffmpeg（imageio-ffmpeg 自动提供）
- 配音：edge-tts（微软 Edge 语音，免费但需联网）
- 前端：原生 HTML / CSS / JavaScript，无构建步骤
- 输出规格：1080×1920 / 30fps / H.264 / AAC

---

## 九、「人生副本」单集系列（今日副本风格，0 积分）

适合「今日副本」「人生副本」这类**每期一个主题**的短视频：暗色游戏化竖屏 + 大字标题 + 剧情卡/金句卡/结束卡 + 账号署名。同样走 **edge-tts + HyperFrames 本地渲染 + ffmpeg 合成**，全程 0 积分。

### 1. 脚本格式

```json
{
  "title": "县城月薪4000，却活的像富二代",
  "series": "今日副本",
  "episode": "EP.01",
  "author": "二狗君",
  "voice": "zh-CN-YunjianNeural",
  "bgm": "/Users/lingmf/Music/bgm.mp3",
  "bgm_volume": 0.18,
  "scenes": [
    {"type": "cover", "heading": "今日副本", "text": "县城月薪4000\n却活的像富二代", "sub": "今日解锁：小县城的财务自由密码", "image_query": "small chinese county town street"},
    {"type": "scene", "heading": "开局", "text": "父母在体制内，房车全款，工资只是零花钱。", "sub": "没有房贷车贷，4000 也能活出 4 万松弛感", "image_query": "Chinese family apartment"},
    {"type": "quote", "heading": "金句", "text": "在大城市叫生存，\n在小县城才叫生活。", "emoji": "🌆"},
    {"type": "scene", "heading": "日常", "text": "早上不慌不忙吃碗牛肉面，下班和朋友撸串，周末开车去周边山野露营。", "sub": "时间便宜，所以愿意浪费在喜欢的事上", "image_query": "beef noodle barbecue camping"},
    {"type": "end", "heading": "副本结算", "text": "今日体验已解锁，\n明天你想活成谁？", "sub": "关注我，每天体验一种人生", "emoji": "🏆"}
  ]
}
```

- `type`: `cover` / `scene` / `quote` / `end`
- `text` 可用 `\n` 换行；`sub` 是小字副文案
- `image_query` 可选：英文关键词，自动生成器会到 **Wikimedia Commons** 拉一张 CC 真实照片（0 积分，适合剧情配图）
- `image` 可选：本地路径 / URL / SVG 字符串，透传进模板（优先级最高）
- `emoji` 可选：放一个 emoji 作为该镜的视觉（第三优先级；0 积分，适合快速配图）
- 都不填时，按类型显示内置 SVG：封面传送门、剧情风景、金句引号、结算奖章

示例：
```json
{"type": "scene", "heading": "日常", "text": "早上不慌不忙吃碗牛肉面...", "sub": "...", "image_query": "beef noodle soup"}
```

### 2. 生成命令

```bash
<PY> scripts/gen_life_copy.py                              # 用内置示例脚本跑一条样片（约 4-5 分钟）
<PY> scripts/gen_life_copy.py my_copy.json                  # 自定义脚本
<PY> scripts/gen_life_copy.py my_copy.json --limit-scenes 3  # 只跑前 3 个 scene 试看
<PY> scripts/gen_life_copy.py my_copy.json --no-fetch       # 不联网拉图，只用 emoji / 内置 SVG
<PY> scripts/gen_life_copy.py my_copy.json --bgm ~/Music/bgm.mp3 --voice zh-CN-XiaoxiaoNeural
```

输出：`projects/<项目>/output/<标题>.mp4`。

> 内置示例脚本已扩到 18 个 scene（封面 + 14 段剧情/金句 + 结算），每段配一张 Wikimedia CC 照片，总长约 4 分半。想要更长，继续加 scene 或把每段文案写长即可。

### 3. 自定义视觉

模板在 `templates/life_copy/index.html`：
- 1080×1920 竖屏，暗色渐变背景，入场动画由 `window.__update(t)` 控制。
- `window.__SCENE__` 注入当前 scene 数据，文本用 `textContent` 注入避免引号破坏。
- 配图优先级：`image`（路径/URL/SVG） > `image_query`（Wikimedia CC 照片） > `emoji`（一个 emoji） > 内置 SVG（按 scene type）。
- 内置 SVG 已内置 4 套：封面传送门光晕 + 角色、剧情风景、金句引号、结算奖章。
- 免费图源实现见 `scripts/fetch_images.py`：优先 Wikimedia Commons，失败退化为 Picsum 随机图。

---

## 十、「睡觉听历史」长音频历史科普系列（视频号音频优先，0 积分）

适合视频号「睡前听历史 / 通史讲解」专栏：每条 **20–30 分钟平缓旁白**，用户可「看视频」也可「锁屏听音」。视频只是发布壳，**音频才是核心**——主打「放松身心、慢慢了解旧时光，不用刻意背诵记忆」。

标签建议：`#睡觉听历史 #历史科普 #王朝简史 #历史人物 #睡前听历史 #通史讲解`

### 1. 脚本格式

```json
{
  "series": "睡觉听历史",
  "episode": "EP.01",
  "title": "唐朝：从贞观之治到安史之乱",
  "subject": "一场盛世的升起与落幕",
  "voice": "zh-CN-YunjianNeural",
  "rate": "-10%",
  "bgm": "", "bgm_volume": 0.10,
  "image": "",
  "paragraphs": [
    "欢迎来到《睡觉听历史》……",
    {"heading": "贞观", "text": "……"}
  ]
}
```

- `rate` 建议 `-10%`～`-20%`，越慢越适合助眠；`voice` 可换 Xiaoxiao / Yunxi 等。
- `paragraphs` 为数组，元素可为字符串（整段）或 `{"heading","text"}`（带小标题，模板暂未渲染小标题，仅作文案分段）。
- `bgm` 留空则不加背景乐；填 mp3 绝对路径会按 `bgm_volume` 混入。
- `image` 留空用内置暗色氛围；填图片绝对路径会做缓慢 Ken Burns 漂移。

### 2. 生成命令

```bash
<PY> scripts/gen_sleep_history.py                              # 用内置示例（唐朝简史，86 段，实测约 28 分钟）
<PY> scripts/gen_sleep_history.py my.json                     # 自定义脚本
<PY> scripts/gen_sleep_history.py my.json --limit-paras 3     # 只跑前 3 段试看
<PY> scripts/gen_sleep_history.py my.json --no-bgm            # 不加背景音乐
<PY> scripts/gen_sleep_history.py my.json --bgm ~/Music/calm.mp3 --voice zh-CN-XiaoxiaoNeural --rate -15%
```

输出：`projects/<标题>/output/<标题>.mp3`（睡前听音主交付，锁屏可听）+ `<标题>.mp4`（视频号发布壳）+ `cover.jpg`。

### 3. 成本

| 环节 | 工具 | 积分 |
|------|------|------|
| 旁白 | edge-tts | 0 |
| 氛围视频壳 | HyperFrames（puppeteer 渲染暗色循环） | 0 |
| 合成 | ffmpeg 本地 | 0 |

全程 0 积分，只有 CPU 渲染与联网 TTS 的时间成本。

### 4. 结构与模板

- 模板 `templates/sleep_history/index.html`：暗色舒缓氛围，缓慢光晕漂移 + 标题/系列名/副标题，可选底图 Ken Burns；`window.__update(t)` 由外部每帧喂时间。
- 渲染器 `scripts/sleep_render.js`：puppeteer 截一段 12s 无缝循环氛围，ffmpeg 铺满音频时长。
- 生成器 `scripts/gen_sleep_history.py`：旁白按段落/句子分块逐块 edge-tts（带重试 + 0 字节校验，规避偶发空响应）→ 拼 MP3 → 循环铺满 → 混音 → 封面。

### 5. 发布建议

- 视频号发 MP4（锁屏后音频继续播，满足「听历史」需求）；把 MP3 同步到播客 / 音频平台做「纯听」分发。
- 封面用 `cover.jpg`，标题区写明「EP.0X 王朝/人物名」。
- 长音频建议在段间留 1–2s 静音便于入睡；当前生成器按段落自然衔接，可在文案里加空段调节。

### 6. 系列批量（通用工厂）

做一个多集专栏（如「大明十六帝」6 卷、宋朝、世界史），不要一集一集手动跑，用系列目录 + 批跑器：

```
series/<系列名>/
  manifest.json    # 系列配置：默认音色 / 语速 / BGM + 集数清单
  ep01.json ...    # 每集脚本（同 gen_sleep_history 的格式）
  .state.json      # 自动生成，记录每集状态（成功/失败/用时/产物路径）
```

```bash
<PY> scripts/run_series.py series/ming-emperors --estimate    # 只估算字数与时长，不渲染
<PY> scripts/run_series.py series/ming-emperors                # 全量串行生成（已完成的自动跳过）
<PY> scripts/run_series.py series/ming-emperors --only EP.02 EP.04
<PY> scripts/run_series.py series/ming-emperors --from EP.03
<PY> scripts/run_series.py series/ming-emperors --force        # 已有成片也重跑
<PY> scripts/run_series.py series/ming-emperors --limit-paras 3 # 每集只跑前 3 段，试听结构
```

**长时间跑必须用守护启动**（6 集约 1.5–2 小时；直接 `nohup &` 会被当前会话回收）：

```bash
<PY> start_series.py series/ming-emperors
# 日志：logs/series-<slug>.log   状态：series/<slug>/.state.json
```

**可视化界面**：打开 <http://127.0.0.1:7799/series>（或主页右上角「系列工厂 →」）

- 左侧列出所有系列，显示集数、总时长、完成进度；右侧是每集的标题、字数、预估时长、状态。
- 「▶ 开始生成」整批续跑（已完成的自动跳过），「生成这集」只跑单集，「强制重跑」覆盖已有成片。
- 「预览」直接播放成片 MP4，可下载 MP3；「目录」在访达中打开产物文件夹。
- 「＋ 新建系列」填系列名/音色/语速，自动生成 `manifest.json` + `ep01.json` 模板。
- 页面每 5 秒自动刷新，运行时下方显示实时日志。

**新建一个系列**：把 `series/_template/` 整个复制成 `series/<新名字>/`，改 `manifest.json` 的 `slug / series / topic / episodes`，再按集改 `ep0X.json` 的 `title / episode / subject / paragraphs` 即可。

字数与时长的换算（实测）：
| 语速 | 字/分钟 | 20 分钟约需 | 28 分钟约需 |
|------|---------|------------|------------|
| `-28%`（标准平缓） | 200 | 4000 字 | 5500 字 |
| `-38%` | 172 | 3450 字 | 4800 字 |
| `-50%`（助眠慢速，当前大明系列） | 136 | 2720 字 | 3800 字 |

注意：
- `--rate` 传负值时必须写成 `--rate=-50%`（`--rate -50%` 会被 argparse 当成选项，批跑器已统一用等号形式）。
- 批量务必串行，edge-tts 并发会返回 429；批跑器默认集间停 5 秒。
- 生成器对音频分块有缓存，中断后重跑只补没合成的块。

### 7. 配套图片（0 积分，可选）

默认成片是暗色氛围循环。如果想配真实图片，可以在已有成片上再出一版「配图版」：

```bash
<PY> scripts/add_images.py --series series/ming-emperors --ep EP.01
<PY> scripts/add_images.py --series series/ming-emperors --ep EP.01 --sections 12 --zoom 0.06
<PY> scripts/add_images.py --series series/ming-emperors --ep EP.01 --limit-sections 2  # 只做前 2 段试看
```

- **图源全部免费**：先取 Wikimedia Commons 的 CC 照片，失败退 Picsum 随机图；0 积分，只有网络 + CPU 成本。
- **不重新配音**：复用已有 MP3，只生成画面再合流，输出 `<标题>_配图.mp4` + `cover_配图.jpg`。
- 配图关键词写在每集 JSON 里：
  - `"image_queries": ["Ming dynasty painting", ...]`：平均分配到各段；
  - `"images": [{"query": "Forbidden City", "paras": [0, 6]}, ...]`：精确指定段落区间。
- 每段做缓慢推近 / 拉远 / 横移（Ken Burns），24fps；单集渲染时间约等于音频时长（20 分钟左右）。
- **页面操作**：系列页每集有「配图」按钮，点一下后台生成，完成后按钮变成「配图版」可直接预览；批量补用 `scripts/image_pass.py --series ...`。
- **标题换行**：每集 JSON 的 `title` 用于项目目录/文件名，封面显示用 `display_title`（支持 `\n` 手动换行），两者解耦，避免长标题被裁切或断在词中间。

---

## 七、常见问题

| 现象 | 原因 / 处理 |
|------|------------|
| 改了前端但页面没变 | 必须**重启服务**；重启前先 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 找到旧进程 kill（`pkill -f app.py` 在本机杀不掉，新进程会报端口占用却仍打印 `ready=True`，容易误判成"改了没生效"）。改 CSS 还需 bump 一次 `style.css?v=N` |
| curl 本地接口返回 502 | 会话代理拦了 localhost，curl 加 `--noproxy '*'` |
| 配音失败 / 卡住 | edge-tts 需联网；守护启动已剥离会话级代理，前台启动若环境有 `HTTP_PROXY` 需手动 `unset` |
| ffmpeg 报找不到字体 | 已做跨平台探测（macOS 用 Hiragino Sans GB，Windows 用微软雅黑，Linux 用 Noto CJK），换机器无需改配置 |
| 服务起在别的端口 | 7799 被占用时以 `start_daemon.py` 打印的 port 为准 |
| 成片有慢放 / 幻灯片感 | 视频素材时长短于配音导致被拉伸。走 `hf` 路线按「配音时长 + 0.6s」渲染可避免 |

---

## 八、100 种人生体验 / 体验清单类视频（HyperFrames 0 积分）

适合「100 件小事」「人生必做清单」「治愈系文案」这类**静止图文 + 朗读**的爆款视频。全程不调用 ImageGen / 视频大模型，**纯本地 HyperFrames（puppeteer 截 HTML）+ edge-tts 配音，0 积分**，只有 CPU 渲染时间。

### 1. 清单格式

```json
{
  "title": "100种人生体验",
  "voice": "zh-CN-YunjianNeural",
  "bgm": "/Users/lingmf/Music/relax.mp3",
  "bgm_volume": 0.16,
  "experiences": [
    {"category": "自然", "text": "在山顶看一次日出"},
    {"category": "旅行", "text": "一个人去一座陌生城市"},
    {"category": "美食", "text": "学做一道外婆的拿手菜"}
  ]
}
```

- `experiences` 里也可以直接写字符串（默认 category 为空）。
- 项目已内置 `templates/experience/sample_100.json`，可直接跑。

### 2. 生成命令

```bash
<PY> scripts/gen_experience.py                              # 用内置 100 条全量生成
<PY> scripts/gen_experience.py my_list.json                 # 自定义清单
<PY> scripts/gen_experience.py --limit 5                    # 只跑前 5 条试看
<PY> scripts/gen_experience.py --bgm ~/Music/bgm.mp3        # 加背景音乐
<PY> scripts/gen_experience.py --voice zh-CN-XiaoxiaoNeural # 换女声
```

输出：`projects/<项目>/output/<标题>.mp4`，同时生成 `cover.jpg`。

### 3. 成本与速度

| 环节 | 工具 | 积分 |
|------|------|------|
| 配音 | edge-tts | 0 |
| 图/视频 | HyperFrames（puppeteer + HTML/CSS） | 0 |
| 字幕 | 文案直接印在卡片上，不额外烧录 | 0 |
| 合成 | ffmpeg 本地 | 0 |

100 条总长约 6–8 分钟；渲染速度取决于 CPU，puppeteer 截图约 100–150 秒/百条（入场 24 帧 + 定格冻结优化）。

### 4. 自定义视觉

视觉全部在 `templates/experience/index.html` 里：
- 1080×1920 竖屏卡片，CSS 渐变背景按 `category` 自动配色。
- 可改字体、排版、入场动画；`window.__update(t)` 仍由外部每帧喂时间，不要写 `setInterval`/`Date.now`。
- 生成器只替换 `{{IDX}} / {{TOTAL}} / {{CATEGORY}} / {{TEXT}} / {{DUR}}` 五个 token。


---

## 十一、IP 角色动画短片（企业文化系列，横屏 16:9）

适合用**固定 IP 形象**（TT虎）做企业文化、内训、合规宣导这类 1–3 分钟**横屏**动画短片。和前面几条链路最大的不同：**画面用图生视频做真运动，不再用静帧推拉**——这是达到"正式产品"质感的关键。

### 1. 规格

| 项 | 值 |
|----|-----|
| 成片 | 1920×1080 / 24fps / H.264 + AAC 48kHz |
| 单镜 | 5–7 秒；2 分钟 ≈ 18–24 镜（不是 12 镜） |
| 出图 | 1536×1024（16:9），image-to-image 参考 `可用素材/` 官方 3D 素材 |
| 出视频 | VideoGen 图生视频，1080P，固定机位 |
| 配音 | **MiniMax `speech-2.5-hd-preview`**，`voice_id=audiobook_male_1`（有声书男声，讲故事语调），speed 0.98；key 读 `~/.ops-bot/reason.json` 的 `api_key` |
| 字幕 | ASS 烧录，**单行轮播**（不占两排），字号 48，`MarginV 128`；断行：句号满 8 字即断、逗号满 16 字即断 |
| 角标 | 左上「企业文化 · EP.01」，同时用于盖住平台水印 |

### 2. 制作流程

1. **分镜**：把 2 分钟切成 18–24 个 5–7 秒的镜头，每镜一句 25–32 字旁白（中文约 4.3 字/秒）。
2. **出图**：`ImageGen` + `size=1536x1024` + 参考图（`input_fidelity=low`），prompt 里把角色特征原样重复。
3. **裁图**：`crop=iw:ih-100:0:0` 去掉底部水印，再 `crop=iw:iw*9/16` 得到 1536×864。
4. **图生视频**：`VideoGen` 传裁好的图，5–6 秒，1080P。
5. **合成**：`setpts` 微慢放对齐旁白 → 烧字幕 → 叠角标 → 混 BGM → 响度标准化。
   若素材已由豆包等工具直接出好视频（自带配音），也可以走网页端：设置行「画面」选 **横屏 16:9**、「旁白音色」选 **不使用（沿用视频原声）**、素材已自带字幕时「字幕」选 **不启用（视频自带 / 无字幕）** → 挂视频 → 点「合成出片」，得到 1920×1080 横屏成片（时长按分镜 `duration` 对齐，0 积分）。

> **视频是外部生成的、没有配图怎么办？** 直接**从视频截帧**补成分镜图：
> 分镜卡片上点 **「从视频截帧」**（只在该镜有视频时出现），或点标题栏 **「全部从视频截帧」** 一次补齐所有「有视频但没图」的镜。
>
> **更省事：上传视频时自动截帧。** 挂载视频的那一刻，若该分镜还没有分镜图，后端直接从刚上传的视频抽一帧填进 `image_path`（取视频 40% 处，与手动截帧同一逻辑），页面刷新后图片即就位，无需事后再点截帧；若该镜已有图片（含手动上传的参考图）则**不覆盖**，需刷新可单独点「从视频截帧」。
>
> | 项 | 说明 |
> |----|------|
> | 抽帧位置 | 默认取视频 **40% 处**（避开开头淡入、结尾淡出和运镜起幅的过渡帧）。接口可传 `at`（秒）或 `ratio`（0–1）指定 |
> | 输出 | `projects/<项目>/images/NN.jpg`（jpg 约为 png 的 1/6 体积，只作预览/首帧参考，不参与成片） |
> | 已有图 | 批量模式**默认跳过**；单镜按钮是主动操作，默认覆盖（`force=true`） |
> | 旧图 | 刻意**不删**旧文件（可能是手动上传的参考图），只把 `image_path` 指向新截的 jpg |
> | 前提 | 该镜必须已挂视频，否则返回「该分镜还没有视频」 |
>
> 命令行走 API：`curl -X POST -d '{"force":true,"ratio":0.4}' http://127.0.0.1:7799/api/projects/<id>/scenes/1/frame`
>
> 分镜图在「视频已就绪」的流水线里**不是必需品**：`render_project` 优先用 `video_path`，只有没视频时才拿图片做 Ken Burns 推近。截帧主要是让网页不再显示「未生成图片」、并给重做镜头留个首帧参考。

### 2.5 栏目资产（角色圣经 / 分镜模板 / 选题库）

「叮叮城故事」企业文化的所有 IP 资产集中维护在仓库根目录 **`dingding-city/`**（内容层，**不跑引擎**，生成仍走本节产线）：

| 文件 | 作用 |
|------|------|
| `dingding-city/README.md` | 栏目定位、命名锁定（TT虎 / 叮叮城 / 叮叮城故事）、与 `projects/`·`series/` 的边界、EP 索引 |
| `dingding-city/角色圣经.md` | TT虎 / 猫老板 / 机器人小助手 / 兔妈妈 锁死规范 + 视觉体系 + 色调情绪映射 + 一致性红线（**每集出图/出视频前必读，prompt 原样重复角色特征**） |
| `dingding-city/分镜模板.md` | 单集分镜标准字段 + 可直接复制的 `project.json` 场景 schema（**已去掉 `year`/`age`**，TT虎 是虚构 IP、无年份年龄）+ 叮叮城 3D 卡通视觉 DNA prompt |
| `dingding-city/剧本生成规范_v2.md` | **系列通用母版（最高约束）**：9 集共用的通用规则——确认班底、主题落点（内部协同非对外服务）、结构弧与反转、第 3A 节导演工艺、逻辑护栏（不开车 / 零手动派单 / 不写乘客苦等 / 不出现同一单取消又送达）、scenes schema、自检清单。**不含任何单集专属剧情** |
| `dingding-city/单集任务提示词_模板.md` | 单集专用信息模板：只填本集专属（集号 / 关键词 / 角色分配 / 命题·立场锚 / 六拍剧情 / 三次反转 / 导演设定 / 护栏 / 落库），不重复通用规则 |
| `dingding-city/EPnn_关键词_任务提示词_vN.md` | 每集一份的定制稿（如 `EP02_说到做到_任务提示词_v2.md` / `EP03_勇于担当_任务提示词_v1.md`），由模板填充本集剧情而来，平台「生成剧本」会自动生成 / 复用 |
| `dingding-city/系列总览.md` | 9 集 ↔ 关键词 ↔ 价值观原文映射，栏目的唯一事实来源 |
| `dingding-city/ep01_坚守底线/` | **EP.01 权威 12 镜脚本**归档（早期 7 镜样片见 `projects/企业文化EP.01_坚守底线（豆包）`） |

> 为什么单列：TT虎 是虚构角色、没有生卒年/年龄，硬套 `projects/` 生平短片的 `year`/`age` 编年史会别扭。专栏的分镜模板复用 `project.json` 的 `scenes[]` 但砍掉这两个字段，其余产线完全一致。

### 2.6 网页入口（独立导航「企业文化」）

- 顶部导航新增 **企业文化**（`/culture/`），与「生平短片」「系列工厂」并列，是**独立分类**，不再混在生平短片列表里。
- 该页列出 9 集卡片（EP / 行为关键词 / 价值观 / 分镜-图-视频进度 / 是否成片）；点卡片进入编辑器 `/?p=<id>&cat=dingding-city`。
- 卡片右下角另有两个直达链接：**剧本**（`&panel=script`）与**角色**（`&panel=chars`），导演不必先进分镜页。
- 进入该分类后：左侧只列这 9 集、标题变为「企业文化 · 叮叮城故事」，且**分镜卡片不再显示「年份 / 年龄」两个输入框**（`web/app.js` 的 `hideYearAge()`，按 `project.category === 'dingding-city'` 判断）。
- 「生平短片」列表会自动剔除这 9 集，两个分类互不干扰。

### 2.7 「生成剧本」走「母版 + 单集任务提示词」两层流程（自包含）

企业文化项目点「1 生成剧本」，复制出的提示词会驱动一个**两层流程**，WorkBuddy 先读再写，不再靠临时回忆：

**第一步 · 生成单集任务提示词**：从标题提取集号与关键词（如 `叮叮城故事 · EP.03 勇于担当` → 集号 03、关键词 勇于担当），查 `dingding-city/` 下是否已有本集任务提示词文件（`EPnn_关键词_任务提示词_vN.md`）；没有就按 `单集任务提示词_模板.md` 填好本集专属信息，写入一份新的 `EPnn_关键词_任务提示词_v1.md`。**母版只管通用规则，单集剧情放进每集自己的提示词，两套文件分工，避免把某一集的故事焊死。**

**第二步 · 落 12 镜分镜**：严格按该任务提示词 + `剧本生成规范_v2.md`（题材 / 结构 / 第 3A 节导演工艺 / 护栏 / schema）把 12 镜写入 `project.json`。

提示词自带六个权威文件路径（母版 `_v2` / 模板 / 角色圣经 / 系列总览 / 分镜模板 / 选题库），并自动纠正三件事：① 集号与关键词从标题精准提取（不再误取「EP.02 说到做到」）；② 主题落点锁死「内部协同 / 对方角度 / 支持团队决策」，防止跑成对外服务；③ 角色只准用确认班底（TT虎 / 猫老板 / 机器人小助手，跨部门用兔妈妈），禁止新造常驻角色。详见 `web/app.js` 的 `buildPrompt()`。

### 2.8 导演面板：剧本 / 角色 / 自检（每集页右上角三个按钮）

分集页（`/?cat=dingding-city`）标题栏右上角有 **剧本 / 角色 / 自检** 三个入口，打开同一个右侧抽屉，抽屉顶部可互切页签。前端在 `web/culture-panel.js`，后端在 `core/culture.py`。

**① 剧本** —— 导演通读 + 配音稿

- 两种视图：**分镜脚本**（逐镜：镜号 / 标题 / 起止时间码 / 时长 / 语速 / 旁白 / 音效四层）+ **配音稿**（只有旁白，大字号，直接拿去录音）。
- 「提示词 开」可展开每镜的画面 / 运镜提示词（原文整段，便于核对是否带角色 DNA）。
- 顶部概要：镜数、总时长、平均语速、最高语速（超 4.3 字/秒标红）、画幅；下面一条**时长节奏条**，一眼看出哪镜偏长偏短。
- 对白自动识别旁白里的「」并用主题色高亮；音效按 `环境 / 拟音 / BGM / 旁白` 拆成小标签。
- 每镜自动挂提醒徽章：语速超限、时长不在 10–13s、缺图、缺视频。

**② 角色** —— 直接读 `dingding-city/角色圣经.md`（改 md 后点「刷新」即生效，不写死在前端）

- 每个角色一张卡：头像（**直接复用视频画面**——从**本集**高清分镜原图里挑该角色最清楚的帧，按角色紧裁成 512×512 存到 `dingding-city/avatars/<本集 slug>/<角色名>.png`，不 AI 重新生成；换图自动带 mtime 版本号清缓存）、身份 / 毛色 / 脸部 / 服装 / 体型等锁定项、**英文提示词原段**（一键复制）、一致性红线清单。
- **头像按集取，不是一套图全系列复用**：同一角色在不同集里的造型/毛色会有差异（EP.01 的小助手是半透明蓝色小机器人，EP.02 是白色小机器人），所以 `avatars/<本集 slug>/` 优先，缺图才回落到 `dingding-city/avatars/` 的系列通用图；卡片头像下方直接标注「本集分镜截图」或「系列通用参考图」，一眼能看出这张图是不是本集的。
- 头像**点头像可全屏放大看细节**（点击图片 1×/2.4× 切换、滚轮缩放、拖动平移、Esc 关闭）；某角色在渲染集里暂无出镜图时回落字母占位，不破图。
- 卡片按「本集出场 / 系列其他角色（本集未出场）」两段分组，出场判定优先读 `project.json` 的 `cast` 字段，没写则按本集旁白 / 标题里是否出现角色名。
- 底部附世界视觉、色调与情绪映射、产线红线（防猛推镜 / 防变形 / 防人类 / 屏幕不乱码字 等）。
- 「复制全部提示词」把全部角色的英文段一次拷走，批量出图时直接贴。

> 换/加某一集头头像的最快办法：把该集分镜原图里的角色裁成正方形存成 `dingding-city/avatars/<project.json 里的 slug>/<角色名>.png`，刷新页面即可，不用改代码。

**③ 自检** —— 把母版硬约束变成可执行检查

`GET /api/projects/{id}/delivery-check` 逐条核对 13 项：镜数 12、总时长 120–180s、单镜 10–13s、每镜语速 ≤4.3、运镜以 `Locked-off static camera` 开头、TT虎 出镜镜次带角色特征句、画面声明 `no readable text`、无人类、旁白数字中文、旁白无英文缩写（TT虎 / TT-Hu 视为专有名词放行）、结尾点题字幕、画幅 16:9、素材齐备。返回 `pass / warn / fail` 与**问题镜号**，点镜号直接跳到该分镜。**硬约束不过会判 fail（红），建议项只是 warn（黄）。**

**导出（浏览器直接下载）**

| 文件 | 接口 | 谁用 |
|------|------|------|
| 剧本 `.md` | `/api/projects/{id}/export/md` | 导演通读、评审留档 |
| 字幕 `.srt` | `/api/projects/{id}/export/srt` | 剪辑对轴、外挂字幕（按分镜时长估算，非逐字时间轴） |
| 剪辑单 `.csv` | `/api/projects/{id}/export/csv` | 剪辑台按镜号排时间线；含入出点、字数、语速、素材路径、两组提示词（带 BOM，Excel 直接打开不乱码） |

**深链**：`/?p=<id>&cat=dingding-city&panel=script|chars|check` 直接展开对应页签，方便把某一集的剧本 / 角色丢给同事。

**打印**：剧本页点「打印」只输出抽屉内容（A4 竖版，分镜不跨页断开），供现场拍摄 / 配音间用纸质稿。

### 2.9 成片命名与下载

成片文件名按项目类型区分（`core/render.py::output_basename`）：

| 项目类型 | 成片文件名 | 示例 |
|----------|------------|------|
| 企业文化（`category=dingding-city` / `series=叮叮城故事`） | `<剧集 slug>[_16x9].mp4` | `叮叮城故事EP.01_坚守底线_16x9.mp4` |
| 生平短片（其它） | `<人物>_生平短片[_16x9].mp4` | `张三_生平短片_16x9.mp4` |

- 横屏成片才加 `_16x9`；竖屏不加。
- 渲染完成后把实际文件名写入 `project.json` 的 `output_name`；网页「下载 .MP4」按钮的 `download` 属性优先取它，**保证下载名与磁盘文件、预览 URL 三者一致**。
- 早期用「人物名」命名的旧成片（如 `TT虎_生平短片_16x9.mp4`）已按新规则改名，并同步回写 `output_path` / `output_url`，无需重渲。

### 3. 必踩的坑（都验证过）

| 坑 | 现象 | 处理 |
|----|------|------|
| **图生视频猛推镜** | 写「slow push-in」后模型一路推，最后一秒只剩脸部大特写、身体出画 | prompt 开头写死 `Locked-off static camera, absolutely no camera movement, no zoom`，让**环境动**（雨、车流、屏幕数据）、人物只微动 |
| **角色变形/出画** | 手、平板、尾巴在运动中被改写 | 加 `keep the character's face, proportions, body and outfit perfectly consistent, fully inside the frame, no morphing` |
| **两处平台水印** | 图片右下角「AI生成 WORKBUDDY」、视频左上角「AI生成」 | 图片裁底 100px；视频左上角叠「企业文化 · EP.0X」角标盖住（`delogo` 会留一块白色补丁，比水印还难看，不要用） |
| **豆包视频水印会跳动** | 「豆包 AI 生成」在同一镜里会在右下角 ↔ 左上角之间换位置，还会淡出消失（实测 02 镜：t=1 右下、t=5 左上、t=8 整帧没有） | 裁固定边（`crop_bottom`）只能裁掉一部分，裁多了会切掉画面内容。这类水印**要么保留、要么整镜重出**，别指望裁边/`delogo` 干净去除；`crop_bottom` 只适合「固定底边水印条」（如 ImageGen 出的图） |
| **构图裁脚** | 16:9 裁切后主体的脚被切掉 | 出图时写 `full body visible with empty floor below his feet, generous headroom` |
| **音频变 96kHz** | `loudnorm` 默认升采样到 96k，进手机可能不兼容 | 链路写成 `amix(normalize=0) → aresample=48000 → loudnorm=I=-16:TP=-1.5 → aresample=48000` |
| **人声被压低** | `amix` 默认按输入数归一化，人声直接小一半 | `amix=...:normalize=0` |
| **配音播音腔太重** | **edge-tts 全部音色本质都是朗读引擎**，换 Yunxi/Yunjian/Xiaoxiao 只能在"哪种播报腔"之间挑，解决不了生硬 | 直接换 **MiniMax `speech-2.5-hd-preview`**（`audiobook_male_1`），它是有声书/故事语调，不是念稿。`edge-tts` 仅作断网兜底 |
| **MiniMax 返回 2013 invalid bitrate** | `audio_setting.bitrate` 只接受 32000 / 64000 / 128000 / 256000 | 传 128000，别传 192000 |
| **MiniMax 音乐接口 410** | `/v1/music_generation`（music-1.5）已下线，返回 HTTP 410 | BGM 只能用本地素材 + sidechain 混音，不要指望在线生成 |
| **听不出有 BGM** | `city_of_the_empire.mp3` 开头 -30dB（弱起），按 0.16 音量叠进去等于没有 | 从**第 65 秒**（能量稳定在 -16dB 左右）开始取，音量 0.34 |
| **音乐盖过人声** | 听感"背景音乐比旁白响" | 不能靠听，要量：人声段与纯音乐段的 RMS 差 **必须 9–12dB**。用 `acompressor` 只压**人声轨**（压整条会把音乐一起抬起来），音乐音量按测量值反算，最后 `alimiter=limit=0.84:level=false` |
| **`loudnorm` 把比例改掉** | 明明调低了音乐，成品里还是很响 | `loudnorm` 是动态压缩，会把音乐段抬回来。改成固定增益 + 人声压缩 + limiter，比例才可控 |
| **`alimiter` 后峰值还是 0dBFS** | 以为限幅失效 | `alimiter` 默认 `level=true` 会做自动电平补偿把输出推回满刻度，必须显式 `level=false` |
| **整体像播报、没电影感** | 只有人声 + 闷在底下的音乐 | 必须加**环境音效层**：`anoisesrc=color=pink` 过滤波器合成（雨 `highpass=700,lowpass=7500`；车流 `lowpass=220`；室内底噪 `lowpass=500`），音量 0.22–0.55，全程铺底 |
| **屏幕/灯牌乱码字** | 中文会被生成成假字 | prompt 加 `no readable text, no letters`，屏幕内容用抽象图标、地图线、色块代替；特写道具（文件夹、报告）要写 `completely blank with no printing` |
| **字幕溢出** | 一行 22 字在 1920 宽下超出画面；`」` 还会被挤成单独一行 | 改用标点优先断行 + 两句一组分两行显示，字号 48；不要用 `compose.split_lines` 默认的按字数硬切 |
| **口型对不上** | 图生视频没法按音频生成唇形 | **别用"让角色闭嘴"的办法糊弄**。用「时间窗口对齐」：① prompt 里写成表演节拍 `for the first 2 seconds closed-mouth smile → then speaks one short sentence with clear lip movement for about 3 seconds → finally mouth closes into a smile`；② 抽帧拼 tile 测出实际说话区间；③ 把**对白配音卡在这个区间内**；④ 对白用**独立角色音色**（如 `male-qn-jingying`），与旁白区分。这样"嘴动时才有声音"，观感就真了 |
| **AI 做不出"物体平移出画"**（**试一次不行就换**，别试第二遍） | 让爪子把卡推走：模型只会往下按、或往回拉；用首尾帧插值中间帧直接崩坏（桌面出现空洞）；逐帧位移又因爪子压在卡上必然穿帮 | **这类动作镜头直接砍掉，不要反复试**。改由"人物的拒绝姿态 + 旁白"承担信息（仰拍+短爪前推+一句"这条线，不能越"），比放一个动作不对的镜头可信 |
| **旁白说了、画面没有（含"推卡"事故）** | 旁白说"他把卡推了回去"，画面只有举手；说"手册写着坚守底线"，手册空白；说"推了回去"，卡根本不在画里 | **旁白只描述画面里真实存在的动作与物体**。做不到的动作就改说法（"抬起头""手收回来了"），不要用旁白替画面补戏 |
| **旁白说了、画面没有（旧条目）** | 旁白说"把卡推了回去"，画面只有举手；说"手册写着坚守底线"，手册是空白 | **关键信息必须有视觉落点**。动作就补动作镜头（道具特写），文字就**后期叠字**——AI 生成中文必然乱码，用 PIL 渲染宋体字做静态图层叠上去（`overlay`），比让模型画字可靠一百倍 |
| **旁白台词与分镜表不一致** | 网页上写"坚守底线"，成片字幕是"诚实正直" | 改了台词必须**回写 project.json 的 scenes[].narration**，否则用户无法在页面校对；`image_path/video_path/audio_path` 也要指向实际用的文件 |
| **旧规则（保留）** | 旁白镜头让角色**不说话**（只表情、动作），对白镜头才让嘴动；正面特写尽量少给说话镜头，多用侧身/过肩/道具特写 |
| **凭空多出肢体/尾巴/路人** | 模型会自己加一只人手、一条尾巴、一个背景角色（第三镜实测：先多出人类握手的手，再版左下角多出一条橙色虎尾） | prompt 显式写 `NO human hands / NO tail visible / nobody else enters`，并**把动作压到最小**（只扶门、抱文件夹，不让伸手）；真出了就截取干净时段，或换镜头语言（道具特写） |
| **背景角色形象崩坏** | 主角出现在背景小尺寸时，模型会自由发挥（第三镜的 TT虎 变成绿眼黄白条） | 要么让主角完全不入画，要么给足正面大特写；**不要让他当背景板** |

### 4. 成本参考（每分钟成片）

| 环节 | 工具 | 积分 |
|------|------|------|
| 12–14 张分镜图 | ImageGen | 约 60–140 |
| 12–14 条 5–6 秒视频 | VideoGen（50–100/条） | 约 600–1400 |
| 配音 / 字幕 / 合成 / 响度 | edge-tts + ffmpeg | 0 |

### 5. 已出成片

| 集 | 主题 | 状态 |
|----|------|------|
| EP.01 | 坚守底线（诚实正直 · 尊重他人 · 严守制度与流程） | 脚本定稿 12 镜 → `projects/叮叮城故事EP.01_坚守底线/`；脚本归档 `dingding-city/ep01_坚守底线/`；早期 7 镜样片 `projects/企业文化EP.01_坚守底线（豆包）` |

### 6. 系列规划（对照价值观表的 9 个行为关键词）

> 权威总表见 `dingding-city/系列总览.md`；9 集均已建 `projects/` 条目，且**均为 12 镜完整脚本**（待逐集出图/出视频）。

| 核心价值观 | 行为关键词 | 集 | 工程落点 |
|------------|------------|----|----------|
| 可信 | 坚守底线 | **EP.01（12 镜定稿）** | `projects/叮叮城故事EP.01_坚守底线/` |
| 可信 | 说到做到 | EP.02（12 镜定稿） | `projects/叮叮城故事EP.02_说到做到/` |
| 可信 | 勇于担当 | EP.03（12 镜定稿） | `projects/叮叮城故事EP.03_勇于担当/` |
| 有用 | 拥抱好奇 | EP.04（12 镜定稿） | `projects/叮叮城故事EP.04_拥抱好奇/` |
| 有用 | 创造价值 | EP.05（12 镜定稿） | `projects/叮叮城故事EP.05_创造价值/` |
| 有用 | 能拿结果 | EP.06（12 镜定稿） | `projects/叮叮城故事EP.06_能拿结果/` |
| 共生 | 协作赋能 | EP.07（12 镜定稿） | `projects/叮叮城故事EP.07_协作赋能/` |
| 共生 | 平等开放 | EP.08（12 镜定稿） | `projects/叮叮城故事EP.08_平等开放/` |
| 共生 | 共创共赢 | EP.09（12 镜定稿） | `projects/叮叮城故事EP.09_共创共赢/` |


### 7. 在手机上看成片

产物卡片在手机钉钉里打不开（提示「前往桌面端查看」）。两条可用路径：

| 方式 | 做法 |
|------|------|
| 钉盘 | `dws drive +upload --file <mp4> --file-name "<中文名>.mp4" -y`，返回的 `docUrl` 手机钉钉内可直接播 |
| 局域网页面 | `hd/share/daemon.py`（双 fork 守护）+ `lanserv.py`（**必须支持 Range 206**，否则 iPhone 播不了），端口 7811，手机浏览器访问 `http://<Mac局域网IP>:7811/` |

坑：`python -m http.server` **不支持 Range**，Safari 会播不动；`nohup ... &` 的进程在工具调用结束后会被回收，必须双 fork + `setsid()`。
