/* 生平短片工厂 —— 前端逻辑 */

const $ = (id) => document.getElementById(id);
const state = {
  projects: [],
  current: null,     // project 详情
  tasks: [],
  polling: null,
  jobId: null,
  promptText: '',
};

/* ---- 分类模式：?cat=dingding-city 时进入「企业文化 · 叮叮城故事」专栏视图 ---- */
const QS = new URLSearchParams(location.search);
const CULTURE_MODE = QS.get('cat') === 'dingding-city';

/* ---------------- 基础 ---------------- */

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2400);
}

async function api(url, opts) {
  let r;
  try {
    r = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...(opts || {}),
    });
  } catch (e) {
    setHealth(false);
    throw new Error('无法连接本地服务，请确认服务已启动（运行 run.bat），然后刷新页面重试');
  }
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(e.detail || r.statusText);
  }
  setHealth(true);
  return r.json();
}

function setHealth(ok) {
  const h = $('health');
  if (!ok) {
    h.textContent = '⚠ 服务未连接';
    h.style.color = '#e5484d';
  } else {
    h.style.color = '';
  }
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function assetUrl(path) {
  if (!path) return '';
  if (path.startsWith('http') || path.startsWith('/')) return path;
  return `/projects/${state.current.slug}/${path}`;
}

/* ---------------- 项目列表 ---------------- */

async function loadProjects(selectId) {
  let all = await api('/api/projects');
  const isCulture = (p) => (p.title || '').includes('叮叮城故事');
  all = CULTURE_MODE ? all.filter(isCulture) : all.filter((p) => !isCulture(p));
  state.projects = all;
  renderProjectList();
  if (selectId) openProject(selectId);
  else if (state.current) openProject(state.current.id, true);
  else if (state.projects.length && !state.current) openProject(state.projects[0].id);
  else if (!state.projects.length) {
    $('emptyState').classList.remove('hidden');
    $('projectView').classList.add('hidden');
  }
}

function renderProjectList() {
  const box = $('projectList');
  if (!state.projects.length) {
    box.innerHTML = '<p class="muted small" style="padding:10px">暂无项目</p>';
    return;
  }
  box.innerHTML = state.projects.map((p) => `
    <div class="proj-item ${state.current && state.current.id === p.id ? 'active' : ''}"
         data-id="${p.id}">
      <div class="pi-name">${esc(CULTURE_MODE ? (p.title || p.person) : p.person)}</div>
      <div class="pi-meta">${p.scenes} 分镜 · 图 ${p.images} · 视频 ${p.videos}${p.output_url ? ' · 已成片' : ''}</div>
    </div>`).join('');
  box.querySelectorAll('.proj-item').forEach((el) => {
    el.onclick = () => openProject(el.dataset.id);
  });
}

/* ---------------- 打开项目 ---------------- */

async function openProject(id, keepScroll) {
  const y = $('workspace').scrollTop;
  state.current = await api(`/api/projects/${id}`);
  $('emptyState').classList.add('hidden');
  $('projectView').classList.remove('hidden');
  renderProject();
  await loadTasks();
  renderProjectList();
  if (keepScroll) $('workspace').scrollTop = y;
  startPolling();
}

function renderProject() {
  const p = state.current;
  $('pTitle').value = p.title || p.person;
  $('pPerson').textContent = p.person;
  $('pUpdated').textContent = '更新于 ' + (p.updated_at || '-');

  const n = p.scenes.length;
  const ni = p.scenes.filter((s) => s.image_path).length;
  const nv = p.scenes.filter((s) => s.video_path).length;
  const na = p.scenes.filter((s) => s.audio_path).length;
  const aspect = p.aspect || 'portrait';
  const aspectTxt = aspect === 'landscape' ? '横屏 16:9' : '竖屏 9:16';
  const subTxt = (p.burn_subtitles === false) ? '字幕 关' : '字幕 开';
  $('pStats').textContent =
    `${n} 分镜 · 图 ${ni}/${n} · 视频 ${nv}/${n} · 配音 ${na}/${n} · ${aspectTxt} · ${subTxt}`;

  $('aspectSel').value = aspect;
  // burn_subtitles === false 是「不烧录字幕（视频自带 / 无字幕）」，渲染时透传原画面
  $('subSel').value = (p.burn_subtitles === false) ? '0' : '1';
  // voice === '' 是「不使用旁白（沿用视频原声）」，不能再回落成默认音色
  $('voiceSel').value = (p.voice === undefined || p.voice === null) ? 'zh-CN-YunjianNeural' : p.voice;
  $('rateSel').value = p.rate || '+0%';
  $('cropBottom').value = p.crop_bottom ?? 0;
  $('bgmName').textContent = p.bgm_path || '未设置';
  $('bgmVol').value = p.bgm_volume ?? 0.18;
  $('bgmVolVal').textContent = (p.bgm_volume ?? 0.18).toFixed(2);

  renderScenes();
  updateSteps();
  renderResult();
}

function updateSteps() {
  const p = state.current;
  const set = (id, cls, txt) => {
    const st = $(id);
    st.className = 'step-state';
    if (cls) st.classList.add(cls);
    st.textContent = txt;
  };

  const nAll = p.scenes.length;
  const nImg = p.scenes.filter((s) => s.image_path).length;
  const nVid = p.scenes.filter((s) => s.video_path).length;
  const nAud = p.scenes.filter((s) => s.audio_path).length;

  const scriptTask = state.tasks.find((t) => t.project_id === p.id && t.type === 'script' && t.status !== 'done');
  const imgTask = state.tasks.find((t) => t.project_id === p.id && t.type === 'images' && t.status !== 'done' && t.status !== 'failed');
  const vidTask = state.tasks.find((t) => t.project_id === p.id && t.type === 'videos' && t.status !== 'done' && t.status !== 'failed');

  const mark = (btnId, waiting) => {
    const b = $(btnId);
    b.classList.toggle('waiting', !!waiting);
    b.classList.toggle('done', !waiting);
  };

  if (!nAll) {
    set('stateScript', '', '未开始'); mark('stepScript', true);
  } else {
    set('stateScript', 'ok', `${nAll} 个分镜`); mark('stepScript', !!scriptTask);
  }

  if (!nAll) { set('stateImages', '', '待剧本'); mark('stepImages', false); }
  else if (nImg < nAll) { set('stateImages', 'waiting', `${nImg}/${nAll} · 待生成`); mark('stepImages', !imgTask); }
  else { set('stateImages', 'ok', `${nImg}/${nAll}`); mark('stepImages', false); }

  if (!nImg) { set('stateVideos', '', '待图片'); mark('stepVideos', false); }
  else if (nVid < nAll) { set('stateVideos', 'waiting', `${nVid}/${nAll} · 待生成`); mark('stepVideos', !vidTask); }
  else { set('stateVideos', 'ok', `${nVid}/${nAll}`); mark('stepVideos', false); }

  const noVoice = p.voice === '' || p.voice === null;
  if (!nAll) set('stateTts', '', '待剧本');
  else if (noVoice) set('stateTts', 'ok', '原声 · 不配音');
  else if (nAud < nAll) set('stateTts', 'waiting', `${nAud}/${nAll} · 点此配音`);
  else set('stateTts', 'ok', `${nAud}/${nAll}`);

  set('stateRender', p.output_url ? 'ok' : '', p.output_url ? '已出片 · 可重新合成' : '点此合成');
  $('stepRender').classList.toggle('done', !!p.output_url);

  renderCallout();
}

/* ---------------- 提示条 ---------------- */

const STEP_LABEL = { script: '剧本', images: '图片', videos: '视频' };

async function renderCallout() {
  const p = state.current;
  const active = (state.tasks || []).filter(
    (t) => t.project_id === p.id && (t.status === 'pending' || t.status === 'running')
  );
  const box = $('callout');
  if (!active.length) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');

  const types = [...new Set(active.map((t) => t.type))];
  const label = types.map((t) => STEP_LABEL[t] || t).join(' + ');
  $('calloutTitle').textContent = `已排队：生成${label}`;

  // 拉取生视频规划（预估积分 + 哪些镜用 AI），让提示词精确约束 WorkBuddy
  let plan = null;
  const vTask = active.find((t) => t.type === 'videos');
  if (vTask) {
    const route = (vTask.payload && vTask.payload.route) || 'hf';
    try {
      plan = await api(`/api/projects/${p.id}/video-plan?route=${encodeURIComponent(route)}`);
    } catch (e) { plan = null; }
    // 取不到规划时的兜底（保证提示词不误导）
    if (!plan) {
      const remaining = p.scenes.filter((s) => s.image_path && !s.video_path).length;
      const isAi = route === 'ai';
      plan = {
        route,
        ai_indices: isAi ? p.scenes.filter((s) => s.image_path && !s.video_path).map((s) => s.index) : [],
        local_indices: isAi ? [] : p.scenes.filter((s) => s.image_path && !s.video_path).map((s) => s.index),
        ai_count: isAi ? remaining : 0,
        total: remaining,
        estimate_low: isAi ? remaining * 50 : 0,
        estimate_high: isAi ? remaining * 100 : 0,
      };
    }
  }
  state.videoPlan = plan;

  let desc = '这一步由 WorkBuddy 在对话里执行。复制提示词发给我即可开始。';
  if (plan) {
    const est = plan.ai_count > 0
      ? `预估消耗 ${plan.estimate_low}~${plan.estimate_high} 积分（${plan.ai_count}/${plan.total} 条用模型）。`
      : '本地渲染，0 积分。';
    desc = `${ROUTE_LABEL[plan.route] || plan.route}。${est}${desc}`;
  }
  $('calloutDesc').textContent = desc;
  state.promptText = buildPrompt(types, p, plan);
}

const ROUTE_LABEL = {
  hf: 'HyperFrames 本地渲染（0 积分）',
  ai: '视频大模型（约 50-100 积分/条）',
  mix: '混合：自动挑镜，仅真实运动镜头用模型',
};

function buildPrompt(types, p, plan) {
  const nAll = p.scenes.length;
  const nImg = p.scenes.filter((s) => s.image_path).length;
  const nVid = p.scenes.filter((s) => s.video_path).length;
  let videosLine = '';
  if (types.includes('videos')) {
    const r = (plan && plan.route) || 'hf';
    if (r === 'hf') {
      videosLine = `把【${p.person}】的批量生成视频任务跑完（共 ${nAll - nVid} 条待生成），路线：HyperFrames 本地渲染（0 积分）。推/拉/摇/移全部由本地 ffmpeg 完成，**不要调用任何视频大模型**，不要消耗积分。`;
    } else if (r === 'ai') {
      videosLine = `把【${p.person}】的批量生成视频任务跑完（共 ${nAll - nVid} 条待生成），路线：视频大模型图生视频（约 ${plan.estimate_low}~${plan.estimate_high} 积分）。每条都用图生视频。`;
    } else { // mix
      const aiList = plan.ai_indices.length ? ('第 ' + plan.ai_indices.join('、') + ' 镜') : '无';
      const localList = plan.local_indices.length ? ('第 ' + plan.local_indices.join('、') + ' 镜') : '无';
      videosLine = `把【${p.person}】的批量生成视频任务跑完，路线：混合（约 ${plan.estimate_low}~${plan.estimate_high} 积分）。规则：仅对 ${aiList} 使用视频大模型图生视频（这些是真实物理运动，如开车/行走/航拍）；其余 ${localList} 一律用本地渲染（推/拉/摇/移），**不要调用视频大模型、不要消耗积分**。`;
    }
  }
  const culture = p.category === 'dingding-city' || (p.title || '').includes('叮叮城故事');
  // 取集号与价值观关键词：从「叮叮城故事 · EP.02 说到做到」→ 集号 02、关键词 说到做到
  const epNo = ((p.title || '').match(/EP\.(\d+)/i) || [])[1] || '';
  const theme = ((p.title || '').split('·').pop().trim().replace(/^EP\.\d+\s*/, '')) || '企业文化';
  const ROOT = '/Users/lingmf/Downloads/workbuddy/bio-video-studio';
  const map = {
    script: culture
      ? `为【${p.person}】生成《${p.series || '叮叮城故事'}》单集分镜剧本，走「母版 + 单集任务提示词」两层流程：\n\n` +
        `【必读权威文件】（工程根 ${ROOT}/，逐一读完再动笔）\n` +
        `1. ${ROOT}/dingding-city/剧本生成规范_v2.md —— 系列通用母版（结构 / 第3A节导演工艺 / 护栏 / scenes schema / 自检清单，最高约束）\n` +
        `2. ${ROOT}/dingding-city/单集任务提示词_模板.md —— 单集专用信息模板（只填本集专属，不重复通用规则）\n` +
        `3. ${ROOT}/dingding-city/角色圣经.md —— 角色特征 + 英文核心句 + 视觉红线（每镜 prompt 原样重复角色特征）\n` +
        `4. ${ROOT}/dingding-city/系列总览.md —— 本集价值观对内原文（逐字对齐，不得改写）+ 簇归属\n` +
        `5. ${ROOT}/dingding-city/分镜模板.md —— 视觉 DNA 前缀（第三节）+ project.json schema\n` +
        `6. ${ROOT}/dingding-city/选题库.md —— 本集剧情钩子参考\n\n` +
        `【第一步 · 生成单集任务提示词】\n` +
        `· 从本集标题提取集号与关键词（如「叮叮城故事 · EP.${epNo || '03'} ${theme}」→ 集号 ${epNo || '03'}、关键词 ${theme}）。\n` +
        `· 先查 ${ROOT}/dingding-city/ 下是否已有本集任务提示词文件（命名 EPnn_关键词_任务提示词_v*.md）：\n` +
        `  已有 → 直接用作权威，跳过本步；没有 → 复制 单集任务提示词_模板.md，填好【】占位（集号、关键词、系列总览对内原文、簇、角色分配、命题/立场锚、六拍剧情、三次反转、导演专属设定、护栏、落库），写入 ${ROOT}/dingding-city/EP${epNo || '03'}_${theme}_任务提示词_v1.md。\n` +
        `· 本集专属信息从 系列总览.md（对内原文 + 簇）与 选题库.md（钩子）取，不在母版里预设剧情。\n\n` +
        `【第二步 · 落 12 镜分镜】\n` +
        `· 严格按上一步任务提示词 + 母版护栏 / 导演工艺 / schema，把 12 镜写入工程 project.json 的 scenes[]。\n` +
        `· 字段：index / title / duration(整数秒, A 档 10–13) / narration(30–45 字, 角色对白用「」) / sound(环境/拟音/BGM/旁白四层) / image_prompt(先贴分镜模板第三节视觉 DNA 前缀) / video_prompt(以 "Locked-off static camera, absolutely no camera movement, no zoom, no pan" 开头) / image_path:"" / video_path:"" / audio_path:"" / image_status:"pending" / video_status:"pending"。\n` +
        `· year / age 留空字符串；aspect: landscape，category: dingding-city，series: 叮叮城故事；点题句写入 ending_subtitle。\n` +
        `· 总时长合计 120–180 秒（≥2 分钟）；旁白 ≤4.3 字/秒；数字写中文、无英文缩写；屏幕 no readable text, no letters。\n` +
        `· 角色只用确认班底 + 本集一次性动物 / 无名客串，无新造常驻角色、无人类。\n` +
        `· 完成后把 pending 的 script 任务标记 done（或直接编辑 project.json 后保存）。\n` +
        `· 交付附：logline、三次反转表（位置｜预期｜实际｜逻辑来源）、12 镜时长合计与每镜语速、母版第 7 节自检勾选、视觉母题与点题字幕。`
      : `为【${p.person}】写一份从出生到死亡的分镜剧本（8-12 个重大事件，每镜含旁白、生图提示词、运镜提示词），并写入工程`,
    images: `把【${p.person}】的批量生图任务跑完（共 ${nAll - nImg} 张待生成）`,
    videos: videosLine,
  };
  const parts = types.map((t) => map[t]).filter(Boolean);
  const factory = culture ? '企业文化专栏' : '生平短片工厂';
  return `请处理「${factory}」的待办任务：\n1. ${parts.join('\n2. ')}\n（工程目录：bio-video-studio/projects/${p.slug}）`;
}

/* ---------------- 企业文化专栏（隐藏 year/age + 换品牌） ---------------- */

function hideYearAge() {
  const p = state.current;
  if (!p) return CULTURE_MODE;
  return p.category === 'dingding-city' || (p.title || '').includes('叮叮城故事');
}

function applyCultureBranding() {
  document.title = '企业文化 · 叮叮城故事';
  const h1 = document.querySelector('.brand h1');
  if (h1) h1.textContent = '企业文化 · 叮叮城故事';
  const sub = document.querySelector('.brand p');
  if (sub) sub.textContent = 'TT虎 系列短剧 · 分镜 → 配图 → 视频 → 成片';
  const np = document.querySelector('.new-project');
  if (np) np.style.display = 'none';
  const foot = document.querySelector('.sidebar-foot');
  if (foot) foot.style.display = 'none';
  const nav = document.querySelectorAll('.brand a.btn, .topbar a.btn');
  nav.forEach((a) => {
    a.classList.toggle('active', a.textContent.includes('企业'));
  });
}

/* ---------------- 分镜表 ---------------- */

function renderScenes() {
  const p = state.current;
  const box = $('scenes');
  if (!p.scenes.length) {
    box.innerHTML = '<p class="muted">还没有分镜。点击上方「1 生成剧本」排队。</p>';
    return;
  }
  box.innerHTML = p.scenes.map((s, i) => sceneHtml(s, i)).join('');
  bindScenes();
}

function sceneHtml(s, i) {
  const imgUrl = assetUrl(s.image_path);
  const vidUrl = assetUrl(s.video_path);
  const audUrl = assetUrl(s.audio_path);
  return `
  <div class="scene" data-index="${s.index}">
    <div>
      <div class="scene-index">${s.index}</div>
    </div>
    <div class="scene-main">
      <div class="scene-row">
        ${hideYearAge() ? '' : `<input class="inp-year" data-f="year" value="${esc(s.year)}" placeholder="年份">
        <input class="inp-age" data-f="age" value="${esc(s.age)}" placeholder="年龄">`}
        <input class="inp-title" data-f="title" value="${esc(s.title)}" placeholder="${hideYearAge() ? '镜头标题' : '事件标题'}">
      </div>
      <span class="field-label">旁白 / 字幕</span>
      <textarea data-f="narration" placeholder="这一段念给观众听的话">${esc(s.narration)}</textarea>
      <div class="scene-row">
        <input class="inp-age" data-f="duration" value="${esc(s.duration)}" placeholder="时长（秒）">
        <input class="inp-title" data-f="sound" value="${esc(s.sound)}" placeholder="音效 / 音乐">
      </div>
      <span class="field-label">生图提示词（画面描述）</span>
      <textarea class="prompt" data-f="image_prompt" placeholder="画面内容、时代、光线、构图">${esc(s.image_prompt)}</textarea>
      <span class="field-label">运镜提示词（视频动态）</span>
      <textarea class="prompt" data-f="video_prompt" placeholder="镜头运动、人物动作、氛围变化">${esc(s.video_prompt)}</textarea>
    </div>
    <div class="scene-assets">
      <div class="asset-row">
        <div class="asset" data-kind="image" data-src="${imgUrl}">
          ${imgUrl ? `<img src="${imgUrl}" loading="lazy">`
            : (vidUrl ? '<span class="ph">未生成图片<br><small>可用视频截帧</small></span>'
                      : '<span class="ph">未生成图片</span>')}
          <span class="badge ${s.image_path ? 'ok' : ''}">图</span>
          <button class="scene-del" data-del="${s.index}" title="删除分镜">×</button>
        </div>
        <div class="asset" data-kind="video" data-src="${vidUrl}">
          ${vidUrl ? `<video src="${vidUrl}" muted playsinline preload="metadata"></video>` : '<span class="ph">未生成视频</span>'}
          <span class="badge ${s.video_path ? 'ok' : ''}">视频</span>
        </div>
      </div>
      ${audUrl
        ? `<div class="audio-chip ok"><audio controls src="${audUrl}"></audio></div>`
        : '<div class="audio-chip">未配音</div>'}
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn small" data-upload="${s.index}" data-kind="image">换图</button>
        <button class="btn small" data-upload="${s.index}" data-kind="video">换视频</button>
        ${vidUrl ? `<button class="btn small" data-frame="${s.index}" title="从这条视频里抽一帧作为分镜图">从视频截帧</button>` : ''}
      </div>
    </div>
  </div>`;
}

function bindScenes() {
  document.querySelectorAll('.scene').forEach((el) => {
    const idx = Number(el.dataset.index);
    const scene = state.current.scenes.find((s) => s.index === idx);

    el.querySelectorAll('[data-f]').forEach((inp) => {
      inp.addEventListener('input', () => {
        scene[inp.dataset.f] = inp.value;
        markDirty(true);
      });
    });

    el.querySelector('.scene-del').onclick = () => {
      state.current.scenes = state.current.scenes.filter((s) => s.index !== idx);
      state.current.scenes.forEach((s, i) => { s.index = i + 1; });
      renderScenes();
      updateSteps();
      markDirty(true);
    };

    el.querySelectorAll('.asset').forEach((a) => {
      a.onclick = (e) => {
        if (e.target.closest('.scene-del')) return;
        const src = a.dataset.src;
        const kind = a.dataset.kind;
        if (!src) {
          triggerUpload(idx, kind);
          return;
        }
        openModal(src, kind, scene);
      };
    });

    el.querySelectorAll('[data-upload]').forEach((b) => {
      b.onclick = () => triggerUpload(Number(b.dataset.upload), b.dataset.kind);
    });

    el.querySelectorAll('[data-frame]').forEach((b) => {
      b.onclick = async () => {
        const i = Number(b.dataset.frame);
        const label = b.textContent;
        b.disabled = true;
        b.textContent = '截帧中…';
        try {
          const r = await api(`/api/projects/${state.current.id}/scenes/${i}/frame`, {
            method: 'POST', body: JSON.stringify({ force: true }),
          });
          if (!r.ok) throw new Error(r.error || r.reason || '截帧失败');
          toast(`镜 ${i} 已从视频截帧`);
          state.current = await api(`/api/projects/${state.current.id}`);
          renderProject();
        } catch (e) {
          toast('截帧失败：' + e.message);
          b.disabled = false;
          b.textContent = label;
        }
      };
    });
  });
}

let dirty = false;
function markDirty(v) {
  dirty = v;
  $('btnSaveScenes').classList.toggle('primary', v);
  $('btnSaveScenes').textContent = v ? '保存剧本 *' : '保存剧本';
}

function triggerUpload(index, kind) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = kind === 'video' ? 'video/*' : 'image/*';
  input.onchange = async () => {
    const f = input.files[0];
    if (!f) return;
    const data = await readAsDataURL(f);
    try {
      const r = await api(`/api/projects/${state.current.id}/asset`, {
        method: 'POST',
        body: JSON.stringify({ index, kind, filename: f.name, data }),
      });
      if (r.frame_auto && r.frame_auto.ok) {
        toast(kind === 'video' ? '已上传视频，并自动截取首帧填充分镜图' : '已上传');
      } else if (r.frame_auto && !r.frame_auto.ok) {
        toast('已上传视频（该镜已有图片，未覆盖；可点「从视频截帧」刷新）');
      } else {
        toast('已上传');
      }
      state.current = await api(`/api/projects/${state.current.id}`);
      renderProject();
    } catch (e) { toast('上传失败：' + e.message); }
  };
  input.click();
}

