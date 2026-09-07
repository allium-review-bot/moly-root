// shell.js — viewer 外壳的交互层:页签 · 浮岛收起 · 纯净模式 · 快捷键 · 截图 · 帮助 · 载入幕帘。
// 只动 DOM 与浏览器 API,不碰 three.js 场景;需要运行时能力时走 window.app 上
// viewer.js 暴露的入口(app.requestScreenshot / app.recenter),拿不到就静默降级。
// 与 viewer.js 的解耦靠两个自定义事件:viewer:unit(换角色完成)、viewer:loading(加载起止)。

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

function isEditable(el) {
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
    || el.tagName === 'SELECT' || el.isContentEditable);
}
function typing() {
  return isEditable(document.activeElement);
}

/* ---------------------------------------------------------------- 轻提示 */

function toast(msg, ms = 2400) {
  const box = $('toasts');
  if (!box) return;
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.classList.add('off'), ms);
  setTimeout(() => t.remove(), ms + 400);
}

/* ---------------------------------------------------------------- 页签 */

{
  const tabs = document.querySelectorAll('#tabs .tab');
  const panes = document.querySelectorAll('.panes > .pane');
  for (const tab of tabs) {
    tab.addEventListener('click', () => {
      for (const t of tabs) t.classList.toggle('on', t === tab);
      for (const p of panes) p.classList.toggle('on', p.dataset.pane === tab.dataset.tab);
    });
  }
}

/* ---------------------------------------------------------------- 浮岛收起 */

function syncDockButtons() {
  const l = $('bDockL'), r = $('bDockR');
  if (l) l.setAttribute('aria-pressed', document.body.classList.contains('railL-off') ? 'false' : 'true');
  if (r) r.setAttribute('aria-pressed', document.body.classList.contains('railR-off') ? 'false' : 'true');
}
$('bDockL')?.addEventListener('click', () => { document.body.classList.toggle('railL-off'); syncDockButtons(); });
$('bDockR')?.addEventListener('click', () => { document.body.classList.toggle('railR-off'); syncDockButtons(); });

/* ---------------------------------------------------------------- 纯净模式 */

function chromeOff() { return document.body.classList.contains('chrome-off'); }
function setChrome(off) {
  document.body.classList.toggle('chrome-off', off);
  const recall = $('uiRecall');
  if (recall) recall.hidden = !off;
  const b = $('bChrome');
  if (b) b.setAttribute('aria-pressed', off ? 'false' : 'true');
}
$('bChrome')?.addEventListener('click', () => setChrome(!chromeOff()));
$('uiRecall')?.addEventListener('click', () => setChrome(false));
if (params.get('ui') === '0') setChrome(true);   // ?ui=0 以纯净模式启动(录屏/截图取景用)

/* ---------------------------------------------------------------- 帮助层 */

function helpOpen() { return !$('helpveil')?.hidden; }
function setHelp(open) { const v = $('helpveil'); if (v) v.hidden = !open; }
$('bHelp')?.addEventListener('click', () => setHelp(!helpOpen()));
$('bHelpClose')?.addEventListener('click', () => setHelp(false));
$('helpveil')?.addEventListener('click', (e) => { if (e.target === e.currentTarget) setHelp(false); });

/* ---------------------------------------------------------------- 相机回中 / 截图 */

$('bRecenter')?.addEventListener('click', () => { window.app?.recenter?.(); });

// viewer.js 在帧循环里渲染完成后回调 app.onShot(dataUrl) —— 只有同一帧内同步取帧
// 才不需要 preserveDrawingBuffer。busy 挡住连按,回调一次后自摘。
let shotBusy = false;
function requestShot() {
  const app = window.app;
  if (!app || typeof app.requestScreenshot !== 'function' || shotBusy) return;
  shotBusy = true;
  app.onShot = (dataUrl) => {
    shotBusy = false;
    app.onShot = null;
    saveShot(dataUrl);
  };
  app.requestScreenshot();
}

