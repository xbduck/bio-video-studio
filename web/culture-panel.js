/* 企业文化专栏 · 导演 / 剪辑辅助面板
 *   剧本通读（分镜脚本 / 配音稿 + 提示词 + 时长节奏）
 *   角色档案（读 dingding-city/角色圣经.md）
 *   交付自检（母版硬约束逐条核对）
 *   以及 SRT 字幕 / 剪辑单 CSV / 剧本 Markdown 导出
 * 由 app.js 在 cat=dingding-city 模式下 init()。
 */
(function () {
  'use strict';

  const CSS = `
  /* 标题栏操作区改成单行（原来只有「删除」一个按钮，堆叠看不出来） */
  .phead-actions{display:flex;align-items:center;gap:6px;flex:0 0 auto}
  .cp-overlay{position:fixed;inset:0;z-index:80;background:rgba(34,31,27,.32);
    display:flex;justify-content:flex-end}
  .cp-drawer{width:min(1020px,95vw);height:100%;background:var(--panel);
    display:flex;flex-direction:column;border-left:1px solid var(--line);
    box-shadow:-14px 0 44px rgba(34,31,27,.16);animation:cpIn .18s ease-out}
  @keyframes cpIn{from{transform:translateX(24px);opacity:.6}to{transform:none;opacity:1}}

  .cp-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;
    padding:16px 20px 12px;border-bottom:1px solid var(--line);flex:0 0 auto}
  .cp-kicker{font-size:11.5px;color:var(--ink-3);letter-spacing:.04em;margin-bottom:3px}
  .cp-head h2{font-size:17px;line-height:1.35}
  .cp-head-right{display:flex;align-items:center;gap:10px;flex:0 0 auto}
  .cp-tabs{display:flex;background:var(--panel-2);border:1px solid var(--line);
    border-radius:9px;padding:3px;gap:2px}
  .cp-tabs button{border:0;background:transparent;padding:5px 12px;border-radius:7px;
    font-size:12.5px;color:var(--ink-2);cursor:pointer;white-space:nowrap}
  .cp-tabs button.on{background:var(--panel);color:var(--accent);font-weight:650;
    box-shadow:0 1px 2px rgba(34,31,27,.08)}
  .cp-x{border:0;background:transparent;font-size:22px;line-height:1;color:var(--ink-3);
    cursor:pointer;padding:2px 6px;border-radius:8px}
  .cp-x:hover{background:var(--panel-2);color:var(--ink)}

  .cp-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
    padding:10px 20px;border-bottom:1px solid var(--line);background:var(--panel-2);flex:0 0 auto}
  .cp-toolbar .grow{flex:1 1 0%;min-width:0}
  .cp-toolbar .tip{font-size:12.5px;color:var(--ink-3);flex:1 1 0%;min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cp-toolbar label{font-size:12.5px;color:var(--ink-2);display:flex;align-items:center;gap:5px;cursor:pointer}
  .cp-seg{display:flex;border:1px solid var(--line-2);border-radius:8px;overflow:hidden;background:var(--panel)}
  .cp-seg button{border:0;background:transparent;padding:5px 11px;font-size:12.5px;
    color:var(--ink-2);cursor:pointer}
  .cp-seg button.on{background:var(--accent-soft);color:var(--accent);font-weight:650}
  .cp-body{flex:1 1 auto;overflow-y:auto;padding:18px 20px 60px}

  /* ---- 概要 ---- */
  .cp-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:8px;margin-bottom:14px}
  .cp-stat{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:9px 11px}
  .cp-stat .k{font-size:11px;color:var(--ink-3)}
  .cp-stat .v{font-size:16px;font-weight:650;margin-top:1px}
  .cp-stat .v small{font-size:11px;font-weight:500;color:var(--ink-3);margin-left:2px}

  /* ---- 时长节奏条 ---- */
  .cp-rhythm{display:flex;gap:2px;align-items:flex-end;height:34px;margin-bottom:16px}
  .cp-rhythm i{flex:1 1 auto;background:var(--line-2);border-radius:3px 3px 0 0;position:relative;
    transition:.12s}
  .cp-rhythm i.ok{background:#9dbfa9}
  .cp-rhythm i.warn{background:#e2c07a}
  .cp-rhythm i:hover{background:var(--accent)}

  /* ---- 分镜条目 ---- */
  .cp-scene{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px;
    background:var(--panel)}
  .cp-scene:hover{border-color:var(--line-2)}
  .cp-scene-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}
  .cp-no{font-size:11px;font-weight:700;color:#fff;background:var(--ink);border-radius:5px;
    padding:1px 6px;font-variant-numeric:tabular-nums}
  .cp-scene-title{font-weight:650;font-size:14px}
  .cp-tc{font-size:11.5px;color:var(--ink-3);font-variant-numeric:tabular-nums;
    background:var(--panel-2);border:1px solid var(--line);border-radius:5px;padding:0 6px}
  .cp-badge{font-size:10.5px;padding:1px 7px;border-radius:20px;border:1px solid var(--line);
    color:var(--ink-2);background:var(--panel-2)}
  .cp-badge.ok{color:var(--ok);background:var(--ok-soft);border-color:#cfe3d6}
  .cp-badge.warn{color:var(--warn);background:var(--warn-soft);border-color:#ecdcb8}
  .cp-badge.bad{color:var(--accent);background:var(--accent-soft);border-color:#f0d7cf}
  .cp-nar{margin:0 0 8px;font-size:14.5px;line-height:1.85;color:var(--ink)}
  .cp-dlg{color:var(--accent);font-weight:600}
  .cp-snds{display:flex;gap:6px;flex-wrap:wrap}
  .cp-snd{font-size:11.5px;color:var(--ink-2);background:var(--panel-2);
    border:1px solid var(--line);border-radius:6px;padding:2px 7px}
  .cp-snd b{color:var(--ink);font-weight:650;margin-right:4px}
  .cp-details{margin-top:9px}
  .cp-details summary{font-size:12px;color:var(--ink-2);cursor:pointer;user-select:none}
  .cp-details summary:hover{color:var(--accent)}
  .cp-code{margin:7px 0 0;padding:9px 11px;background:var(--panel-2);border:1px solid var(--line);
    border-radius:8px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
    line-height:1.65;color:var(--ink-2);white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto}

  /* ---- 配音稿 ---- */
  .cp-line{margin-bottom:18px}
  .cp-line .tc{font-size:11px;color:var(--ink-3);font-variant-numeric:tabular-nums;
    display:flex;gap:8px;align-items:center;margin-bottom:3px}
  .cp-line p{margin:0;font-size:15.5px;line-height:1.9}

  /* ---- 角色 ---- */
  .cp-char{border:1px solid var(--line);border-radius:11px;padding:15px 16px;margin-bottom:13px}
  .cp-char-head{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
  .cp-char-head h3{font-size:16px}
  .cp-char-note{font-size:11.5px;color:var(--ink-2);background:var(--panel-2);
    border:1px solid var(--line);border-radius:20px;padding:1px 9px}
  .cp-char-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
  .cp-ava-wrap{position:relative;width:84px;aspect-ratio:1/1;flex:0 0 auto;border-radius:14px;
    overflow:hidden;border:1px solid var(--line);background:var(--panel-2);cursor:zoom-in}
  .cp-ava-wrap:hover{border-color:var(--accent)}
  .cp-ava-wrap::after{content:"🔍";position:absolute;right:5px;bottom:4px;font-size:11px;
    background:rgba(0,0,0,.45);color:#fff;border-radius:6px;padding:1px 4px;line-height:1.4;
    opacity:0;transition:opacity .15s}
  .cp-ava-wrap:hover::after{opacity:1}
  .cp-ava{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 28%;display:block}
  .cp-ava-col{display:flex;flex-direction:column;align-items:center;gap:5px;flex:0 0 auto}
  .cp-ava-src{font-size:10.5px;color:var(--ink-3);line-height:1.2;text-align:center;max-width:84px}
  .cp-ava-src.ep{color:var(--accent)}
  .cp-ava.mono{position:static;display:flex;align-items:center;justify-content:center;
    width:84px;height:84px;aspect-ratio:auto;font-size:26px;font-weight:700;color:var(--ink-3);
    letter-spacing:.02em;border-radius:14px}
  .cp-lightbox{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;
    background:rgba(0,0,0,.86);cursor:zoom-in}
  .cp-lightbox.open{display:flex}
  .cp-lightbox img{width:92vw;height:88vh;object-fit:contain;
    filter:drop-shadow(0 20px 60px rgba(0,0,0,.5));transition:transform .12s ease-out;transform-origin:0 0}
  .cp-lightbox.zoomed{cursor:zoom-out}
  .cp-lightbox.zoomed img{cursor:zoom-out}
  .cp-lightbox .cp-lb-tip{position:absolute;top:14px;left:50%;transform:translateX(-50%);
    color:#fff;font-size:12.5px;background:rgba(0,0,0,.5);padding:5px 12px;border-radius:20px}
  .cp-lightbox .cp-lb-close{position:absolute;top:14px;right:16px;color:#fff;font-size:22px;
    cursor:pointer;background:rgba(0,0,0,.4);width:36px;height:36px;border-radius:50%;
    display:flex;align-items:center;justify-content:center}
  .cp-kv{width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:10px}
  .cp-kv td{border-top:1px solid var(--line);padding:6px 8px 6px 0;vertical-align:top;line-height:1.65}
  .cp-kv td:first-child{width:132px;color:var(--ink-2);font-weight:600;white-space:nowrap}
  .cp-prompt-head{display:flex;align-items:center;justify-content:space-between;
    font-size:11.5px;color:var(--ink-3);margin-bottom:2px}
  .cp-red{margin:9px 0 0;padding-left:18px;font-size:12.2px;color:var(--ink-2);line-height:1.75}
  .cp-red li{margin-bottom:2px}
  .cp-sub{margin:22px 0 10px;font-size:13px;font-weight:650;color:var(--ink-2);
    display:flex;align-items:center;gap:8px}
  .cp-sub::after{content:'';flex:1 1 auto;height:1px;background:var(--line)}

  /* ---- 自检 ---- */
  .cp-verdict{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:11px;
    border:1px solid var(--line);margin-bottom:14px;background:var(--panel-2)}
  .cp-verdict .big{font-size:26px;font-weight:700;line-height:1}
  .cp-verdict .txt{font-size:12.5px;color:var(--ink-2)}
  .cp-verdict.ok{background:var(--ok-soft);border-color:#cfe3d6}
  .cp-verdict.ok .big{color:var(--ok)}
  .cp-verdict.bad{background:var(--accent-soft);border-color:#f0d7cf}
  .cp-verdict.bad .big{color:var(--accent)}
  .cp-verdict.warn{background:var(--warn-soft);border-color:#ecdcb8}
  .cp-verdict.warn .big{color:var(--warn)}
  .cp-item{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--line);align-items:flex-start}
  .cp-item:last-child{border-bottom:0}
  .cp-dot{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:0 0 8px;background:var(--line-2)}
  .cp-item.pass .cp-dot{background:var(--ok)}
  .cp-item.warn .cp-dot{background:#d9a63c}
  .cp-item.fail .cp-dot{background:var(--accent)}
  .cp-item-main{flex:1 1 auto;min-width:0}
  .cp-item-main b{font-size:13px;font-weight:600}
  .cp-item-main .d{font-size:12px;color:var(--ink-3);margin-top:1px;line-height:1.6}
  .cp-chips{display:flex;gap:4px;flex-wrap:wrap;max-width:190px;justify-content:flex-end}
  .cp-chip{font-size:10.5px;border:1px solid var(--line-2);background:var(--panel);
    border-radius:5px;padding:0 5px;color:var(--ink-2);cursor:pointer;font-variant-numeric:tabular-nums}
  .cp-chip:hover{border-color:var(--accent);color:var(--accent)}
  .cp-foot{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}

  .cp-btn{border:1px solid var(--line-2);background:var(--panel);border-radius:8px;
    padding:5px 11px;font-size:12.5px;cursor:pointer;color:var(--ink)}
  .cp-btn:hover{border-color:var(--accent);color:var(--accent)}
  .cp-btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}
  .cp-btn.pri:hover{background:#9d3623;color:#fff}

  .cp-empty{padding:40px 10px;text-align:center;color:var(--ink-3);font-size:13px}

  /* 打印：只留抽屉内容，给导演出纸质稿 */
  @media print {
    body > *:not(#cpOverlay){display:none !important}
    #cpOverlay{position:static !important;background:#fff !important;display:block !important;
      backdrop-filter:none !important}
    #cpOverlay.hidden{display:none !important}
    .cp-drawer{width:100% !important;max-width:none !important;height:auto !important;
      border:0 !important;box-shadow:none !important;animation:none !important}
    .cp-toolbar,.cp-head-right{display:none !important}
    .cp-body{overflow:visible !important;height:auto !important;padding:0 !important}
    .cp-scene,.cp-char,.cp-item{break-inside:avoid}
  }
  `;

  let ctx = null;          // { api, esc, toast }
  let mode = 'script';     // script | chars | check
  let opt = { pure: false, prompts: false };
  let charsCache = null;
  let checkCache = null;
  let prompts = [];        // 角色英文提示词，供复制按钮按下标取
  let lastId = null;

  /* ---------------- 小工具 ---------------- */

  const esc = (s) => (ctx ? ctx.esc(s) : String(s == null ? '' : s));
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const mmss = (sec) => {
    const s = Math.max(0, Math.round(num(sec)));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };
  const dur1 = (v) => {
    const n = Math.round(num(v) * 10) / 10;
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  };
  function words(text) {
    const t = String(text || '');
    const cjk = (t.match(/[\u3400-\u9fff]/g) || []).length;
    const lat = (t.match(/[A-Za-z0-9]+/g) || []).length;
    return cjk + lat;
  }
  function metas(p) {
    let t = 0;
    return (p.scenes || []).map((s, i) => {
      const d = num(s.duration);
      const w = words(s.narration);
      const m = {
        index: s.index || i + 1, title: s.title || '',
        duration: d, start: t, end: t + d,
        words: w, rate: d > 0 ? Math.round((w / d) * 100) / 100 : 0,
      };
      t += d;
      return m;
    });
  }
  const rateCls = (r) => (r > 4.3 ? 'bad' : r > 4.0 ? 'warn' : 'ok');

  function narHtml(text) {
    return esc(text).replace(/「[^」]{0,200}」/g, (m) => `<span class="cp-dlg">${m}</span>`);
  }
  function soundHtml(s) {
    if (!s) return '';
    return String(s).split(/[；;]/).map((x) => x.trim()).filter(Boolean).map((part) => {
      const m = part.match(/^([^：:]{1,6})[：:]([\s\S]*)$/);
      if (m) return `<span class="cp-snd"><b>${esc(m[1].trim())}</b>${esc(m[2].trim())}</span>`;
      return `<span class="cp-snd">${esc(part)}</span>`;
    }).join('');
  }
  function copy(text, tip) {
    const done = () => ctx.toast(tip || '已复制');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallback());
    } else fallback();
    function fallback() {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { ctx.toast('复制失败'); }
      ta.remove();
    }
  }

  /* ---------------- 骨架 ---------------- */

  function injectStyle() {
    if (document.getElementById('cp-style')) return;
    const st = document.createElement('style');
    st.id = 'cp-style';
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function ensureDom() {
    if (document.getElementById('cpOverlay')) return;
    const wrap = document.createElement('div');
    wrap.id = 'cpOverlay';
    wrap.className = 'cp-overlay hidden';
    wrap.innerHTML = `
      <div class="cp-drawer" role="dialog" aria-modal="true" aria-label="剧本与角色">
        <header class="cp-head">
          <div class="cp-head-main">
            <div class="cp-kicker" id="cpKicker"></div>
            <h2 id="cpTitle">—</h2>
          </div>
          <div class="cp-head-right">
            <div class="cp-tabs" id="cpTabs">
              <button data-tab="script">剧本</button>
              <button data-tab="chars">角色</button>
              <button data-tab="check">自检</button>
            </div>
            <button class="cp-x" id="cpClose" title="关闭（Esc）">×</button>
          </div>
        </header>
        <div class="cp-toolbar" id="cpToolbar"></div>
        <div class="cp-body" id="cpBody"></div>
      </div>`;
    document.body.appendChild(wrap);

    // 角色图放大灯箱（点击头像看细节）
    const lb = document.createElement('div');
    lb.className = 'cp-lightbox';
    lb.id = 'cpLightbox';
    lb.innerHTML = `<div class="cp-lb-close" title="关闭（Esc）">×</div>
      <div class="cp-lb-tip">点击图片放大 / 缩小 · 滚轮缩放 · 拖动平移</div>
      <img alt="角色大图">`;
    document.body.appendChild(lb);
    const lbImg = lb.querySelector('img');
    let lbZoom = 1, lbX = 0, lbY = 0;
    const lbApply = () => { lbImg.style.transform = `translate(${lbX}px,${lbY}px) scale(${lbZoom})`; };
    const lbSetZoom = (z, cx, cy) => {
      z = Math.max(1, Math.min(6, z));
      if (z === 1) { lbZoom = 1; lbX = 0; lbY = 0; lb.classList.remove('zoomed'); }
      else {
        // 以鼠标位置为缩放中心
        const r = lbImg.getBoundingClientRect();
        const ox = (cx - r.left) / lbZoom, oy = (cy - r.top) / lbZoom;
        lbX -= (cx - r.left) - ox * z; lbY -= (cy - r.top) - oy * z;
        lbZoom = z; lb.classList.add('zoomed');
      }
      lbApply();
    };
    lb.addEventListener('click', (e) => {
      if (e.target === lb || e.target.classList.contains('cp-lb-close')) { closeLightbox(); return; }
      if (e.target === lbImg) {
        if (lbZoom > 1) lbSetZoom(1);
        else { const r = lb.getBoundingClientRect(); lbSetZoom(2.4, r.width / 2, r.height / 2); }
      }
    });
    lb.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = lb.getBoundingClientRect();
      lbSetZoom(lbZoom * (e.deltaY < 0 ? 1.2 : 0.83), e.clientX, e.clientY);
    }, { passive: false });
    lb.addEventListener('mousemove', (e) => {
      if (lbZoom > 1 && (e.buttons & 1)) {
        lbX += e.movementX; lbY += e.movementY; lbApply();
      }
    });
    function closeLightbox() { lb.classList.remove('open', 'zoomed'); lbZoom = 1; lbX = 0; lbY = 0; }
    window.__cpCloseLightbox = closeLightbox;

    wrap.addEventListener('click', (e) => { if (e.target === wrap) close(); });
    wrap.querySelector('#cpClose').onclick = close;
    wrap.querySelectorAll('#cpTabs button').forEach((b) => {
      b.onclick = () => { mode = b.dataset.tab; paint(); };
    });
    wrap.querySelector('#cpToolbar').addEventListener('click', onToolbarClick);
    wrap.querySelector('#cpBody').addEventListener('click', onBodyClick);
    document.addEventListener('keydown', (e) => {
      const lb = document.getElementById('cpLightbox');
      if (e.key === 'Escape') {
        if (lb && lb.classList.contains('open')) { window.__cpCloseLightbox(); return; }
        if (!wrap.classList.contains('hidden')) close();
      }
    });
  }

  function open(tab) {
    ensureDom();
    mode = tab || mode;
    document.getElementById('cpOverlay').classList.remove('hidden');
    paint();
  }
  function close() {
    const w = document.getElementById('cpOverlay');
    if (w) w.classList.add('hidden');
  }
  const isOpen = () => {
    const w = document.getElementById('cpOverlay');
    return w ? !w.classList.contains('hidden') : false;
  };

  /* ---------------- 顶栏按钮 ---------------- */

  function renderActions() {
    const bar = document.querySelector('.phead-actions');
    if (!bar) return;
    let box = bar.querySelector('.cp-actions');
    if (!box) {
      box = document.createElement('div');
      box.className = 'cp-actions';
      box.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap';
      box.innerHTML = `
        <button class="btn small" data-cp="script" title="通读分镜脚本 / 配音稿，支持导出">剧本</button>
        <button class="btn small" data-cp="chars" title="查看角色档案与英文提示词">角色</button>
        <button class="btn small" data-cp="check" title="按母版硬约束逐条自检">自检</button>`;
      bar.insertBefore(box, bar.firstChild);
      box.addEventListener('click', (e) => {
        const b = e.target.closest('[data-cp]');
        if (b) open(b.dataset.cp);
      });
    }
  }

  /* ---------------- 渲染调度 ---------------- */

  function currentProject() {
    return (window.__cpProject || null);
  }

  function paint() {
    const p = currentProject();
    const drawer = document.querySelector('.cp-drawer');
    if (!p || !drawer) return;
    document.querySelectorAll('#cpTabs button').forEach((b) => {
      b.classList.toggle('on', b.dataset.tab === mode);
    });
    document.getElementById('cpKicker').textContent =
      `企业文化 · ${p.series || '叮叮城故事'} · 导演稿`;
    document.getElementById('cpTitle').textContent = p.title || p.person || '未命名';

    if (mode === 'script') paintScript(p);
    else if (mode === 'chars') paintChars(p);
    else paintCheck(p);
  }

  function setToolbar(html) {
    document.getElementById('cpToolbar').innerHTML = html;
  }
  function setBody(html) {
    document.getElementById('cpBody').innerHTML = html;
    document.getElementById('cpBody').scrollTop = 0;
  }

  /* ---------------- 剧本 ---------------- */

  function paintScript(p) {
    const ms = metas(p);
    const total = ms.reduce((n, m) => n + m.duration, 0);
    const allWords = ms.reduce((n, m) => n + m.words, 0);
    const maxRate = ms.reduce((n, m) => Math.max(n, m.rate), 0);
    // 一张图/一条视频都还没有时，逐镜标「缺图/缺视频」纯噪音；有进度了才提示缺口
    const anyImg = (p.scenes || []).some((s) => s.image_path);
    const anyVid = (p.scenes || []).some((s) => s.video_path);

    setToolbar(`
      <div class="cp-seg">
        <button data-act="view" data-v="scene" class="${opt.pure ? '' : 'on'}">分镜脚本</button>
        <button data-act="view" data-v="pure" class="${opt.pure ? 'on' : ''}">配音稿</button>
      </div>
      <button class="cp-btn ${opt.prompts ? 'pri' : ''}" data-act="prompts" title="展开 / 收起画面与运镜提示词">提示词 ${opt.prompts ? '开' : '关'}</button>
      <span class="grow"></span>
      <button class="cp-btn" data-act="copy">复制</button>
      <button class="cp-btn" data-act="print">打印</button>
      <button class="cp-btn" data-act="dl" data-kind="md">剧本 .md</button>
      <button class="cp-btn" data-act="dl" data-kind="srt">字幕 .srt</button>
      <button class="cp-btn" data-act="dl" data-kind="csv">剪辑单 .csv</button>`);

    const rhythm = ms.map((m) => {
      const h = Math.max(18, Math.min(100, (m.duration / 13) * 100));
      const cls = (m.duration >= 10 && m.duration <= 13) ? 'ok' : 'warn';
      return `<i class="${cls}" style="height:${h}%" title="第${m.index}镜 ${dur1(m.duration)}s"></i>`;
    }).join('');

    const stats = `
      <div class="cp-stats">
        <div class="cp-stat"><div class="k">镜数</div><div class="v">${ms.length}</div></div>
        <div class="cp-stat"><div class="k">总时长</div><div class="v">${mmss(total)}</div></div>
        <div class="cp-stat"><div class="k">平均语速</div><div class="v">${total ? (allWords / total).toFixed(2) : '0'}<small>字/秒</small></div></div>
        <div class="cp-stat"><div class="k">最高语速</div><div class="v" style="color:${maxRate > 4.3 ? 'var(--accent)' : 'var(--ok)'}">${maxRate.toFixed(2)}<small>字/秒</small></div></div>
        <div class="cp-stat"><div class="k">画幅</div><div class="v" style="font-size:13px">${p.aspect === 'landscape' ? '横屏 16:9' : '竖屏 9:16'}</div></div>
      </div>`;

    const bodyHtml = opt.pure
      ? ms.map((m, i) => {
          const s = (p.scenes || [])[i] || {};
          return `<div class="cp-line">
            <div class="tc"><span>${String(m.index).padStart(2, '0')}</span>
              <span>${mmss(m.start)}–${mmss(m.end)}</span><span>${dur1(m.duration)}s</span></div>
            <p>${narHtml(s.narration || '') || '<span class="muted">（本镜无旁白）</span>'}</p>
          </div>`;
        }).join('')
      : ms.map((m, i) => {
          const s = (p.scenes || [])[i] || {};
          const hasImg = !!s.image_path, hasVid = !!s.video_path;
          const badges = [];
          if (m.rate > 4.3) badges.push('<span class="cp-badge bad">语速超限</span>');
          else if (m.rate > 4.0) badges.push('<span class="cp-badge warn">语速偏快</span>');
          if (!(m.duration >= 10 && m.duration <= 13)) badges.push('<span class="cp-badge warn">时长异常</span>');
          if (anyImg && !hasImg) badges.push('<span class="cp-badge">缺图</span>');
          if (anyVid && !hasVid) badges.push('<span class="cp-badge">缺视频</span>');
          const snd = soundHtml(s.sound);
          const prompts = opt.prompts ? `
            <details class="cp-details" open>
              <summary>画面提示词</summary>
              <pre class="cp-code">${esc(s.image_prompt || '')}</pre>
            </details>
            <details class="cp-details">
              <summary>运镜提示词</summary>
              <pre class="cp-code">${esc(s.video_prompt || '')}</pre>
            </details>` : '';
          return `<article class="cp-scene" data-i="${m.index}">
            <div class="cp-scene-top">
              <span class="cp-no">${String(m.index).padStart(2, '0')}</span>
              <span class="cp-scene-title">${esc(m.title.replace(/^第\s*\d+\s*镜\s*[·:：]?\s*/, ''))}</span>
              <span class="cp-tc">${mmss(m.start)}–${mmss(m.end)}</span>
              <span class="cp-badge">${dur1(m.duration)}s</span>
              <span class="cp-badge ${rateCls(m.rate)}">${m.rate} 字/秒</span>
              ${badges.join('')}
            </div>
            <p class="cp-nar">${narHtml(s.narration || '') || '<span class="muted">（本镜无旁白）</span>'}</p>
            ${snd ? `<div class="cp-snds">${snd}</div>` : ''}
            ${prompts}
          </article>`;
        }).join('');

    setBody(stats + `<div class="cp-rhythm">${rhythm}</div>` + (bodyHtml || '<div class="cp-empty">还没有分镜</div>'));
  }

  function scriptPlain(p) {
    const ms = metas(p);
    if (opt.pure) {
      return ms.map((m, i) => {
        const s = (p.scenes || [])[i] || {};
        return `【${m.index}｜${dur1(m.duration)}s】${s.narration || ''}`;
      }).join('\n');
    }
    const head = `${p.title || ''}\n${ms.length} 镜 · 总时长 ${mmss(ms.reduce((n, m) => n + m.duration, 0))}\n`;
    const lines = ms.map((m, i) => {
      const s = (p.scenes || [])[i] || {};
      const out = [
        `第${m.index}镜 ${s.title || ''}　${dur1(m.duration)}s（${mmss(m.start)}–${mmss(m.end)}）`,
        `旁白：${s.narration || ''}`,
      ];
      if (s.sound) out.push(`音效：${s.sound}`);
      if (opt.prompts && s.image_prompt) out.push(`画面：${s.image_prompt}`);
      if (opt.prompts && s.video_prompt) out.push(`运镜：${s.video_prompt}`);
      return out.join('\n');
    });
    return head + '\n' + lines.join('\n\n');
  }

  /* ---------------- 角色 ---------------- */

  async function paintChars(p) {
    setToolbar(`<span class="tip">角色设定来自 dingding-city/角色圣经.md；照片取本集分镜图（avatars/&lt;本集&gt;/），缺图才回落到系列通用图</span>
      <button class="cp-btn" data-act="reload">刷新</button>
      <button class="cp-btn pri" data-act="copy-all-prompts">复制全部提示词</button>`);
    if (!charsCache || charsCache.__pid !== p.id) {
      setBody('<div class="cp-empty">读取角色圣经…</div>');
      try {
        const d = await ctx.api(`/api/culture/characters?project=${encodeURIComponent(p.id)}`);
        d.__pid = p.id;
        charsCache = d;
      }
      catch (e) { setBody(`<div class="cp-empty">读取失败：${esc(e.message)}</div>`); return; }
    }
    const d = charsCache;
    if (!d.exists) { setBody('<div class="cp-empty">找不到 dingding-city/角色圣经.md</div>'); return; }

    const narText = (p.scenes || []).map((s) => s.narration || '').join(' ');
    prompts = d.characters.map((c) => c.prompt_en || '');
    const cast = d.cast || [];

    const isOnStage = (c) => (c.on_stage !== null && c.on_stage !== undefined)
      ? c.on_stage : (!!c.name && narText.includes(c.name));

    const card = (c, i) => {
      const onStage = isOnStage(c);
      const initial = (c.name || '?').trim().slice(0, 1);
      // 有照片就叠在字母底色上；图挂了自动移除，回落到字母，不会出现破图
      // 点头像 → 灯箱放大看细节（data-ava 传原图地址）
      const avatar = `<span class="cp-ava-wrap${c.image ? ' cp-ava-zoom' : ''}"${c.image ? ` data-ava="${esc(c.image)}"` : ''}>
          <span class="cp-ava mono">${esc(initial)}</span>
          ${c.image ? `<img class="cp-ava" src="${esc(c.image)}" alt="${esc(c.name)}" loading="lazy" onerror="this.remove()">` : ''}
        </span>`;
      const srcTag = c.image_source === 'episode'
        ? '<span class="cp-ava-src ep">本集分镜截图</span>'
        : (c.image_source === 'series' ? '<span class="cp-ava-src">系列通用参考图</span>' : '');
      return `<section class="cp-char">
        <div class="cp-char-head">
          <span class="cp-no">${String(i + 1).padStart(2, '0')}</span>
          <div class="cp-ava-col">${avatar}${srcTag}</div>
          <div class="cp-char-title">
            <h3>${esc(c.name)}</h3>
            ${c.note ? `<span class="cp-char-note">${esc(c.note)}</span>` : ''}
            ${onStage ? '<span class="cp-badge ok">本集出场</span>' : '<span class="cp-badge">本集未出场</span>'}
          </div>
        </div>
        ${c.traits.length ? `<table class="cp-kv">${c.traits.map((t) =>
          `<tr><td>${esc(t.k)}</td><td>${esc(t.v)}</td></tr>`).join('')}</table>` : ''}
        ${c.prompt_en ? `
          <div class="cp-prompt-head"><span>英文提示词（出图 / 出视频原样复用）</span>
            <button class="cp-btn" data-copy-prompt="${i}">复制</button></div>
          <pre class="cp-code">${esc(c.prompt_en)}</pre>` : ''}
        ${c.redlines.length ? `<ul class="cp-red">${c.redlines.map((r) =>
          `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
      </section>`;
    };

    const onList = [], offList = [];
    d.characters.forEach((c, i) => (isOnStage(c) ? onList : offList).push(card(c, i)));
    const cards = [
      onList.length ? `<div class="cp-sub">本集出场 · ${cast.length ? esc(cast.join(' / ')) : onList.length + ' 位'}</div>` : '',
      ...onList,
      offList.length ? `<div class="cp-sub">系列其他角色（本集未出场，备造型参考）</div>` : '',
      ...offList,
    ].join('');

    const world = d.world.length ? `<div class="cp-sub">世界视觉</div>
      <table class="cp-kv">${d.world.map((w) =>
        `<tr><td>${esc(w.scene)}</td><td>${esc(w.notes)}</td></tr>`).join('')}</table>` : '';
    const moods = d.moods.length ? `<div class="cp-sub">色调与情绪映射</div>
      <table class="cp-kv">${d.moods.map((m) =>
        `<tr><td>${esc(m.emotion)}</td><td>${esc(m.tone)}${m.example ? `<br><span class="muted small">${esc(m.example)}</span>` : ''}</td></tr>`).join('')}</table>` : '';
    const guards = d.guards.length ? `<div class="cp-sub">产线红线（出图 / 出视频必写）</div>
      <ul class="cp-red">${d.guards.map((g) => `<li>${esc(g)}</li>`).join('')}</ul>` : '';

    setBody(cards + world + moods + guards);
  }

  /* ---------------- 自检 ---------------- */

  async function paintCheck(p) {
    setToolbar(`<span class="tip">按《剧本生成规范_v2》硬约束逐条核对</span>
      <button class="cp-btn" data-act="recheck">重新检查</button>
      <button class="cp-btn" data-act="folders">打开素材文件夹</button>`);
    if (!checkCache) {
      setBody('<div class="cp-empty">检查中…</div>');
      try { checkCache = await ctx.api(`/api/projects/${p.id}/delivery-check`); }
      catch (e) { setBody(`<div class="cp-empty">检查失败：${esc(e.message)}</div>`); return; }
    }
    const r = checkCache;
    const s = r.summary;
    const cls = s.failed ? 'bad' : s.warned ? 'warn' : 'ok';
    const verdictTxt = s.failed
      ? `${s.failed} 项不通过，建议先修再进入出图 / 出视频`
      : s.warned ? `${s.warned} 项提醒，硬约束已全部满足` : '全部通过，可以进入产线';

    const stats = `
      <div class="cp-stats">
        <div class="cp-stat"><div class="k">镜数</div><div class="v">${s.scenes}</div></div>
        <div class="cp-stat"><div class="k">总时长</div><div class="v">${s.total_mmss}</div></div>
        <div class="cp-stat"><div class="k">平均语速</div><div class="v">${s.avg_rate}<small>字/秒</small></div></div>
        <div class="cp-stat"><div class="k">最高语速</div><div class="v">${s.max_rate}<small>字/秒</small></div></div>
        <div class="cp-stat"><div class="k">缺素材</div><div class="v" style="font-size:13px">图 ${s.missing.image} · 视频 ${s.missing.video} · 配音 ${s.missing.audio}</div></div>
      </div>`;

    const items = r.items.map((it) => `
      <div class="cp-item ${it.status}">
        <span class="cp-dot"></span>
        <div class="cp-item-main"><b>${esc(it.label)}</b>
          <div class="d">${esc(it.detail)}</div></div>
        ${it.scenes && it.scenes.length ? `<div class="cp-chips">${it.scenes.slice(0, 12).map((n) =>
          `<span class="cp-chip" data-goto="${n}">${n}</span>`).join('')}</div>` : ''}
      </div>`).join('');

    const timeline = `<div class="cp-sub">分镜时间轴</div>
      <table class="cp-kv">
        <tr><td style="width:auto;color:var(--ink-3)">镜号 / 标题</td><td>时间码</td><td>时长</td><td>语速</td><td>素材</td></tr>
        ${r.scenes.map((m) => `<tr>
          <td style="width:auto"><b>${m.index}</b> ${esc(String(m.title || '').replace(/^第\s*\d+\s*镜\s*[·:：]?\s*/, ''))}</td>
          <td style="color:var(--ink-3)">${mmss(m.start)}–${mmss(m.end)}</td>
          <td>${dur1(m.duration)}s</td>
          <td style="color:${m.rate > 4.3 ? 'var(--accent)' : 'var(--ink-2)'}">${m.rate}</td>
          <td>${m.has_image ? '图' : '—'} ${m.has_video ? '视' : '—'} ${m.has_audio ? '音' : '—'}</td>
        </tr>`).join('')}
      </table>`;

    setBody(`<div class="cp-verdict ${cls}">
        <div class="big">${s.passed}<span style="font-size:13px;font-weight:500">/${r.items.length}</span></div>
        <div class="txt"><b>${esc(verdictTxt)}</b><br>
          <span class="muted">通过 ${s.passed} · 提醒 ${s.warned} · 不通过 ${s.failed}</span></div>
      </div>
      ${stats}
      <div class="cp-sub">逐条核对</div>
      ${items}
      ${timeline}`);
  }

  /* ---------------- 交互 ---------------- */

  async function onToolbarClick(e) {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    const p = currentProject();
    if (!p) return;

    if (act === 'view') {
      opt.pure = b.dataset.v === 'pure';
      paintScript(p);
      return;
    }
    if (act === 'prompts') {
      opt.prompts = !opt.prompts;
      paintScript(p);
      return;
    }
    if (act === 'copy') { copy(scriptPlain(p), '剧本已复制'); return; }
    if (act === 'print') { window.print(); return; }
    if (act === 'dl') {
      const a = document.createElement('a');
      a.href = `/api/projects/${p.id}/export/${b.dataset.kind}`;
      a.rel = 'noopener';
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    if (act === 'reload') { charsCache = null; paintChars(p); return; }
    if (act === 'recheck') { checkCache = null; paintCheck(p); return; }
    if (act === 'folders') {
      try {
        await ctx.api('/api/open-folder', {
          method: 'POST', body: JSON.stringify({ path: `projects/${p.slug}` }),
        });
      } catch (err) { ctx.toast('如无法打开，请手动前往 projects/' + p.slug); }
      return;
    }
    if (act === 'copy-all-prompts') {
      const parts = (charsCache?.characters || [])
        .filter((c) => c.prompt_en)
        .map((c) => `/* ${c.name} */\n${c.prompt_en}`);
      copy(parts.join('\n\n'), '全部角色提示词已复制');
      return;
    }
  }

  function onBodyClick(e) {
    const av = e.target.closest('.cp-ava-zoom');
    if (av) {
      const src = av.dataset.ava;
      const lb = document.getElementById('cpLightbox');
      if (lb && src) {
        lb.querySelector('img').src = src;
        lb.classList.add('open');
        lb.classList.remove('zoomed');
        const img = lb.querySelector('img');
        img.style.transform = 'translate(0,0) scale(1)';
      }
      return;
    }
    const c = e.target.closest('[data-copy-prompt]');
    if (c) {
      const i = Number(c.dataset.copyPrompt);
      const text = prompts[i] || '';
      if (text) copy(text, '角色提示词已复制');
      return;
    }
    const g = e.target.closest('[data-goto]');
    if (g) {
      const n = Number(g.dataset.goto);
      close();
      const el = document.querySelector(`.scene[data-index="${n}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.style.transition = 'box-shadow .3s';
        el.style.boxShadow = '0 0 0 3px var(--accent-soft)';
        setTimeout(() => { el.style.boxShadow = ''; }, 1600);
      }
    }
  }

  /* ---------------- 对外 ---------------- */

  window.CulturePanel = {
    init(context) {
      ctx = context;
      injectStyle();
      ensureDom();
    },
    /** 打开指定页签（script | chars | check），支持 URL 深链 */
    open(tab) {
      if (!ctx) return;
      open(tab);
    },
    /** app.js 每次 renderProject() 后调用 */
    render(project) {
      if (!ctx || !project) return;
      window.__cpProject = project;
      if (lastId && project.id !== lastId) {
        close();
        checkCache = null;
      }
      lastId = project.id;
      renderActions();
      if (isOpen()) paint();
    },
  };
})();