function readAsDataURL(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

/* ---------------- 弹窗 ---------------- */

function openModal(src, kind, scene) {
  const c = $('modalContent');
  c.innerHTML = kind === 'video'
    ? `<video src="${src}" controls autoplay playsinline></video>`
    : `<img src="${src}">`;
  if (scene) {
    const cap = document.createElement('div');
    cap.className = 'modal-cap';
    cap.innerHTML = `<b>${esc(hideYearAge() ? '' : scene.year)} ${esc(scene.title)}</b><br>${esc(scene.narration)}`;
    c.appendChild(cap);
  }
  $('modal').classList.remove('hidden');
}
$('modalClose').onclick = () => $('modal').classList.add('hidden');
$('modalMask').onclick = () => $('modal').classList.add('hidden');
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') $('modal').classList.add('hidden');
});

/* ---------------- 流水线动作 ---------------- */

async function requestStep(type) {
  const p = state.current;
  if (!p) return;
  try {
    if (type === 'script') {
      if (p.scenes.length && !confirm(`已有 ${p.scenes.length} 个分镜，确定重新生成剧本？`)) return;
      await api(`/api/projects/${p.id}/request/script`, { method: 'POST' });
    } else if (type === 'images') {
      const todo = p.scenes.filter((s) => !s.image_path).map((s) => s.index);
      if (!todo.length) { toast('所有分镜已有图片'); return; }
      await api(`/api/projects/${p.id}/request/images`, {
        method: 'POST', body: JSON.stringify({ indices: todo }),
      });
    } else if (type === 'videos') {
      const todo = p.scenes.filter((s) => s.image_path && !s.video_path).map((s) => s.index);
      if (!todo.length) { toast('没有可生成视频的分镜（需先有图片）'); return; }
      const route = ($('videoRoute') && $('videoRoute').value) || 'hf';
      await api(`/api/projects/${p.id}/request/videos`, {
        method: 'POST', body: JSON.stringify({ indices: todo, route }),
      });
    } else if (type === 'tts') {
      if (!p.scenes.length) { toast('请先生成剧本'); return; }
      const { job_id } = await api(`/api/projects/${p.id}/tts`, { method: 'POST' });
      watchJob(job_id, '配音中');
      return;
    } else if (type === 'render') {
      if (!p.scenes.some((s) => s.image_path || s.video_path)) { toast('请先生成素材'); return; }
      const { job_id } = await api(`/api/projects/${p.id}/render?with_title=true&with_bgm=true`,
        { method: 'POST' });
      watchJob(job_id, '合成中');
      return;
    }
    await loadTasks();
    renderProject();
    toast('已加入队列，复制提示词发给我即可执行');
    $('callout').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) { toast(e.message); }
}

