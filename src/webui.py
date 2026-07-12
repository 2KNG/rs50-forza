"""웹 대시보드 — 게임 옆 브라우저/폰에서 상태 관찰용.

stdlib http.server 기반 (의존성 없음). / = 대시보드, /state = JSON 폴링(150ms).
테마 5종 내장 (우상단 스위처, localStorage 기억):
  pit(기본) / f1 / retro(아날로그) / minimal(OLED) / neon(신스웨이브)
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RS50 x FH6</title>
<style>
/* ===== 공통 토큰 ===== */
:root{
  --grn:#2bd45f; --red:#ff3b3b; --blu:#3b6cff; --pur:#b93bff; --amb:#ffb020;
  --seg-off:#1a2029;
}
*{margin:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
body{background:var(--bg);color:var(--tx);min-height:100vh;padding:16px;
     display:flex;flex-direction:column;gap:14px;transition:background .3s}
header{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:2px;font-size:14px;color:var(--dim)}
.badge{font-size:15px;font-weight:800;letter-spacing:2px;padding:7px 16px;border-radius:8px}
.badge.auto{background:#0d2d18;color:var(--grn);border:1px solid #1d5c33}
.badge.manual{background:#332309;color:var(--amb);border:1px solid #6b4d15}
.badge.off{background:#22262e;color:var(--dim);border:1px solid var(--line)}
.dot{width:9px;height:9px;border-radius:50%;background:#444}
.dot.on{background:var(--grn);box-shadow:0 0 8px var(--grn)}
.themes{margin-left:auto;display:flex;gap:6px}
.themes button{background:var(--panel);color:var(--dim);border:1px solid var(--line);
  border-radius:7px;padding:5px 11px;font-size:11px;letter-spacing:1px;cursor:pointer}
.themes button.on{color:var(--tx);border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px}
main{display:flex;flex-direction:column;gap:14px}
/* 클러스터 */
.cluster{display:flex;gap:14px;align-items:stretch;flex-wrap:wrap}
.block{padding:14px 22px;display:flex;flex-direction:column;justify-content:center;
       align-items:center;gap:4px}
.block small{font-size:11px;color:var(--dim);letter-spacing:2px}
#gear{font-size:110px;font-weight:800;line-height:1;min-width:120px;text-align:center;
      font-variant-numeric:tabular-nums;transition:transform .12s}
#gear.pop{transform:scale(1.14)}
.vnum{font-size:44px;font-weight:700;font-variant-numeric:tabular-nums}
#gaugewrap{display:none;padding:8px}
/* rev 스트립 */
.revbar{padding:16px 18px 8px}
.strip{display:flex;gap:8px}
.led{flex:1;height:44px;border-radius:8px;background:var(--seg-off);
     border:1px solid var(--line);transition:background .06s,box-shadow .06s}
.revmeta{display:flex;justify-content:space-between;color:var(--dim);
         font-size:13px;padding:8px 2px 6px;font-variant-numeric:tabular-nums}
#shift{font-weight:800;letter-spacing:3px;color:var(--pur)}
/* 이벤트 */
.events{padding:14px 18px}
.events h3{font-size:11px;color:var(--dim);letter-spacing:2px;margin-bottom:8px}
.log{overflow-y:auto;max-height:260px;font:13px/1.7 Consolas,monospace}
.log div{color:var(--dim);border-bottom:1px solid var(--logline);padding:2px 4px}
.log div b{color:var(--tx);font-weight:600}

/* ===== 테마: pit (기본 — 엔지니어링 패널) ===== */
body[data-theme=pit]{--bg:#0b0e14;--panel:#141922;--line:#232b38;--tx:#e6edf3;
  --dim:#8b98a9;--acc:#3b6cff;--logline:#10141b}

/* ===== 테마: f1 (방송 그래픽 — 카본/레드, 대형 기어) ===== */
body[data-theme=f1]{--bg:#08080a;--panel:#111114;--line:#26262c;--tx:#fff;
  --dim:#77777f;--acc:#e10600;--logline:#151519;
  background-image:repeating-linear-gradient(45deg,#0a0a0d 0 3px,#08080a 3px 6px)}
body[data-theme=f1] .panel{border-left:3px solid var(--acc)}
body[data-theme=f1] #gear{font-size:150px;font-style:italic;
  text-shadow:0 0 26px rgba(225,6,0,.35)}
body[data-theme=f1] .vnum{font-style:italic}
body[data-theme=f1] .led{height:34px;border-radius:3px}
body[data-theme=f1] .strip{gap:4px}
body[data-theme=f1] .brand::after{content:" · BROADCAST";color:var(--acc)}

/* ===== 테마: retro (아날로그 클러스터 — 앰버 백라이트) ===== */
body[data-theme=retro]{--bg:#0d0a06;--panel:#161007;--line:#3a2c14;--tx:#ffd9a0;
  --dim:#9c7b4a;--acc:#ffb020;--seg-off:#221808;--logline:#1c1409}
body[data-theme=retro] #gaugewrap{display:block}
body[data-theme=retro] #gear{font-size:84px;color:#ffcf7d;
  text-shadow:0 0 18px rgba(255,176,32,.45)}
body[data-theme=retro] .vnum{color:#ffcf7d;font-family:Consolas,monospace}
body[data-theme=retro] .led{border-radius:2px;height:26px}
body[data-theme=retro] .panel{border-radius:10px;
  box-shadow:inset 0 0 40px rgba(255,176,32,.05)}

/* ===== 테마: minimal (OLED — 글랜스/폰 전용) ===== */
body[data-theme=minimal]{--bg:#000;--panel:#000;--line:#000;--tx:#ddd;
  --dim:#555;--acc:#888;--seg-off:#111;--logline:#0a0a0a}
body[data-theme=minimal] .panel{border:none}
body[data-theme=minimal] .events,body[data-theme=minimal] .rpmnum{display:none}
body[data-theme=minimal] #gear{font-size:200px;font-weight:300}
body[data-theme=minimal] .led{height:12px;border:none;border-radius:2px}
body[data-theme=minimal] .cluster{justify-content:center}
body[data-theme=minimal] .revmeta{display:none}

/* ===== 테마: neon (신스웨이브) ===== */
body[data-theme=neon]{--bg:#0d0221;--panel:#170b33;--line:#3b1a6e;--tx:#f3e9ff;
  --dim:#8f7bb8;--acc:#ff2bd6;--seg-off:#1d1040;--logline:#1f1244;
  background-image:linear-gradient(#0d0221 60%,#1b0640),
   repeating-linear-gradient(transparent 0 39px,rgba(255,43,214,.07) 39px 40px)}
body[data-theme=neon] #gear{background:linear-gradient(180deg,#2be2ff,#ff2bd6);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 14px rgba(255,43,214,.5))}
body[data-theme=neon] .led{border-radius:10px;
  box-shadow:inset 0 0 6px rgba(0,0,0,.6)}
body[data-theme=neon] .panel{box-shadow:0 0 24px rgba(59,26,110,.35)}
</style></head>
<body data-theme="pit">
<header>
  <span class="brand">RS50 × FH6</span>
  <span class="badge off" id="mode">대기</span>
  <span class="dot" id="teldot"></span>
  <nav class="themes" id="themes"></nav>
</header>
<main>
<section class="cluster">
  <div class="panel" id="gaugewrap">
    <svg width="230" height="230" viewBox="0 0 200 200">
      <g id="ticks"></g>
      <path id="redzone" fill="none" stroke="#ff3b3b" stroke-width="6" opacity=".8"/>
      <line id="needle" x1="100" y1="100" x2="100" y2="26" stroke="#ffcf7d"
            stroke-width="3.5" stroke-linecap="round"
            style="transform-origin:100px 100px;transition:transform .1s linear"/>
      <circle cx="100" cy="100" r="7" fill="#ffcf7d"/>
      <text id="gunit" x="100" y="150" text-anchor="middle" fill="#9c7b4a"
            font-size="10" letter-spacing="2">RPM ×1000</text>
    </svg>
  </div>
  <div class="panel block"><small>GEAR</small><div id="gear">-</div></div>
  <div class="panel block"><span class="vnum" id="speed">0</span><small>KM/H</small></div>
  <div class="panel block rpmnum"><span class="vnum" id="rpm">0</span>
    <small>/ <span id="maxrpm">0</span> RPM</small></div>
</section>
<section class="panel revbar">
  <div class="strip" id="strip"></div>
  <div class="revmeta"><span id="ratio">0%</span><span id="shift"></span></div>
</section>
<section class="panel events"><h3>EVENTS</h3><div class="log" id="log"></div></section>
</main>
<script>
const N=10, SEG=['var(--grn)','var(--grn)','var(--grn)','var(--red)','var(--red)',
                 'var(--red)','var(--red)','var(--blu)','var(--blu)','var(--blu)'];
const THEMES=[['pit','PIT'],['f1','F1'],['retro','RETRO'],['minimal','OLED'],['neon','NEON']];
const $=id=>document.getElementById(id);

/* 테마 스위처 */
const nav=$('themes');
THEMES.forEach(([key,label])=>{
  const b=document.createElement('button');
  b.textContent=label; b.dataset.t=key;
  b.onclick=()=>setTheme(key);
  nav.appendChild(b);
});
function setTheme(t){
  document.body.dataset.theme=t;
  localStorage.setItem('rs50-theme',t);
  [...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.t===t));
}
setTheme(localStorage.getItem('rs50-theme')||'pit');

/* rev 스트립 */
const strip=$('strip');
for(let i=0;i<N;i++){const d=document.createElement('div');d.className='led';strip.appendChild(d);}
const leds=[...strip.children];

/* retro 게이지 눈금 (스윕 -120°..+120°, 240°) */
const tickG=$('ticks');
for(let i=0;i<=10;i++){
  const a=(-120+i*24)*Math.PI/180, r1=86, r2=i%2?78:72;
  const x1=100+r1*Math.sin(a), y1=100-r1*Math.cos(a);
  const x2=100+r2*Math.sin(a), y2=100-r2*Math.cos(a);
  tickG.innerHTML+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
    stroke="${i>=9?'#ff3b3b':'#9c7b4a'}" stroke-width="${i%2?1.5:3}"/>`
   + (i%2?'':`<text x="${100+60*Math.sin(a)}" y="${100-60*Math.cos(a)+3}"
      text-anchor="middle" fill="#9c7b4a" font-size="11">${i}</text>`);
}
/* 레드존 아크 (95%~100%) */
(()=>{const a0=(-120+.95*240)*Math.PI/180, a1=(120)*Math.PI/180, r=90;
$('redzone').setAttribute('d',`M ${100+r*Math.sin(a0)} ${100-r*Math.cos(a0)}
 A ${r} ${r} 0 0 1 ${100+r*Math.sin(a1)} ${100-r*Math.cos(a1)}`);})();

let lastEvents='', lastGear=null;
async function tick(){
  try{
    const s=await (await fetch('/state')).json();
    const gtxt = s.gear===0?'R':(s.gear>10?'N':(s.gear||'-'));
    const g=$('gear');
    if(gtxt!==lastGear){g.classList.add('pop');setTimeout(()=>g.classList.remove('pop'),120);lastGear=gtxt;}
    g.textContent=gtxt;
    $('speed').textContent=Math.round(s.speed_kmh);
    $('rpm').textContent=Math.round(s.rpm);
    $('maxrpm').textContent=Math.round(s.max_rpm);
    $('ratio').textContent=Math.round(s.ratio*100)+'%';
    const b=$('mode');
    if(!s.alive){b.textContent='대기';b.className='badge off';}
    else if(s.mode==='AUTO'){b.textContent='AUTO';b.className='badge auto';}
    else{b.textContent='MANUAL';b.className='badge manual';}
    $('teldot').className='dot'+(s.alive?' on':'');
    /* 스트립 (물리 LED 미러) */
    const lit=s.ratio<=s.start_ratio?0:
      Math.min(N,Math.max(1,Math.round((s.ratio-s.start_ratio)/(s.blink_ratio-s.start_ratio)*N)));
    const blink=s.alive&&s.ratio>=s.blink_ratio&&(Date.now()>>6)%2===0;
    leds.forEach((el,i)=>{
      if(blink){el.style.background='var(--pur)';el.style.boxShadow='0 0 16px var(--pur)';}
      else if(s.alive&&i<lit){el.style.background=SEG[i];el.style.boxShadow='0 0 10px '+SEG[i];}
      else{el.style.background='var(--seg-off)';el.style.boxShadow='none';}
    });
    $('shift').textContent=(s.alive&&s.ratio>=s.blink_ratio)?'SHIFT ▲':'';
    /* retro 바늘: ratio -> -120°..+120° */
    $('needle').style.transform=`rotate(${-120+Math.min(1,Math.max(0,s.ratio))*240}deg)`;
    const ev=s.events.map(e=>`<div><b>${e[0]}</b> ${e[1]}</div>`).reverse().join('');
    if(ev!==lastEvents){$('log').innerHTML=ev;lastEvents=ev;}
  }catch(e){}
}
setInterval(tick,150); tick();
</script></body></html>"""


class WebUI(threading.Thread):
    def __init__(self, provider, port=8777):
        """provider() -> dict (JSON 직렬화 가능 상태 스냅샷)"""
        super().__init__(daemon=True, name="webui")
        self.provider = provider
        self.port = port

    def run(self):
        provider = self.provider

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 요청 로그 소음 제거
                pass

            def do_GET(self):
                if self.path == "/state":
                    body = json.dumps(provider()).encode()
                    ctype = "application/json"
                elif self.path == "/":
                    body = PAGE.encode()
                    ctype = "text/html; charset=utf-8"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        ThreadingHTTPServer(("127.0.0.1", self.port), Handler).serve_forever()
