// Oopz 登录助手
//
//   node tools/oopz_login.js              # 有头模式（本地电脑用，最省事）
//   node tools/oopz_login.js --headless   # 无头模式（服务器用，配合截图/远程查看）
//
// 原理：登录成功后，Web 端每个 API 请求都会带 Oopz-Signature(=token) / Oopz-Person(=uid)，
//       脚本在网络层把这些凭证截下来写入 oopz_config.json，无需手动 F12 复制。
//
// 注意：Oopz 对短信登录 / 密码重置强制腾讯滑动拼图人机验证，脚本无法代过，
//       所以登录这一步必须有人工介入一次；之后服务器即可完全无头自动签到。

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/snap/bin/chromium',
].filter(Boolean);

const HEADLESS = process.argv.includes('--headless') || process.env.OOPZ_HEADLESS === '1';
const PORT = Number(process.env.OOPZ_CDP_PORT || 9777);
const PROFILE = process.env.OOPZ_PROFILE || path.join(os.tmpdir(), 'oopz-login-profile');
const CONFIG = path.join(__dirname, '..', 'oopz_config.json');
const SHOT_DIR = path.join(__dirname, '..');
const WAIT_MINUTES = Number(process.env.OOPZ_LOGIN_WAIT || 8);
const LOGIN_URL = process.env.OOPZ_LOGIN_URL || 'https://web.oopz.cn/#/login';

const sleep = ms => new Promise(r => setTimeout(r, ms));

const HOOK = `
(function(){
  window.__oopzLogin = { token:null, uid:null, seen:[] };
  function scan(url, headers){
    try{
      var h = {};
      if (headers && headers.forEach) headers.forEach(function(v,k){ h[String(k).toLowerCase()] = v; });
      else if (headers && typeof headers === 'object') { for (var k in headers) h[String(k).toLowerCase()] = headers[k]; }
      var sig = h['oopz-signature'] || h['xx_signature'];
      var person = h['oopz-person'] || h['oopz-uid'];
      if (sig && String(sig).length > 20) {
        window.__oopzLogin.token = String(sig);
        window.__oopzLogin.uid = person != null ? String(person) : '';
        window.__oopzLogin.seen.push({ url: String(url), uid: String(person) });
      }
    }catch(e){}
  }
  var oOpen = XMLHttpRequest.prototype.open, oSet = XMLHttpRequest.prototype.setRequestHeader, oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; this.__h={}; return oOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function(k,v){ try{ this.__h[k]=v; }catch(e){} return oSet.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(b){ try{ scan(this.__u, this.__h); }catch(e){} return oSend.apply(this, arguments); };
  if (window.fetch) {
    var of = window.fetch;
    window.fetch = function(input, init){
      try { scan((input && input.url) || input, (init && init.headers) || (input && input.headers)); } catch(e){}
      return of.apply(this, arguments);
    };
  }
})();
`;

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map();
    ws.onmessage = ev => { const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) { const r = this.pending.get(m.id); this.pending.delete(m.id); r(m); } }; }
  send(method, params = {}) { const id = ++this.id;
    return new Promise(res => { this.pending.set(id, res); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result && r.result.exceptionDetails) return '__ERR__';
    return r.result && r.result.result ? r.result.result.value : null;
  }
  async screenshot(file) {
    const s = await this.send('Page.captureScreenshot', { format: 'png' });
    if (s.result && s.result.data) { fs.writeFileSync(file, Buffer.from(s.result.data, 'base64')); return true; }
    return false;
  }
}

(async () => {
  const chromePath = CHROME_CANDIDATES.find(p => { try { return fs.existsSync(p); } catch { return false; } });
  if (!chromePath) {
    console.error('[!] 未找到 Chrome / Chromium。可用环境变量 CHROME_PATH 指定路径。');
    process.exit(1);
  }

  const args = [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${PROFILE}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=Translate',
    '--window-size=1280,900',
  ];
  if (HEADLESS) args.push('--headless=new', '--no-sandbox', '--disable-gpu');
  args.push(LOGIN_URL);

  console.log(`[*] 启动浏览器（${HEADLESS ? '无头' : '有头'}模式）: ${chromePath}`);
  if (fs.existsSync(PROFILE)) { try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch {} }
  const chrome = spawn(chromePath, args, { stdio: 'ignore' });

  let target = null;
  for (let i = 0; i < 80; i++) {
    await sleep(500);
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/list`); const list = await r.json();
      target = list.find(t => t.type === 'page' && t.url.startsWith('http'));
      if (target && target.webSocketDebuggerUrl) break; } catch {}
  }
  if (!target) { console.error('[!] 浏览器未就绪'); try { chrome.kill(); } catch {} process.exit(1); }

  const cdp = new CDP(await new Promise((res, rej) => {
    const ws = new WebSocket(target.webSocketDebuggerUrl); ws.onopen = () => res(ws); ws.onerror = () => rej(new Error('ws fail'));
  }));
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: HOOK });
  await cdp.eval(HOOK);

  console.log(`[*] 已打开 ${LOGIN_URL}`);
  if (HEADLESS) {
    const shot = path.join(SHOT_DIR, 'login_screen.png');
    await sleep(18000);
    if (await cdp.screenshot(shot)) console.log(`[*] 当前页面截图: ${shot}（可下载查看/扫码）`);
  }
  console.log('[*] 请完成登录：手机号+验证码 / 手机号+密码 / 微信扫码');
  console.log(`[*] 最长等待 ${WAIT_MINUTES} 分钟 ...\n`);

  const deadline = Date.now() + WAIT_MINUTES * 60 * 1000;
  let saved = false, tick = 0;
  while (Date.now() < deadline) {
    await sleep(2000);
    tick++;
    // 无头模式每 30s 刷新一次截图，便于远程观察验证码/二维码
    if (HEADLESS && tick % 15 === 0) {
      await cdp.screenshot(path.join(SHOT_DIR, 'login_screen.png'));
    }
    let snap;
    try { snap = await cdp.eval('JSON.stringify(window.__oopzLogin || null)'); } catch { continue; }
    if (!snap || snap === 'null' || snap === '__ERR__') continue;
    let obj; try { obj = JSON.parse(snap); } catch { continue; }
    if (obj && obj.token) {
      let cfg = {};
      try { if (fs.existsSync(CONFIG)) cfg = JSON.parse(fs.readFileSync(CONFIG, 'utf8')); } catch {}
      cfg.token = obj.token;
      cfg.uid = obj.uid || cfg.uid || '';
      cfg.platform = 'windows';
      cfg.channel = 'Web';
      cfg.app_version_number = '88053';
      cfg.obtained_at = new Date().toISOString();
      fs.writeFileSync(CONFIG, JSON.stringify(cfg, null, 2));
      console.log('\n[+] 登录成功，凭证已保存！');
      console.log(`    token = ${String(obj.token).slice(0, 24)}... (${String(obj.token).length} 字符)`);
      console.log(`    uid   = ${obj.uid}`);
      console.log(`    文件  = ${CONFIG}`);
      saved = true;
      break;
    }
  }

  if (!saved) console.log('\n[!] 等待超时，未捕获到登录凭证。可重新运行本脚本。');
  try { chrome.kill(); } catch {}
  await sleep(600);
  try { if (fs.existsSync(PROFILE)) fs.rmSync(PROFILE, { recursive: true, force: true }); } catch {}
  process.exit(saved ? 0 : 1);
})();