function watchJob(jobId, label) {
  state.jobId = jobId;
  $('progressWrap').classList.remove('hidden');
  const timer = setInterval(async () => {
    let st;
    try { st = await api(`/api/jobs/${encodeURIComponent(jobId)}`); }
    catch (e) { clearInterval(timer); return; }
    $('progressFill').style.width = (st.progress || 0) + '%';
    $('progressText').textContent = `${label}：${st.message || ''}`;
    if (st.status === 'done') {
      clearInterval(timer);
      state.jobId = null;
      $('progressText').textContent = '完成';
      setTimeout(() => $('progressWrap').classList.add('hidden'), 1200);
      state.current = await api(`/api/projects/${state.current.id}`);
      renderProject();
      loadProjects(state.current.id);
      toast(label + '完成');
    } else if (st.status === 'failed') {
      clearInterval(timer);
      state.jobId = null;
      $('progressText').textContent = '失败：' + (st.error || '');
      toast('失败：' + (st.error || '').slice(0, 80));
    }
  }, 1200);
}

/* ---------------- 任务队列 ---------------- */

async function loadTasks() {
  state.tasks = await api('/api/tasks?limit=40');
  renderTasks();
}

function renderTasks() {
  const mine = state.tasks.filter((t) => t.project_id === state.current?.id).slice(0, 8);
  const box = $('taskList');
  if (!mine.length) {
    box.innerHTML = '<p class="muted small">暂无任务</p>';
    return;
  }
  const name = { script: '生成剧本', images: '批量生图', videos: '批量生视频' };
  box.innerHTML = mine.map((t) => `
    <div class="task">
      <span class="st ${t.status}">${t.status}</span>
      <span>${name[t.type] || t.type}</span>
      <span class="tid">${t.task_id}</span>
      <span class="muted">${esc(t.message || '')}</span>
    </div>`).join('');
}