function saveShot(dataUrl) {
  const chip = document.querySelector('#list .uchip.on');
  const who = (chip?.dataset.who || chip?.textContent?.trim() || 'unit')
    .replace(/[\\/:*?"<>|\s]+/g, '_');
  const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = `chara_${who}_${ts}.png`;
  a.click();
  toast(`已保存截图 ${a.download}`);
}

$('bShot')?.addEventListener('click', requestShot);

/* ---------------------------------------------------------------- 角色筛选 */

{
  const input = $('unitFilter');
  if (input) {
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const chips = document.querySelectorAll('#list .uchip');
      let shown = 0;
      for (const c of chips) {
        // 名字在文本里,代号与组合 slug 在 data-key 里 —— 两路都能筛
        const hit = !q || ((c.textContent + ' ' + (c.dataset.key || '')).toLowerCase().includes(q));
        c.hidden = !hit;
        if (hit) shown++;
      }
      const badge = $('unitCount');
      if (badge) badge.textContent = chips.length ? (q && shown !== chips.length ? `${shown}/${chips.length}` : `${chips.length}`) : '';
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        document.querySelector('#list .uchip:not([hidden])')?.click();
      } else if (e.key === 'Escape') {
        input.value = '';
        input.dispatchEvent(new Event('input'));
        input.blur();   // 清完把焦点还给页面,←→ 换角色立刻可用
      }
    });
  }
}

/* ---------------------------------------------------------------- 角色导航(←→) */

function stepUnit(dir) {
  const chips = [...document.querySelectorAll('#list .uchip:not([hidden])')];
  if (!chips.length) return;
  const cur = chips.findIndex((c) => c.classList.contains('on'));
  const next = chips[(cur + dir + chips.length) % chips.length] || chips[0];
  next.click();
}

/* ---------------------------------------------------------------- 快捷键 */

window.addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  // Esc:先关帮助,再退出纯净模式;其余场景不抢
  if (e.key === 'Escape') {
    if (helpOpen()) { setHelp(false); return; }
    if (chromeOff()) { setChrome(false); return; }
    return;
  }
  if (helpOpen() && e.key !== '?') return;   // 帮助开着时只认 ?(切换)与 Esc(上面已处理)
  if (typing()) return;

  switch (e.key) {
    case ' ':
      e.preventDefault();
      $('bPlay')?.click();
      break;
    case 'ArrowLeft':
      e.preventDefault();
      stepUnit(-1);
      break;
    case 'ArrowRight':
      e.preventDefault();
      stepUnit(1);
      break;
    case 'c':
    case 'C': {
      const orbit = $('bCameraOrbit'), free = $('bCameraFree');
      if (orbit && free) (orbit.classList.contains('on') ? free : orbit).click();
      break;
    }
    case 'h':
    case 'H':
      setChrome(!chromeOff());
      break;
    case 'p':
    case 'P':
      requestShot();
      break;
    case '?':
      setHelp(!helpOpen());
      break;
    default:
      break;
  }
});

/* ---------------------------------------------------------------- 载入幕帘 */

const veil = $('loadveil');
const veilStatus = $('veilStatus');
let veilTimer = 0;

function showVeil(text) {
  if (!veil) return;
  if (text && veilStatus) veilStatus.textContent = text;
  veil.classList.remove('off');
  clearTimeout(veilTimer);
  // 幕帘是体验优化,不是闸门:任何异常路径下最长 25 秒自动收,页面永远不会被它困住。
  veilTimer = setTimeout(() => veil.classList.add('off'), 25000);
}
function hideVeil() {
  clearTimeout(veilTimer);
  veil?.classList.add('off');
}

window.addEventListener('viewer:loading', (e) => {
  const { unit, full, phase, message } = e.detail || {};
  const who = full || `sd_${unit}`;
  if (phase === 'start') showVeil(`${who} 载入中…`);
  else if (phase === 'error') {
    showVeil(message || `${who} 载入失败`);
    veilTimer = setTimeout(hideVeil, 2600);
  }
});
window.addEventListener('viewer:unit', (e) => {
  const { unit, full } = e.detail || {};
  const now = $('nowUnit');
  if (now && unit) {
    now.textContent = full || `sd_${unit}`;
    now.title = `sd_${unit}`;   // 代号是技术标识,悬停可查
  }
  hideVeil();
  // URL 记住角色:刷新/分享都在同一角色上,不打扰历史栈
  try {
    const u = new URL(location.href);
    u.searchParams.set('unit', String(unit));
    history.replaceState(null, '', u);
  } catch { /* 隐私模式等场景下静默放弃 */ }
});

// 兜底:模块系统或数据目录缺失导致 viewer.js 一直不发光时,25 秒后自行收幕。
showVeil('正在准备…');

/* ---------------------------------------------------------------- 面板初始焦点 */

// 键盘流的第一站:打开页面直接 ←→ 就能换角色。
// 不抢焦点给输入框 —— 输入框聚焦会吞掉快捷键。
window.addEventListener('viewer:unit', () => {
  if (!typing() && !chromeOff() && document.activeElement === document.body) {
    document.querySelector('#list .uchip.on')?.focus?.();
  }
}, { once: true });
