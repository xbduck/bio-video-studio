# 生平短片工厂 · 使用说明

> 输入一个人物名（或企业名），输出一条 1080×1920 竖屏生平短片。
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
| HyperFrames 本地渲染（默认 `hf`） | 0 | **0** | 运镜以推 / 拉 / 摇 / 移为主，原生 30fps，时长与配音精确对齐 |
| 视频大模型（`ai`） | 50–100 | **600–1200** | 需要真实物理运动（车在开、人在走、航拍俯冲） |
| 混合（`mix`） | 仅大模型那几条计费 | **250–500** | 挑 4–5 条重点镜头用大模型，其余本地渲染 |

计费口径不同：`ai` 按条计费，`mix` 是整片合计（只有 4–5 条产生费用）。
选好的路线会随任务入队，并显示在排队提示卡和复制给 WorkBuddy 的提示词里。

---

## 三、其它设置

| 设置项 | 位置 | 说明 |
|--------|------|------|
| 音色 | 设置行「配音音色」 | 默认 `zh-CN-YunjianNeural`（浑厚男声）。另有 Yunxi / Xiaoxiao / Yunyang 等 |
| 语速 | 设置行 | `+0%` 起调 |
| BGM | 「上传 BGM」 | 支持 mp3/wav/m4a/aac；音量滑杆默认 0.18 |
| 保存设置 | 设置行末尾 | 改完记得点，否则不落库 |

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

## 七、常见问题

| 现象 | 原因 / 处理 |
|------|------------|
| 改了前端但页面没变 | 必须**重启服务**；重启前先 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 找到旧进程 kill（`pkill -f app.py` 在本机杀不掉，新进程会报端口占用却仍打印 `ready=True`，容易误判成"改了没生效"）。改 CSS 还需 bump 一次 `style.css?v=N` |
| curl 本地接口返回 502 | 会话代理拦了 localhost，curl 加 `--noproxy '*'` |
| 配音失败 / 卡住 | edge-tts 需联网；守护启动已剥离会话级代理，前台启动若环境有 `HTTP_PROXY` 需手动 `unset` |
| ffmpeg 报找不到字体 | 已做跨平台探测（macOS 用 Hiragino Sans GB，Windows 用微软雅黑，Linux 用 Noto CJK），换机器无需改配置 |
| 服务起在别的端口 | 7799 被占用时以 `start_daemon.py` 打印的 port 为准 |
| 成片有慢放 / 幻灯片感 | 视频素材时长短于配音导致被拉伸。走 `hf` 路线按「配音时长 + 0.6s」渲染可避免 |