/* ---------------- 轮询 ---------------- */

function startPolling() {
  clearInterval(state.polling);
  state.polling = setInterval(async () => {
    // 有本地 job 在跑，或用户正在编辑未保存时，不刷新，避免覆盖输入
    if (!state.current || state.jobId || dirty) return;
    try {
      const before = JSON.stringify(state.current.scenes?.map((s) => [s.image_path, s.video_path, s.audio_path]));
      state.current = await api(`/api/projects/${state.current.id}`);
      const after = JSON.stringify(state.current.scenes?.map((s) => [s.image_path, s.video_path, s.audio_path]));
      await loadTasks();
      if (before !== after) {
        renderScenes();
        renderResult();
      }
      updateSteps();
    } catch (e) { setHealth(false); /* 忽略瞬时错误 */ }
  }, 3000);
}

/* ---------------- 成片 ---------------- */

function renderResult() {
  const p = state.current;
  const box = $('resultBox');
  if (!p.output_url) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('resultVideo').src = p.output_url;
  $('btnDownload').href = p.output_url;
  $('btnDownload').setAttribute('download', `${p.person}_生平短片.mp4`);
  $('resultMeta').textContent = `输出目录：projects/${p.slug}/output`;
}
$('btnOpenFolder').onclick = async () => {
  const p = state.current;
  try {
    await api('/api/open-folder', {
      method: 'POST', body: JSON.stringify({ path: `projects/${p.slug}/output` }),
    });
  } catch (e) { toast('如无法打开，请手动前往 projects/' + p.slug + '/output'); }
};

