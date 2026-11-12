/* 赶路咯 · Hero Cinema v1 — 程序化户外运动背景引擎
   SpaceX 式首页动态背景：暗色实拍感场景、镜头呼吸、多机位剪辑轮播。
   引导页选择运动 → 对应场景即时切换（Cinema.set）。
   零依赖、无外部素材；prefers-reduced-motion 输出静帧。
   后续接入真实赛事视频时，可将 canvas 容器替换为 <video> 列表，引擎接口不变。 */
(function (global) {
'use strict';
var REDUCED = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
var TAU = Math.PI * 2;
var ORDER = ['hiking', 'climbing', 'stream', 'cycling', 'camping', 'skiing', 'orienteering', 'trail-running'];
var LANDSCAPES = ['l-snow', 'l-snow2', 'l-meadow', 'l-fjord', 'l-danxia', 'l-karst', 'l-desert', 'l-grassland', 'l-granite', 'l-waterfall', 'l-volcano', 'l-peakforest', 'l-faultblock', 'l-plateaulake'];
var LIBS = { sports: ORDER, landscape: LANDSCAPES };
var SCENES = {};

/* ---------- 工具 ---------- */
function rr(seed) { // 种子随机（mulberry32）：同一 seed 结果一致，粒子/纹理可复现
  var h = 1779033703 ^ seed.length;
  for (var i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}
function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
function lerp(a, b, k) { return a + (b - a) * k; }
function shuffle(arr) {
  var a = arr.slice();
  for (var i = a.length - 1; i > 0; i--) { var j = (Math.random() * (i + 1)) | 0; var t = a[i]; a[i] = a[j]; a[j] = t; }
  return a;
}
function ridge(x, base, amp, f1, f2, p1, p2, off) { // 分层山脊线
  return base + Math.sin(x * f1 + p1 + off * .35) * amp + Math.sin(x * f2 + p2 + off * .6) * amp * .45;
}
function fillRidge(x, w, h, col, base, amp, f1, f2, p1, p2, off) {
  x.fillStyle = col; x.beginPath(); x.moveTo(-6, h + 6);
  for (var px = -6; px <= w + 6; px += 6) x.lineTo(px, ridge(px, base * h, amp * h, f1, f2, p1, p2, off));
  x.lineTo(w + 6, h + 6); x.closePath(); x.fill();
}
function person(x, px, py, s, col, ph, t, pole) { // 徒步者小人剪影
  x.strokeStyle = col; x.fillStyle = col; x.lineWidth = s * .2; x.lineCap = 'round';
  var bob = Math.sin(t * 2.6 + ph) * s * .08;
  x.beginPath(); x.arc(px, py - s * 1.45 + bob, s * .3, 0, TAU); x.fill();
  x.beginPath();
  x.moveTo(px, py - s * 1.15 + bob); x.lineTo(px, py - s * .5 + bob);
  var lg = Math.sin(t * 2.6 + ph) * s * .3;
  x.moveTo(px, py - s * .5 + bob); x.lineTo(px - s * .3 + lg, py);
  x.moveTo(px, py - s * .5 + bob); x.lineTo(px + s * .3 - lg, py);
  x.moveTo(px, py - s * 1.0 + bob); x.lineTo(px + s * .5, py - s * .7 + bob);
  if (pole) { x.moveTo(px - s * .35, py - s * 1.0 + bob); x.lineTo(px - s * .5, py + s * .1); }
  x.stroke();
}

/* ---------- 场景：徒步 · 远景（层叠山脊 + 逆光 + 雾带 + 徒步者） ---------- */
SCENES.hiking = { label: '徒步 · 山野远景', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#233618'); g.addColorStop(.45, '#16240f'); g.addColorStop(1, '#0a120a');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var sx = w * .74, sy = h * .28;
  var sg = x.createRadialGradient(sx, sy, 0, sx, sy, h * .5);
  sg.addColorStop(0, 'rgba(242,221,125,.5)'); sg.addColorStop(.14, 'rgba(242,221,125,.15)'); sg.addColorStop(1, 'rgba(242,221,125,0)');
  x.fillStyle = sg; x.fillRect(0, 0, w, h);
  x.fillStyle = 'rgba(246,232,160,.9)'; x.beginPath(); x.arc(sx, sy, h * .042, 0, TAU); x.fill();
  fillRidge(x, w, h, '#22381a', .46, .045, .010, .027, 2.2, .8, t * 5);
  /* 雾带：山脊间缓移 */
  var mg = x.createLinearGradient(0, h * .52, 0, h * .66);
  mg.addColorStop(0, 'rgba(220,235,205,0)'); mg.addColorStop(.5, 'rgba(220,235,205,.10)'); mg.addColorStop(1, 'rgba(220,235,205,0)');
  x.fillStyle = mg; x.fillRect(0, h * .52, w, h * .14);
  var mid = h * .60, amp = h * .05;
  fillRidge(x, w, h, '#16260f', .60, .05, .012, .031, 2.1, .7, t * 10);
  /* 徒步者：与中景山层同速平移（镜头横移经过） */
  var off = t * 10;
  for (var i = 0; i < 4; i++) {
    var wx = w * (.12 + i * .24);
    var px = ((wx - off) % (w + 160) + w + 160) % (w + 160) - 80;
    var py = ridge(px, mid, amp, .012, .031, 2.1, .7, t * 10) + 2;
    person(x, px, py, h * .026, '#0a120a', i * 2.3, t, true);
  }
  fillRidge(x, w, h, '#0d180d', .74, .06, .009, .024, 1.4, 2.3, t * 16);
  var fg = x.createLinearGradient(0, h * .7, 0, h);
  fg.addColorStop(0, 'rgba(10,18,10,0)'); fg.addColorStop(1, 'rgba(10,18,10,.85)');
  x.fillStyle = fg; x.fillRect(0, h * .7, w, h * .3);
} };

/* ---------- 场景：攀岩 · 岩壁特写（岩面纹理 + 攀爬者 + 粉笔尘 + 浅景深） ---------- */
SCENES.climbing = { label: '攀岩 · 岩壁特写', _key: '', _rock: null, _holds: null,
  draw: function (x, w, h, t) {
    var S = this;
    if (S._key !== w + 'x' + h) {
      S._key = w + 'x' + h;
      var c = document.createElement('canvas'); c.width = w; c.height = h; var r = c.getContext('2d');
      var g = r.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, '#31421f'); g.addColorStop(.5, '#243118'); g.addColorStop(1, '#1a2510');
      r.fillStyle = g; r.fillRect(0, 0, w, h);
      var R = rr('climb');
      for (var i = 0; i < 26; i++) {
        r.fillStyle = R() > .5 ? 'rgba(0,0,0,.18)' : 'rgba(255,255,255,.05)';
        r.beginPath(); r.ellipse(R() * w, R() * h, R() * w * .05 + 8, R() * h * .05 + 6, R() * TAU, 0, TAU); r.fill();
      }
      r.strokeStyle = 'rgba(0,0,0,.32)';
      for (i = 0; i < 9; i++) {
        r.lineWidth = .6 + R() * 1.8; r.beginPath();
        var cx0 = R() * w, cy0 = R() * h; r.moveTo(cx0, cy0);
        for (var k = 0; k < 5; k++) { cx0 += (R() - .5) * w * .16; cy0 += R() * h * .1; r.lineTo(cx0, cy0); }
        r.stroke();
      }
      for (i = 0; i < 1500; i++) { r.fillStyle = R() > .5 ? 'rgba(0,0,0,.06)' : 'rgba(255,255,255,.03)'; r.fillRect(R() * w, R() * h, 1, 1); }
      S._rock = c;
      S._holds = [];
      var H = rr('holds');
      for (i = 0; i < 14; i++) S._holds.push({ x: w * (.16 + H() * .62), y: h * (.10 + H() * .62), r: h * .012 + H() * h * .01 });
    }
    x.drawImage(S._rock, 0, 0);
    var p;
    for (i = 0; i < S._holds.length; i++) {
      p = S._holds[i];
      x.fillStyle = 'rgba(225,238,205,.14)';
      x.beginPath(); x.ellipse(p.x, p.y, p.r * 1.5, p.r, .3, 0, TAU); x.fill();
    }
    var seg = Math.floor(t * .045), k = t * .045 - seg;
    var ease = k * k * (3 - 2 * k);
    var A = S._holds[seg % 14], B = S._holds[(seg + 1) % 14];
    var hx = lerp(A.x, B.x, ease), hy = lerp(A.y, B.y, ease);
    var bx = hx - w * .02, by = hy + h * .062 + Math.sin(t * 1.3) * 3;
    x.strokeStyle = 'rgba(222,232,200,.22)'; x.lineWidth = 1.4;
    x.beginPath(); x.moveTo(hx + w * .05, -4); x.quadraticCurveTo(hx + w * .075, hy * .5, bx + 6, by); x.stroke();
    x.strokeStyle = 'rgba(11,16,9,.95)'; x.fillStyle = 'rgba(11,16,9,.95)';
    x.lineWidth = h * .012; x.lineCap = 'round';
    x.beginPath(); x.moveTo(bx, by); x.lineTo(hx, hy - h * .014); x.stroke();
    x.beginPath(); x.arc(hx, hy - h * .03, h * .011, 0, TAU); x.fill();
    x.beginPath();
    x.moveTo(hx, hy - h * .014); x.lineTo(A.x, A.y);
    x.moveTo(hx, hy - h * .014); x.lineTo(lerp(A.x, B.x, ease), lerp(A.y, B.y, ease) - 2);
    x.stroke();
    var sw = Math.sin(t * 2.2) * h * .02;
    x.beginPath();
    x.moveTo(bx, by); x.lineTo(bx - w * .03, by + h * .05 + sw);
    x.moveTo(bx, by); x.lineTo(bx + w * .025, by + h * .05 - sw);
    x.stroke();
    for (i = 0; i < 10; i++) {
      p = (t * 1.6 + i * .23) % 1;
      x.fillStyle = 'rgba(235,242,225,' + ((1 - p) * .35) + ')';
      x.beginPath(); x.arc(B.x + Math.sin(p * 9 + i) * 5, B.y + 6 + p * 26, 1 + p * 1.4, 0, TAU); x.fill();
    }
    /* 顶光光束：跟随攀爬者，塑造特写主体 */
    var beam = x.createRadialGradient(hx, hy, 0, hx, hy, h * .34);
    beam.addColorStop(0, 'rgba(240,244,215,.22)');
    beam.addColorStop(.4, 'rgba(240,244,215,.08)');
    beam.addColorStop(1, 'rgba(240,244,215,0)');
    x.fillStyle = beam; x.fillRect(hx - h * .34, hy - h * .34, h * .68, h * .68);
    var fg = x.createRadialGradient(w * .04, h * 1.02, h * .04, w * .04, h * 1.02, h * .42);
    fg.addColorStop(0, 'rgba(5,8,4,.9)'); fg.addColorStop(1, 'rgba(5,8,4,0)');
    x.fillStyle = fg; x.beginPath(); x.arc(w * .02, h * 1.04, h * .36, 0, TAU); x.fill();
    fg = x.createRadialGradient(w * .98, h * .1, h * .05, w * .98, h * .1, h * .4);
    fg.addColorStop(0, 'rgba(5,8,4,.8)'); fg.addColorStop(1, 'rgba(5,8,4,0)');
    x.fillStyle = fg; x.beginPath(); x.arc(w * 1.0, h * .08, h * .32, 0, TAU); x.fill();
  } };

/* ---------- 场景：溯溪 · 溪流（层波 + 高光碎点 + 浪花） ---------- */
SCENES.stream = { label: '溯溪 · 溪谷激流', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#1c2a30'); g.addColorStop(.4, '#122026'); g.addColorStop(1, '#0a1214');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  fillRidge(x, w, h, '#12222a', .34, .05, .011, .028, 1.8, 2.6, t * 4);
  var y0 = h * .46;
  var wg = x.createLinearGradient(0, y0, 0, h);
  wg.addColorStop(0, '#13242a'); wg.addColorStop(1, '#071114');
  x.fillStyle = wg; x.fillRect(0, y0, w, h - y0);
  var R = rr('streamRocks');
  for (var i = 0; i < 4; i++) {
    var rx = w * (.12 + R() * .76), ry = y0 + h * (.1 + R() * .3), rw = w * (.06 + R() * .07);
    x.fillStyle = '#0a1318';
    x.beginPath(); x.ellipse(rx, ry, rw, rw * .55, 0, 0, TAU); x.fill();
    x.fillStyle = 'rgba(220,235,240,.08)';
    x.beginPath(); x.ellipse(rx - rw * .2, ry - rw * .3, rw * .5, rw * .2, 0, 0, TAU); x.fill();
    for (var j = 0; j < 5; j++) {
      p = (t * .55 + j * .21 + i * .13) % 1;
      var ang = (R() - .5) * 1.4;
      x.fillStyle = 'rgba(225,240,245,' + ((1 - p) * .5) + ')';
      x.beginPath(); x.arc(rx + Math.sin(p * TAU + ang) * rw * .8, ry - h * .05 * Math.sin(p * Math.PI) - p * h * .02, 1.3, 0, TAU); x.fill();
    }
  }
  var b, ii, p;
  for (b = 0; b < 4; b++) {
    var yb = y0 + b * h * .12 + h * .04, amp = h * .006 + b * 2, ph = t * (1.1 + b * .45);
    x.fillStyle = 'rgba(180,220,230,' + (.03 + b * .011) + ')';
    x.beginPath(); x.moveTo(0, h + 4);
    for (var px = 0; px <= w; px += 5) x.lineTo(px, yb + Math.sin(px * .045 + ph + b * 2) * amp + Math.sin(px * .013 - ph * .6) * amp * .6);
    x.lineTo(w, h + 4); x.closePath(); x.fill();
  }
  var HL = rr('streamHL');
  for (ii = 0; ii < 34; ii++) {
    var x0 = HL() * w, sp = 26 + HL() * 40, yl = y0 + HL() * (h - y0) * .9;
    var xx = ((x0 + t * sp) % (w + 40)) - 20;
    var al = .08 + .15 * Math.pow(Math.sin(t * 3 + ii * 2.7), 2);
    x.strokeStyle = 'rgba(230,245,250,' + al + ')'; x.lineWidth = 1;
    x.beginPath(); x.moveTo(xx, yl); x.lineTo(xx + 5 + HL() * 9, yl); x.stroke();
  }
  var vg = x.createRadialGradient(w / 2, h / 2, h * .3, w / 2, h / 2, h * .95);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(4,8,10,.5)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 场景：骑行 · 跟拍（滚动树列 + 伏骑剪影 + 速度线） ---------- */
SCENES.cycling = { label: '骑行 · 公路跟拍', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#26211a'); g.addColorStop(.4, '#191711'); g.addColorStop(1, '#0d0f0a');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var sx = w * .3, sy = h * .2;
  var sg = x.createRadialGradient(sx, sy, 0, sx, sy, h * .45);
  sg.addColorStop(0, 'rgba(255,205,120,.4)'); sg.addColorStop(1, 'rgba(255,205,120,0)');
  x.fillStyle = sg; x.fillRect(0, 0, w, h);
  fillRidge(x, w, h, '#1b2013', .40, .04, .012, .03, 1.1, 2.0, t * 60);
  fillRidge(x, w, h, '#121609', .50, .05, .014, .035, 3.3, .9, t * 120);
  /* 树列快速后掠 */
  var sp = 88, off = (t * 240) % sp;
  for (var i = -1; i < w / sp + 1; i++) {
    var tx = i * sp - off;
    var th = h * (.16 + ((i * 37) % 5) * h * .012);
    x.fillStyle = '#0b0f07';
    x.beginPath(); x.moveTo(tx, h * .66); x.lineTo(tx - th * .28, h * .66); x.lineTo(tx, h * .66 - th); x.lineTo(tx + th * .28, h * .66); x.closePath(); x.fill();
    x.fillRect(tx - 1.5, h * .66, 3, h * .06);
  }
  var rg = x.createLinearGradient(0, h * .62, 0, h);
  rg.addColorStop(0, '#13170e'); rg.addColorStop(1, '#0b0e08');
  x.fillStyle = rg; x.fillRect(0, h * .64, w, h * .36);
  /* 路面中线快速后移 */
  x.strokeStyle = 'rgba(224,255,168,.30)';
  for (i = 0; i < 7; i++) {
    var p = ((i + t * .55) % 7) / 7;
    var ly = h * .68 + (h * .32) * p * p;
    x.lineWidth = 1 + p * p * 3;
    x.beginPath(); x.moveTo(w / 2, ly); x.lineTo(w / 2, ly + p * p * h * .06); x.stroke();
  }
  /* 速度线 */
  for (i = 0; i < 6; i++) {
    var q = (t * (.9 + i * .12) + i * .37) % 1;
    x.strokeStyle = 'rgba(240,248,230,' + (.05 + .07 * Math.sin(q * Math.PI)) + ')';
    x.lineWidth = 1;
    var lx = -60 + q * (w + 120), lyy = h * (.3 + ((i * 53) % 50) / 100);
    x.beginPath(); x.moveTo(lx, lyy); x.lineTo(lx + 46 + i * 8, lyy); x.stroke();
  }
  /* 骑手剪影 */
  var cx = w * .46, cy = h * .80, r = h * .05;
  x.strokeStyle = '#070a05'; x.fillStyle = '#070a05'; x.lineWidth = h * .008; x.lineCap = 'round';
  for (i = -1; i <= 1; i += 2) {
    x.beginPath(); x.arc(cx + i * r * 1.5, cy, r, 0, TAU); x.stroke();
    for (var a = 0; a < 3; a++) {
      var an = t * 9 + a * TAU / 3 + (i > 0 ? .5 : 0);
      x.beginPath(); x.moveTo(cx + i * r * 1.5, cy);
      x.lineTo(cx + i * r * 1.5 + Math.cos(an) * r * .8, cy + Math.sin(an) * r * .8); x.stroke();
    }
  }
  x.beginPath();
  x.moveTo(cx - r * 1.5, cy); x.lineTo(cx - r * .3, cy - r * 1.1); x.lineTo(cx + r * .9, cy - r * 1.35); x.lineTo(cx + r * 1.5, cy);
  x.stroke();
  x.beginPath(); x.arc(cx + r * 1.15, cy - r * 1.9, h * .016, 0, TAU); x.fill();
  var legA = Math.sin(t * 7);
  x.beginPath();
  x.moveTo(cx - r * .3, cy - r * 1.1); x.lineTo(cx + legA * r * .7, cy - r * .3 + Math.cos(t * 7) * r * .2);
  x.moveTo(cx - r * .3, cy - r * 1.1); x.lineTo(cx - legA * r * .7, cy - r * .3 - Math.cos(t * 7) * r * .2);
  x.stroke();
  var vg = x.createRadialGradient(w / 2, h / 2, h * .3, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(4,6,3,.55)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 场景：露营 · 夜营（星空 + 帐篷暖光 + 营火 + 炊烟） ---------- */
SCENES.camping = { label: '露营 · 星夜营地', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#0a0f1e'); g.addColorStop(.55, '#0d1410'); g.addColorStop(1, '#0a0f0a');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var S = rr('stars');
  for (var i = 0; i < 90; i++) {
    var sxx = S() * w, syy = S() * h * .62, base = .25 + S() * .6;
    var al = base * (0.45 + 0.55 * Math.pow(Math.sin(t * (0.6 + S() * 1.6) + i * 1.7), 2));
    x.fillStyle = 'rgba(226,236,220,' + al.toFixed(2) + ')';
    x.fillRect(sxx, syy, S() > .85 ? 2 : 1.2, 1.2);
  }
  var mg = x.createLinearGradient(0, 0, w, h * .5);
  mg.addColorStop(0, 'rgba(200,214,240,0)'); mg.addColorStop(.5, 'rgba(200,214,240,.05)'); mg.addColorStop(1, 'rgba(200,214,240,0)');
  x.fillStyle = mg; x.fillRect(0, 0, w, h * .55);
  fillRidge(x, w, h, '#0e1a0c', .62, .03, .02, .05, 4.2, 1.1, t * 2);
  /* 帐篷两座 + 暖光 */
  function tent(cx, base, s, lit) {
    x.fillStyle = '#0a1007';
    x.beginPath(); x.moveTo(cx, base - s); x.lineTo(cx - s * .95, base); x.lineTo(cx + s * .95, base); x.closePath(); x.fill();
    if (lit) {
      var flick = .75 + .25 * Math.sin(t * 6.3) * Math.sin(t * 2.9 + 1);
      var lg = x.createRadialGradient(cx, base - s * .28, 0, cx, base - s * .28, s * .55);
      lg.addColorStop(0, 'rgba(255,178,84,' + (.5 * flick) + ')'); lg.addColorStop(1, 'rgba(255,178,84,0)');
      x.fillStyle = lg; x.beginPath(); x.arc(cx, base - s * .28, s * .55, 0, TAU); x.fill();
      x.fillStyle = 'rgba(255,196,110,' + (.85 * flick) + ')';
      x.beginPath(); x.moveTo(cx, base - s * .42); x.lineTo(cx - s * .3, base); x.lineTo(cx + s * .3, base); x.closePath(); x.fill();
    }
  }
  var gy = h * .8;
  tent(w * .36, gy, h * .15, true);
  tent(w * .62, gy, h * .11, false);
  /* 营火 + 火星 */
  var fx = w * .47, fy = gy + 4;
  var fl = .7 + .3 * Math.sin(t * 9) * Math.sin(t * 3.7);
  var fg = x.createRadialGradient(fx, fy, 0, fx, fy, h * .1);
  fg.addColorStop(0, 'rgba(255,150,60,' + (.55 * fl) + ')'); fg.addColorStop(1, 'rgba(255,150,60,0)');
  x.fillStyle = fg; x.beginPath(); x.arc(fx, fy, h * .1, 0, TAU); x.fill();
  x.fillStyle = 'rgba(255,190,90,' + (.8 * fl) + ')';
  x.beginPath(); x.ellipse(fx, fy - h * .008, h * .008 * fl, h * .02 * fl, 0, 0, TAU); x.fill();
  for (i = 0; i < 12; i++) {
    var p = (t * .8 + i * .13) % 1;
    x.fillStyle = 'rgba(255,170,80,' + ((1 - p) * .7 * fl) + ')';
    x.beginPath(); x.arc(fx + Math.sin(p * 8 + i * 2) * 6, fy - p * h * .1, 1.1, 0, TAU); x.fill();
  }
  /* 炊烟 */
  x.strokeStyle = 'rgba(210,220,215,.06)'; x.lineWidth = 2.5;
  for (i = 0; i < 3; i++) {
    x.beginPath();
    var smx = w * .62 + i * 4;
    x.moveTo(smx, gy - h * .11);
    for (var yy = 0; yy < h * .22; yy += 6) x.lineTo(smx + Math.sin(yy * .05 + t * .9 + i) * 6, gy - h * .11 - yy);
    x.stroke();
  }
  var vg = x.createRadialGradient(w / 2, h / 2, h * .28, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(2,4,8,.6)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 场景：滑雪 · 高山速降（雪雾 + 斜坡 + 滑雪者 + 尾迹） ---------- */
SCENES.skiing = { label: '滑雪 · 高山速降', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#1e2a33'); g.addColorStop(.5, '#141d24'); g.addColorStop(1, '#0c1218');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  x.fillStyle = 'rgba(235,244,248,.55)';
  x.beginPath(); x.arc(w * .68, h * .16, h * .028, 0, TAU); x.fill();
  var sg = x.createRadialGradient(w * .68, h * .16, 0, w * .68, h * .16, h * .3);
  sg.addColorStop(0, 'rgba(235,244,248,.25)'); sg.addColorStop(1, 'rgba(235,244,248,0)');
  x.fillStyle = sg; x.fillRect(0, 0, w, h);
  fillRidge(x, w, h, '#1a2630', .40, .07, .008, .02, 2.5, 1.2, t * 3);
  /* 雪坡（对角下滑面） */
  x.fillStyle = '#141d24';
  x.beginPath(); x.moveTo(0, h * .52);
  for (var px = 0; px <= w; px += 8) x.lineTo(px, h * (.52 + px / w * .18 + Math.sin(px * .01 + 2) * h * .02));
  x.lineTo(w, h); x.lineTo(0, h); x.closePath(); x.fill();
  x.fillStyle = '#0e151b';
  x.beginPath(); x.moveTo(0, h * .74);
  for (px = 0; px <= w; px += 8) x.lineTo(px, h * (.74 + px / w * .14 + Math.sin(px * .014) * h * .015));
  x.lineTo(w, h); x.lineTo(0, h); x.closePath(); x.fill();
  /* 雪花三层 */
  var L;
  for (var l = 0; l < 3; l++) {
    var cnt = 40 + l * 25, sp = .1 + l * .09, sz = 1 + l * .8, al = .5 - l * .12;
    for (var i = 0; i < cnt; i++) {
      var sd = rr('snow' + l + i);
      var x0 = sd() * w, y0 = sd(), wob = sd() * TAU;
      var py = ((y0 + t * sp * (1 + (sd() - .5) * .3)) % 1) * h;
      var pxx = ((x0 - t * (30 + l * 26) + Math.sin(t + wob) * 8) % w + w) % w;
      x.fillStyle = 'rgba(232,240,246,' + (al * (.5 + .5 * Math.sin(t * 2 + i)).toFixed(2)) + ')';
      x.fillRect(pxx, py, sz, sz);
    }
  }
  /* 滑雪者：沿坡下滑 + 雪雾尾迹 */
  var q = (t * .055) % 1.3;
  var sxp = q * (w + 220) - 110;
  var syp = h * (.52 + sxp / w * .18 + Math.sin(sxp * .01 + 2) * h * .02) - h * .012;
  for (i = 0; i < 14; i++) {
    var dp = (t * 1.3 + i * .1) % 1;
    x.fillStyle = 'rgba(232,240,246,' + ((1 - dp) * .35) + ')';
    x.beginPath(); x.arc(sxp - dp * 46 - i * 2, syp + h * .012 + Math.sin(dp * 9 + i) * 4, 1.6 + dp * 2, 0, TAU); x.fill();
  }
  x.strokeStyle = '#0a0f13'; x.fillStyle = '#0a0f13'; x.lineWidth = h * .009; x.lineCap = 'round';
  x.beginPath();
  x.moveTo(sxp - h * .014, syp + h * .014); x.lineTo(sxp + h * .012, syp - h * .006);
  x.moveTo(sxp - h * .014, syp + h * .014); x.lineTo(sxp - h * .026, syp + h * .03);
  x.moveTo(sxp - h * .014, syp + h * .014); x.lineTo(sxp - h * .004, syp + h * .032);
  x.moveTo(sxp + h * .012, syp - h * .006); x.lineTo(sxp + h * .03, syp + h * .012);
  x.stroke();
  x.beginPath(); x.arc(sxp + h * .017, syp - h * .018, h * .008, 0, TAU); x.fill();
  var vg = x.createRadialGradient(w / 2, h / 2, h * .3, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(3,6,9,.55)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 场景：定向越野 · 等高线图（网格 + 检查点脉冲 + 指北针） ---------- */
SCENES.orienteering = { label: '定向越野 · 等高线图', _key: '', _map: null,
  draw: function (x, w, h, t) {
    var S = this;
    var g = x.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, '#161c10'); g.addColorStop(1, '#0e130b');
    x.fillStyle = g; x.fillRect(0, 0, w, h);
    var off = (t * 5) % 46;
    x.strokeStyle = 'rgba(230,240,210,.05)'; x.lineWidth = 1;
    for (var gx = -46 + off; gx < w + 46; gx += 46) { x.beginPath(); x.moveTo(gx, 0); x.lineTo(gx, h); x.stroke(); }
    for (var gy = -46 + off * .6; gy < h + 46; gy += 46) { x.beginPath(); x.moveTo(0, gy); x.lineTo(w, gy); x.stroke(); }
    /* 等高线预渲染（形状固定，仅缓慢漂移） */
    if (S._key !== w + 'x' + h) {
      S._key = w + 'x' + h;
      var c = document.createElement('canvas'); c.width = w; c.height = h; var m = c.getContext('2d');
      var R = rr('contour');
      for (var ci = 0; ci < 5; ci++) {
        var cx = w * (.15 + R() * .7), cy = h * (.2 + R() * .6), rings = 3 + (R() * 2 | 0);
        m.strokeStyle = 'rgba(160,200,110,.15)';
        for (var rg2 = 0; rg2 < rings; rg2++) {
          var rad = h * (.05 + rg2 * .045 + R() * .02);
          var k1 = 2 + R() * 2, s1 = R() * TAU, k2 = 3 + R() * 2, s2 = R() * TAU;
          m.beginPath();
          for (var a = 0; a <= TAU + .1; a += .22) {
            var rad2 = rad * (1 + .3 * Math.sin(a * k1 + s1 + rg2) + .16 * Math.sin(a * k2 + s2 - rg2 * 2));
            var px2 = cx + Math.cos(a) * rad2 * 1.3, py2 = cy + Math.sin(a) * rad2;
            if (a === 0) m.moveTo(px2, py2); else m.lineTo(px2, py2);
          }
          m.stroke();
        }
      }
      S._map = c;
    }
    var drift = Math.sin(t * .1) * 14;
    x.drawImage(S._map, drift * .4, drift);
  /* 路径虚线 */
  var P = [{ x: w * .2, y: h * .68 }, { x: w * .5, y: h * .38 }, { x: w * .8, y: h * .62 }];
  x.strokeStyle = 'rgba(224,255,168,.5)'; x.lineWidth = 2;
  x.setLineDash([7, 9]); x.lineDashOffset = -t * 26;
  x.beginPath(); x.moveTo(P[0].x, P[0].y); x.lineTo(P[1].x, P[1].y); x.lineTo(P[2].x, P[2].y); x.stroke();
  x.setLineDash([]);
  /* 检查点脉冲 */
  var active = Math.floor((t * .22) % 3);
  for (var i = 0; i < 3; i++) {
    x.strokeStyle = 'rgba(164,241,80,.8)'; x.lineWidth = 2;
    x.beginPath(); x.arc(P[i].x, P[i].y, h * .018, 0, TAU); x.stroke();
    if (i === active) {
      var pr = h * .02 + Math.sin(t * 4.2) * h * .012;
      x.strokeStyle = 'rgba(164,241,80,' + (.55 - .3 * Math.sin(t * 4.2)).toFixed(2) + ')';
      x.beginPath(); x.arc(P[i].x, P[i].y, h * .018 + pr, 0, TAU); x.stroke();
      x.fillStyle = '#a4f150';
      x.beginPath(); x.arc(P[i].x, P[i].y, 3, 0, TAU); x.fill();
    }
  }
  /* 指北针 */
  var nx = w - 46, ny = 52, nr = 22;
  x.strokeStyle = 'rgba(230,240,210,.5)'; x.lineWidth = 1.5;
  x.beginPath(); x.arc(nx, ny, nr, 0, TAU); x.stroke();
  var rot = Math.sin(t * .6) * .18;
  x.save(); x.translate(nx, ny); x.rotate(rot);
  x.fillStyle = 'rgba(164,241,80,.9)';
  x.beginPath(); x.moveTo(0, -nr + 4); x.lineTo(5, 0); x.lineTo(-5, 0); x.closePath(); x.fill();
  x.fillStyle = 'rgba(230,240,210,.7)';
  x.beginPath(); x.moveTo(0, nr - 4); x.lineTo(5, 0); x.lineTo(-5, 0); x.closePath(); x.fill();
  x.restore();
  x.fillStyle = 'rgba(230,240,210,.7)'; x.font = '700 10px sans-serif'; x.textAlign = 'center';
  x.fillText('N', nx, ny - nr - 5);
  var vg = x.createRadialGradient(w / 2, h / 2, h * .3, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(4,6,3,.5)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 场景：越野跑 · 山径推进（滚动层 + 跑者节奏 + 扬尘） ---------- */
SCENES['trail-running'] = { label: '越野跑 · 山径奔袭', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#222f1a'); g.addColorStop(.45, '#141f10'); g.addColorStop(1, '#0b120b');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  fillRidge(x, w, h, '#1e2c16', .40, .05, .011, .026, 2.4, 1.3, t * 8);
  fillRidge(x, w, h, '#131f0d', .54, .06, .013, .03, 1.2, 2.8, t * 22);
  fillRidge(x, w, h, '#0b130a', .70, .07, .015, .034, 3.1, .4, t * 44);
  /* 跑者 */
  var cx = w * .44, cy = h * .74 + Math.abs(Math.sin(t * 4.6)) * h * .014;
  var s = h * .075;
  x.strokeStyle = '#080d07'; x.fillStyle = '#080d07'; x.lineWidth = s * .16; x.lineCap = 'round';
  var lean = s * .28;
  x.beginPath();
  x.moveTo(cx - lean * .4, cy - s * 1.3); x.lineTo(cx + lean * .2, cy - s * .45); // 前倾躯干
  x.stroke();
  x.beginPath(); x.arc(cx + lean * .34, cy - s * 1.5, s * .2, 0, TAU); x.fill();
  var swing = Math.sin(t * 9.2), swing2 = Math.sin(t * 9.2 + Math.PI);
  x.beginPath();
  x.moveTo(cx + lean * .2, cy - s * .45); x.lineTo(cx + swing * s * .7, cy - s * .05);
  x.moveTo(cx + lean * .2, cy - s * .45); x.lineTo(cx + swing2 * s * .7, cy - s * .02);
  x.moveTo(cx - lean * .1, cy - s * 1.05); x.lineTo(cx - lean * .1 - swing * s * .5, cy - s * .7);
  x.moveTo(cx - lean * .1, cy - s * 1.05); x.lineTo(cx - lean * .1 + swing2 * s * .5, cy - s * .75);
  x.stroke();
  for (var i = 0; i < 8; i++) {
    var p = (t * 1.1 + i * .13) % 1;
    x.fillStyle = 'rgba(180,200,150,' + ((1 - p) * .22) + ')';
    x.beginPath(); x.arc(cx - 10 - p * w * .06 + i * 3, cy + s * .1 + Math.sin(p * 7 + i) * 5, 1.4 + p * 2.4, 0, TAU); x.fill();
  }
  var fg = x.createLinearGradient(0, h * .78, 0, h);
  fg.addColorStop(0, 'rgba(8,14,8,0)'); fg.addColorStop(1, 'rgba(8,14,8,.9)');
  x.fillStyle = fg; x.fillRect(0, h * .78, w, h * .22);
  var vg = x.createRadialGradient(w / 2, h / 2, h * .32, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(3,6,3,.5)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 风景：晨光 · 云海日出 ---------- */
SCENES['l-dawn'] = { label: '晨光 · 云海日出', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#141f2e'); g.addColorStop(.42, '#33301e'); g.addColorStop(.62, '#4a3a22'); g.addColorStop(1, '#12180c');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var sx = w * .5, sy = h * .55;
  var sg = x.createRadialGradient(sx, sy, 0, sx, sy, h * .55);
  sg.addColorStop(0, 'rgba(255,196,115,.85)'); sg.addColorStop(.18, 'rgba(255,196,115,.3)'); sg.addColorStop(1, 'rgba(255,196,115,0)');
  x.fillStyle = sg; x.fillRect(0, 0, w, h);
  x.fillStyle = 'rgba(255,222,150,.95)';
  x.beginPath(); x.arc(sx, sy, h * .06, 0, TAU); x.fill();
  /* 远山探出云海 */
  fillRidge(x, w, h, '#1a2412', .44, .05, .008, .02, 2.2, .8, t * 2);
  /* 云海：多条缓涌波带 */
  for (var b = 0; b < 5; b++) {
    var yb = h * (.52 + b * .075), amp = h * (.012 + b * .004), ph = t * (.5 + b * .22) + b * 2.2;
    var al = .06 + b * .022;
    x.fillStyle = 'rgba(232,226,214,' + al + ')';
    x.beginPath(); x.moveTo(0, h + 6);
    for (var px = 0; px <= w; px += 5) x.lineTo(px, yb + Math.sin(px * .02 + ph) * amp + Math.sin(px * .007 - ph * .7) * amp * 1.6);
    x.lineTo(w, h + 6); x.closePath(); x.fill();
  }
  fillRidge(x, w, h, '#101809', .8, .05, .009, .022, 1.3, 2.4, t * 3);
  /* 飞鸟 */
  for (var i = 0; i < 4; i++) {
    var bp = ((t * .02) + i * .29) % 1.2;
    var bx2 = bp * (w + 60) - 30, by2 = h * (.24 + (i % 2) * .06) + Math.sin(t + i) * 3;
    x.strokeStyle = 'rgba(20,26,16,.8)'; x.lineWidth = 1.4;
    var flap = Math.sin(t * 6 + i * 2) * 3;
    x.beginPath(); x.moveTo(bx2 - 5, by2 - flap); x.quadraticCurveTo(bx2, by2 + 2, bx2 + 5, by2 - flap); x.stroke();
  }
} };

/* ---------- 风景：湖面 · 晨雾倒影 ---------- */
SCENES['l-lake'] = { label: '湖面 · 晨雾倒影', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#182430'); g.addColorStop(.45, '#121d24'); g.addColorStop(1, '#0a1114');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var mx = w * .78, my = h * .14;
  x.fillStyle = 'rgba(230,238,244,.8)';
  x.beginPath(); x.arc(mx, my, h * .03, 0, TAU); x.fill();
  var ridgeY = function (px) { return h * .40 + Math.sin(px * .012 + 1.2) * h * .05 + Math.sin(px * .031) * h * .02; };
  x.fillStyle = '#141f18';
  x.beginPath(); x.moveTo(-6, h * .5);
  for (var px = -6; px <= w + 6; px += 6) x.lineTo(px, ridgeY(px));
  x.lineTo(w + 6, h * .5); x.closePath(); x.fill();
  /* 水面：倒影 + 波纹高光 */
  var wy = h * .5;
  var wg = x.createLinearGradient(0, wy, 0, h);
  wg.addColorStop(0, '#101a20'); wg.addColorStop(1, '#080f13');
  x.fillStyle = wg; x.fillRect(0, wy, w, h - wy);
  x.fillStyle = 'rgba(180,200,215,.05)';
  x.beginPath(); x.moveTo(-6, wy);
  for (px = -6; px <= w + 6; px += 6) x.lineTo(px, wy + (h * .40 - ridgeY(px)) * .7 + Math.sin(px * .05 + t * 1.4) * 2);
  x.lineTo(w + 6, wy); x.closePath(); x.fill();
  var HL = rr('lakeHL');
  for (var i = 0; i < 26; i++) {
    var x0 = HL() * w, sp = 14 + HL() * 26, yl = wy + HL() * (h - wy) * .85;
    var xx = ((x0 + t * sp) % (w + 30)) - 15;
    x.strokeStyle = 'rgba(215,230,240,' + (.05 + .1 * Math.pow(Math.sin(t * 2.4 + i * 2.1), 2)).toFixed(2) + ')';
    x.beginPath(); x.moveTo(xx, yl); x.lineTo(xx + 8 + HL() * 12, yl); x.stroke();
  }
  /* 晨雾横移两层 */
  for (i = 0; i < 2; i++) {
    var fy = h * (.46 + i * .1), drift = ((t * (8 + i * 5)) % (w * 1.6)) - w * .3;
    var fgr = x.createRadialGradient(drift, fy, 0, drift, fy, w * .45);
    fgr.addColorStop(0, 'rgba(220,232,238,.09)'); fgr.addColorStop(1, 'rgba(220,232,238,0)');
    x.fillStyle = fgr;
    x.save(); x.translate(drift, fy); x.scale(2.2, .5); x.beginPath(); x.arc(0, 0, w * .45, 0, TAU); x.fill(); x.restore();
  }
  var vg = x.createRadialGradient(w / 2, h / 2, h * .3, w / 2, h / 2, h);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(3,6,8,.5)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
} };

/* ---------- 风景：林间 · 光斑穿行 ---------- */
SCENES['l-forest'] = { label: '林间 · 光斑穿行', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, w, h);
  g.addColorStop(0, '#111c0e'); g.addColorStop(1, '#070e06');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  /* 光束（斜向，呼吸） */
  for (var i = 0; i < 3; i++) {
    var bx = w * (.2 + i * .28), al = .05 + .04 * Math.sin(t * .7 + i * 2.1);
    var lg = x.createLinearGradient(bx, 0, bx - w * .3, h);
    lg.addColorStop(0, 'rgba(210,240,150,' + al.toFixed(2) + ')'); lg.addColorStop(1, 'rgba(210,240,150,0)');
    x.fillStyle = lg;
    x.beginPath();
    x.moveTo(bx - 10, 0); x.lineTo(bx + 34, 0); x.lineTo(bx + 34 - w * .3 + 60, h); x.lineTo(bx + 10 - w * .3, h);
    x.closePath(); x.fill();
  }
  /* 远层树干（细、慢） */
  var R1 = rr('treeFar');
  x.fillStyle = 'rgba(16,26,12,.8)';
  for (i = 0; i < 14; i++) {
    var tw = 4 + R1() * 5;
    var tx = ((R1() * w - t * 4) % w + w) % w;
    x.fillRect(tx, 0, tw, h);
  }
  /* 光尘（金色上浮） */
  for (i = 0; i < 22; i++) {
    var sd = rr('dust' + i);
    var dx0 = sd() * w, sp = .04 + sd() * .06, ph = sd() * TAU;
    var dy = h - ((t * sp + sd()) % 1) * h;
    var dxx = dx0 + Math.sin(t * .8 + ph) * 10;
    x.fillStyle = 'rgba(230,220,140,' + (.14 + .16 * Math.sin(t * 2.2 + ph)).toFixed(2) + ')';
    x.beginPath(); x.arc(dxx, dy, 1 + sd() * 1.4, 0, TAU); x.fill();
  }
  /* 近层树干（粗、快） */
  var R2 = rr('treeNear');
  x.fillStyle = '#060b05';
  for (i = 0; i < 9; i++) {
    var tw2 = 10 + R2() * 16;
    var tx2 = ((R2() * w - t * 12) % w + w) % w;
    x.fillRect(tx2, -10, tw2, h + 20);
  }
  var fg = x.createLinearGradient(0, h * .7, 0, h);
  fg.addColorStop(0, 'rgba(6,10,5,0)'); fg.addColorStop(1, 'rgba(6,10,5,.8)');
  x.fillStyle = fg; x.fillRect(0, h * .7, w, h * .3);
} };

/* ---------- 风景：星夜 · 银河山径 ---------- */
SCENES['l-night'] = { label: '星夜 · 银河山径', draw: function (x, w, h, t) {
  var g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#080d1a'); g.addColorStop(.6, '#0c1210'); g.addColorStop(1, '#0a0f0a');
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  var S = rr('nstars');
  for (var i = 0; i < 130; i++) {
    var sxx = S() * w, syy = S() * h * .7, base = .2 + S() * .6;
    var al = base * (.4 + .6 * Math.pow(Math.sin(t * (.5 + S() * 1.4) + i * 1.9), 2));
    x.fillStyle = 'rgba(222,232,226,' + al.toFixed(2) + ')';
    x.fillRect(sxx, syy, S() > .88 ? 2 : 1.2, 1.2);
  }
  /* 银河斜带 */
  x.save(); x.translate(w * .5, h * .3); x.rotate(-.42);
  var mg = x.createLinearGradient(0, -h * .2, 0, h * .2);
  mg.addColorStop(0, 'rgba(190,205,235,0)'); mg.addColorStop(.5, 'rgba(190,205,235,.08)'); mg.addColorStop(1, 'rgba(190,205,235,0)');
  x.fillStyle = mg; x.fillRect(-w, -h * .2, w * 2, h * .4);
  x.restore();
  /* 流星（每 7s 一颗） */
  var mp = (t % 7) / .9;
  if (mp < 1) {
    var mx2 = w * (.15 + mp * .55), my2 = h * (.08 + mp * .3);
    var tl = x.createLinearGradient(mx2, my2, mx2 - 60, my2 - 36);
    tl.addColorStop(0, 'rgba(235,242,250,.9)'); tl.addColorStop(1, 'rgba(235,242,250,0)');
    x.strokeStyle = tl; x.lineWidth = 1.6;
    x.beginPath(); x.moveTo(mx2, my2); x.lineTo(mx2 - 60, my2 - 36); x.stroke();
  }
  fillRidge(x, w, h, '#0f1a10', .68, .05, .01, .026, 2.2, .8, t * 2);
  fillRidge(x, w, h, '#090f08', .82, .05, .012, .03, 3.1, 1.4, t * 4);
  /* 地平线远光（远处村落/晨光） */
  var hg = x.createLinearGradient(0, h * .68, 0, h * .84);
  hg.addColorStop(0, 'rgba(255,196,110,0)'); hg.addColorStop(.6, 'rgba(255,196,110,.06)'); hg.addColorStop(1, 'rgba(255,196,110,0)');
  x.fillStyle = hg; x.fillRect(0, h * .68, w, h * .16);
} };

/* ---------- 引擎 ---------- */
function Engine(cv, opts) {
  opts = opts || {};
  this.cv = cv;
  this.x = cv.getContext('2d');
  this.dpr = Math.min(global.devicePixelRatio || 1, 1.5);
  this.ambient = !!opts.ambient;
  this.pool = LIBS[opts.library || 'sports'] || ORDER;
  this.preferred = (opts.preferred || []).filter(function (p) { return SCENES[p]; });
  this.videos = opts.videos || {};
  this.vsrcIdx = {};
  this._broken = {};
  this._vidActive = false;
  this.cb = opts.onScene || null;
  this.labels = opts.labels || {};
  this.fixed = (opts.fixed && (SCENES[opts.fixed] || (opts.videos && opts.videos[opts.fixed]))) ? opts.fixed : null;
  /* 视频场景可能没有程序化 SCENES 条目：记录每个 id 的兜底场景 */
  this.fallbackScene = opts.fallbackScene || 'l-dawn';
  this.DUR = this.fixed ? 1e9 : 9;
  this.FADE = .7;
  this.idx = 0; this.fade = 0; this.fadeStart = -10; this.startT = 0; this.now = 0;
  this.w = 0; this.h = 0;
  /* 视频层：原生 <video> DOM 元素（object-fit:cover 铺满，硬件解码），
     按场景轮换 src；文件加载失败自动剔除并回退程序化 canvas 场景 */
  if (!REDUCED && Object.keys(this.videos).length) {
    var self = this;
    this.vid = document.createElement('video');
    this.vid.className = 'cinema-video';
    this.vid.muted = true; this.vid.loop = true;
    this.vid.setAttribute('playsinline', '');
    this.vid.setAttribute('autoplay', '');
    this.vid.preload = 'auto';
    this.vid.style.display = 'none';
    this.vid.addEventListener('error', function () {
      var src = self.vid.getAttribute('src');
      if (src) self._broken[src] = true;
      self._vidActive = false;
      self._syncLayers();
    });
    this.fadeEl = document.createElement('div');
    this.fadeEl.className = 'cinema-fade';
    cv.parentNode.insertBefore(this.fadeEl, cv);
    cv.parentNode.insertBefore(this.vid, this.fadeEl);
  }
  this.buildSchedule();
  var self = this;
  function resize() {
    var r = cv.getBoundingClientRect();
    if (!r.width || !r.height) return;
    self.w = Math.round(r.width * self.dpr); self.h = Math.round(r.height * self.dpr);
    if (cv.width !== self.w || cv.height !== self.h) { cv.width = self.w; cv.height = self.h; }
  }
  resize();
  if (global.ResizeObserver) new ResizeObserver(resize).observe(cv);
  else global.addEventListener('resize', resize);
  this.notify();
  this._startVideo();
  if (REDUCED) { this.render(6.5); return; }
  (function loop(now) {
    self.frame(now);
    requestAnimationFrame(loop);
  })(performance.now());
}
Engine.prototype.buildSchedule = function () {
  var self = this;
  var pref = shuffle(this.preferred.filter(function (p) { return self.pool.indexOf(p) >= 0; }));
  var rest = shuffle(this.pool.filter(function (o) { return self.preferred.indexOf(o) < 0; }));
  var seq = [];
  /* 偏好运动前置且高频出现：每轮 3 次偏好，穿插 2 个其余场景调剂 */
  for (var i = 0; i < 3; i++) {
    pref.forEach(function (p) {
      seq.push(p);
      if (rest.length) seq.push(rest[(i * 2 + seq.length) % rest.length]);
    });
  }
  while (seq.length < 12) seq = seq.concat(shuffle(this.pool));
  this.schedule = seq;
};
Engine.prototype.id = function () { return this.fixed || this.schedule[this.idx % this.schedule.length]; };
Engine.prototype.notify = function () {
  var id = this.id();
  var label = (SCENES[id] && SCENES[id].label) || this.labels[id] || id;
  if (this.cb) this.cb(id, label);
};
Engine.prototype._nextVideoSrc = function (id) {
  var self = this;
  var list = (this.videos[id] || []).filter(function (f) { return !self._broken[f]; });
  if (!list.length) return null;
  var i = this.vsrcIdx[id] || 0;
  this.vsrcIdx[id] = (i + 1) % list.length;
  return list[i % list.length];
};
Engine.prototype._startVideo = function () {
  if (!this.vid) return;
  var src = this._nextVideoSrc(this.id());
  this._vidActive = false;
  if (!src) { this.vid.pause(); this._syncLayers(); return; }
  if (this.vid.getAttribute('src') !== src) {
    this.vid.setAttribute('src', src);
    this.vid.load();
  }
  this._vidActive = true;
  this._syncLayers();
  this._flashFade();
  var pr = this.vid.play();
  if (pr && pr.catch) pr.catch(function () {});
};
Engine.prototype._syncLayers = function () {
  /* 视频 active → 隐藏 canvas 显视频；否则反之 */
  var on = this._vidActive;
  if (this.cv) this.cv.style.display = on ? 'none' : 'block';
  if (this.vid) this.vid.style.display = on ? 'block' : 'none';
};
Engine.prototype._flashFade = function () {
  if (!this.fadeEl) return;
  this.fadeEl.style.transition = 'none';
  this.fadeEl.style.opacity = '1';
  void this.fadeEl.offsetWidth;
  this.fadeEl.style.transition = 'opacity .55s ease';
  this.fadeEl.style.opacity = '0';
};
Engine.prototype.advance = function (t) {
  this.idx++;
  if (this.idx % this.schedule.length === 0) this.buildSchedule();
  this.startT = t; this.fadeStart = t; this.fade = 1;
  this.notify();
  this._startVideo();
};
Engine.prototype.set = function (id) {
  if (id && !SCENES[id]) id = null;
  if ((this.fixed || null) === (id || null)) return;
  this.fixed = id || null;
  this.DUR = this.fixed ? 1e9 : 9;
  this.startT = this.now; this.fadeStart = this.now; this.fade = 1;
  this.notify();
  this._startVideo();
};
Engine.prototype.frame = function (now) {
  var t = (now - this._t0) / 1000;
  if (this._t0 === undefined) { this._t0 = now; t = 0; }
  this.now = t;
  if (!this.fixed && t - this.startT > this.DUR) this.advance(t);
  this.render(t);
};
Engine.prototype.render = function (t) {
  var x = this.x, w = this.w, h = this.h;
  if (!w || !h) return;
  x.clearRect(0, 0, w, h);
  var id = this.id(), sc = SCENES[id];
  /* 视频接管中 → canvas 保持透明，露出原生 <video> 层 */
  if (this._vidActive) { x.clearRect(0, 0, w, h); return; }
  /* 视频场景无程序化条目且视频未就绪 → 兜底场景，避免黑屏 */
  if (!sc) sc = SCENES[this.fallbackScene] || SCENES[Object.keys(SCENES)[0]];
  if (!sc) return;
  var lt = t - this.startT;
  x.save();
  /* 镜头呼吸：缓慢推拉 + 横移，模拟手持运镜 */
  var s = 1 + .02 * Math.sin(t * .24), panx = Math.sin(t * .1) * w * .009;
  x.translate(w / 2, h / 2); x.scale(s, s); x.translate(-w / 2 + panx, -h / 2 + Math.cos(t * .13) * h * .006);
  sc.draw(x, w, h, lt > 0 ? lt : 0);
  x.restore();
  /* 剪辑黑场过渡 */
  var f = clamp(1 - (t - this.fadeStart) / this.FADE, 0, 1);
  if (f > 0) { x.fillStyle = 'rgba(5,8,4,' + f.toFixed(2) + ')'; x.fillRect(0, 0, w, h); }
};

global.Cinema = {
  mount: function (cv, opts) { return new Engine(cv, opts); },
  scenes: SCENES, order: ORDER
};
})(window);