/* ---------------- 事件绑定 ---------------- */

async function loadVoices() {
  const vs = await api('/api/voices');
  // 第一项为空值：视频自带配音时不选音色，合成时保留原声音轨
  $('voiceSel').innerHTML =
    '<option value="">不使用（沿用视频自带音色 / 原声）</option>'
    + vs.map((v) => `<option value="${v.id}">${v.name}</option>`).join('');
}

$('btnCreate').onclick = async () => {
  const person = $('personInput').value.trim();
  if (!person) { toast('请输入人物名'); return; }
  try {
    const p = await api('/api/projects', {
      method: 'POST', body: JSON.stringify({ person }),
    });
    $('personInput').value = '';
    await loadProjects(p.id);
    toast(`已创建「${person}」`);
  } catch (e) { toast('创建失败：' + e.message); }
};
$('personInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('btnCreate').click();
});

$('stepScript').onclick = () => requestStep('script');
$('stepImages').onclick = () => requestStep('images');
$('stepVideos').onclick = () => requestStep('videos');
$('stepTts').onclick = () => requestStep('tts');
$('stepRender').onclick = () => requestStep('render');

$('btnCopyPrompt').onclick = async () => {
  const text = state.promptText || '';
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove();
  }
  toast('提示词已复制，粘贴到对话框发给我');
};

$('btnSaveScenes').onclick = async () => {
  try {
    await api(`/api/projects/${state.current.id}/scenes`, {
      method: 'PUT', body: JSON.stringify({ scenes: state.current.scenes }),
    });
    markDirty(false);
    toast('剧本已保存');
    renderProject();
  } catch (e) { toast(e.message); }
};

$('btnFramesFromVideos').onclick = async () => {
  const btn = $('btnFramesFromVideos');
  btn.disabled = true;
  btn.textContent = '截帧中…';
  try {
    const r = await api(`/api/projects/${state.current.id}/frames`, {
      method: 'POST', body: JSON.stringify({}),
    });
    const n = r.count || 0;
    const skip = (r.skipped || []).length;
    const bad = (r.failed || []).length;
    toast(`已截 ${n} 张${skip ? ` · 跳过 ${skip}（已有图）` : ''}${bad ? ` · 失败 ${bad}` : ''}`);
    state.current = await api(`/api/projects/${state.current.id}`);
    renderProject();
  } catch (e) {
    toast('截帧失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '全部从视频截帧';
  }
};

$('btnAddScene').onclick = () => {
  const scenes = state.current.scenes;
  scenes.push({
    index: scenes.length + 1, year: '', age: '', title: '新分镜',
    narration: '', duration: '', sound: '', image_prompt: '', video_prompt: '',
    image_path: '', video_path: '', audio_path: '',
    image_status: 'pending', video_status: 'pending',
  });
  renderScenes();
  updateSteps();
  markDirty(true);
  $('scenes').lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

$('pTitle').addEventListener('change', async () => {
  await api(`/api/projects/${state.current.id}`, {
    method: 'PATCH', body: JSON.stringify({ title: $('pTitle').value }),
  });
  state.current.title = $('pTitle').value;
  loadProjects(state.current.id);
});

$('btnSaveSettings').onclick = async () => {
  const r = await api(`/api/projects/${state.current.id}`, {
    method: 'PATCH', body: JSON.stringify({
      voice: $('voiceSel').value,
      rate: $('rateSel').value,
      aspect: $('aspectSel').value,
      crop_bottom: Number($('cropBottom').value || 0),
      burn_subtitles: $('subSel').value === '1',
      bgm_volume: Number($('bgmVol').value),
    }),
  });
  state.current = await api(`/api/projects/${state.current.id}`);
  renderProject();
  toast(r.audio_dropped ? `设置已保存（已清除 ${r.audio_dropped} 条旧配音，需重新配音）` : '设置已保存');
};

// 改画面比例/音色时不落库，只在保存时生效；这里给即时反馈
$('aspectSel').onchange = () => {
  const t = $('aspectSel').value === 'landscape' ? '横屏 1920×1080' : '竖屏 1080×1920';
  toast(`画面切到${t}，点「保存设置」后生效`);
};

$('subSel').onchange = () => {
  const on = $('subSel').value === '1';
  toast(on ? '将烧录自配旁白字幕，点「保存设置」后生效' : '不烧录字幕，直接透传视频自带字幕，点「保存设置」后生效');
};

$('bgmVol').oninput = () => { $('bgmVolVal').textContent = Number($('bgmVol').value).toFixed(2); };

$('btnBgm').onclick = () => $('bgmFile').click();
$('bgmFile').onchange = async () => {
  const f = $('bgmFile').files[0];
  if (!f) return;
  const data = await readAsDataURL(f);
  await api(`/api/projects/${state.current.id}/asset`, {
    method: 'POST',
    body: JSON.stringify({ index: 0, kind: 'bgm', filename: f.name, data }),
  });
  state.current = await api(`/api/projects/${state.current.id}`);
  renderProject();
  toast('BGM 已上传');
};

$('btnDelete').onclick = async () => {
  if (!confirm(`删除项目「${state.current.person}」？所有素材一并删除，不可恢复。`)) return;
  await api(`/api/projects/${state.current.id}`, { method: 'DELETE' });
  state.current = null;
  await loadProjects();
  toast('已删除');
};

/* ---------------- 启动 ---------------- */

(async function init() {
  if (CULTURE_MODE) applyCultureBranding();
  await loadVoices();
  await loadProjects(QS.get('p') || undefined);
  try {
    const h = await api('/api/health');
    $('health').textContent = `ffmpeg ${h.ffmpeg ? '就绪' : '缺失'} · 待处理任务 ${h.pending_tasks}`;
  } catch (e) { $('health').textContent = '服务未连接'; }
})();
