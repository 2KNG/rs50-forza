"""웹 대시보드 — 게임 옆 브라우저/폰에서 상태 관찰용.

stdlib http.server 기반 (의존성 없음). / = 대시보드, /state = JSON 폴링(150ms).
- 테마 5종: pit(기본)/f1/retro/minimal/neon — 우상단 스위처, localStorage 기억
- 표시 모드: DIGITAL(숫자 클러스터) <-> ANALOG(타코미터 바늘) — 테마와 독립
- 적응형: --u = min(1vw, 1.78vh) 단위로 16:9 기준 모든 해상도 비율 고정 스케일
- 폰에서 보려면 config [web].host = "0.0.0.0" (같은 공유기 내 PC IP로 접속)
"""
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RS50 x FH6</title>
<style>
/* ===== 스케일 단위: 16:9에서 1vw == 1.78vh — min으로 어떤 비율에도 맞춤 ===== */
:root{
  --u:min(1vw,1.78vh);
  --grn:#2bd45f; --red:#ff3b3b; --blu:#3b6cff; --pur:#b93bff; --amb:#ffb020;
  --seg-off:#1a2029;
}
*{margin:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{height:100%}
body{background:var(--bg);color:var(--tx);padding:calc(var(--u)*1.4);
     display:flex;flex-direction:column;gap:calc(var(--u)*1.2);transition:background .3s}
/* 레드라인 앰비언트 글로우 + 시프트 플래시 오버레이 */
#ambient{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:0;
  background:radial-gradient(ellipse at 50% 110%,rgba(255,59,59,.32),transparent 60%)}
#flash{position:fixed;inset:0;pointer-events:none;z-index:1;opacity:0;
  box-shadow:inset 0 0 calc(var(--u)*14) calc(var(--u)*2) var(--pur)}
header,main{position:relative;z-index:2}
header{display:flex;align-items:center;gap:calc(var(--u)*1.2);flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:2px;font-size:calc(var(--u)*1.3);color:var(--dim)}
.badge{font-size:calc(var(--u)*1.4);font-weight:800;letter-spacing:2px;
       padding:calc(var(--u)*.6) calc(var(--u)*1.4);border-radius:calc(var(--u)*.7)}
.badge.auto{background:#0d2d18;color:var(--grn);border:1px solid #1d5c33}
.badge.manual{background:#332309;color:var(--amb);border:1px solid #6b4d15;
  animation:pulse 1.6s ease-in-out infinite}
.badge.off{background:#22262e;color:var(--dim);border:1px solid var(--line)}
.badge.lost{background:#33090c;color:var(--red);border:1px solid #6b1518}
@keyframes pulse{50%{box-shadow:0 0 calc(var(--u)*1.2) rgba(255,176,32,.55)}}
.dot{width:calc(var(--u)*.8);height:calc(var(--u)*.8);border-radius:50%;background:#444}
.dot.on{background:var(--grn);box-shadow:0 0 calc(var(--u)*.8) var(--grn)}
.switchers{margin-left:auto;display:flex;gap:calc(var(--u)*1.6);flex-wrap:wrap}
.sw{display:flex;gap:calc(var(--u)*.5)}
.sw button{background:var(--panel);color:var(--dim);border:1px solid var(--line);
  border-radius:calc(var(--u)*.6);padding:calc(var(--u)*.45) calc(var(--u)*1);
  font-size:calc(var(--u)*1);letter-spacing:1px;cursor:pointer}
.sw button.on{color:var(--tx);border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:calc(var(--u)*1.2)}
main{display:flex;flex-direction:column;gap:calc(var(--u)*1.2);flex:1;min-height:0}
/* ===== 클러스터 ===== */
.cluster{display:flex;gap:calc(var(--u)*1.2);align-items:stretch;flex-wrap:wrap;
         justify-content:center}
.block{padding:calc(var(--u)*1.2) calc(var(--u)*2);display:flex;flex-direction:column;
       justify-content:center;align-items:center;gap:calc(var(--u)*.4)}
.block small{font-size:calc(var(--u)*1);color:var(--dim);letter-spacing:2px}
#gear{font-size:calc(var(--u)*11);font-weight:800;line-height:1;
      min-width:calc(var(--u)*12);text-align:center;
      font-variant-numeric:tabular-nums;transition:transform .12s}
.pop{transform:scale(1.14)!important}
.vnum{font-size:calc(var(--u)*4.4);font-weight:700;font-variant-numeric:tabular-nums}
/* 드리프트/횡G */
.driftblk .vnum{color:var(--acc)}
.driftblk small #dpeak{color:var(--tx);font-weight:700}
#darrow{font-size:calc(var(--u)*2.6);vertical-align:middle;margin-right:calc(var(--u)*.4)}
.gblk{min-width:calc(var(--u)*16)}
.gtrack{position:relative;width:calc(var(--u)*13);height:calc(var(--u)*1.4);
  background:var(--seg-off);border:1px solid var(--line);border-radius:calc(var(--u)*.7)}
.gtick{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--dim);opacity:.6}
#gdot{position:absolute;top:50%;left:50%;width:calc(var(--u)*1.1);height:calc(var(--u)*1.1);
  border-radius:50%;background:var(--acc);transform:translate(-50%,-50%);
  box-shadow:0 0 calc(var(--u)*.8) var(--acc)}
/* ===== 아날로그 타코 ===== */
.tacho{position:relative;display:none;padding:calc(var(--u)*.8)}
.tacho svg{width:calc(var(--u)*32);height:calc(var(--u)*32);display:block}
#gearA{position:absolute;left:50%;top:62%;transform:translate(-50%,-50%);
       font-size:calc(var(--u)*7);font-weight:800;line-height:1;
       transition:transform .12s;transform-origin:center}
#gearA.pop{transform:translate(-50%,-50%) scale(1.14)!important}
.tick{stroke:var(--gauge-dim)} .tick.red{stroke:var(--red)}
.tlabel{fill:var(--gauge-dim)}
#needle{stroke:var(--gauge-fg)} #hub{fill:var(--gauge-fg)}
#gunit{fill:var(--gauge-dim)}
body[data-display=analog] .tacho{display:block}
body[data-display=analog] .block.gearblk{display:none}
/* ===== rev 스트립 ===== */
.revbar{padding:calc(var(--u)*1.3) calc(var(--u)*1.5) calc(var(--u)*.6)}
.strip{display:flex;gap:calc(var(--u)*.7)}
.led{flex:1;height:calc(var(--u)*3.8);border-radius:calc(var(--u)*.7);
     background:var(--seg-off);border:1px solid var(--line);
     transition:background .06s,box-shadow .06s}
.revmeta{display:flex;justify-content:space-between;color:var(--dim);
  font-size:calc(var(--u)*1.2);padding:calc(var(--u)*.7) 2px calc(var(--u)*.4);
  font-variant-numeric:tabular-nums}
#shift{font-weight:800;letter-spacing:3px;color:var(--pur)}
/* ===== 이벤트 ===== */
.events{padding:calc(var(--u)*1.2) calc(var(--u)*1.5);flex:1;min-height:0;
        display:flex;flex-direction:column}
.events h3{font-size:calc(var(--u)*1);color:var(--dim);letter-spacing:2px;
           margin-bottom:calc(var(--u)*.6)}
.log{overflow-y:auto;flex:1;font:calc(var(--u)*1.15)/1.7 Consolas,monospace}
.log div{color:var(--dim);border-bottom:1px solid var(--logline);padding:2px 4px;
  animation:fadein .35s ease}
.log div b{color:var(--tx);font-weight:600}
@keyframes fadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1}}
@media (orientation:portrait){
  :root{--u:min(2.2vw,1.4vh)}
  #gear{font-size:calc(var(--u)*16)}
  .tacho svg{width:calc(var(--u)*40);height:calc(var(--u)*40)}
}

/* ===== 테마: pit ===== */
body[data-theme=pit]{--bg:#0b0e14;--panel:#141922;--line:#232b38;--tx:#e6edf3;
  --dim:#8b98a9;--acc:#3b6cff;--logline:#10141b;
  --gauge-fg:#e6edf3;--gauge-dim:#8b98a9}
/* ===== 테마: f1 ===== */
body[data-theme=f1]{--bg:#08080a;--panel:#111114;--line:#26262c;--tx:#fff;
  --dim:#77777f;--acc:#e10600;--logline:#151519;
  --gauge-fg:#fff;--gauge-dim:#77777f;
  background-image:repeating-linear-gradient(45deg,#0a0a0d 0 3px,#08080a 3px 6px)}
body[data-theme=f1] .panel{border-left:3px solid var(--acc)}
body[data-theme=f1] #gear{font-size:calc(var(--u)*14);font-style:italic;
  text-shadow:0 0 calc(var(--u)*2.4) rgba(225,6,0,.35)}
body[data-theme=f1] #gearA{font-style:italic}
body[data-theme=f1] .vnum{font-style:italic}
body[data-theme=f1] .led{height:calc(var(--u)*3);border-radius:3px}
body[data-theme=f1] .strip{gap:4px}
body[data-theme=f1] .brand::after{content:" · BROADCAST";color:var(--acc)}
/* ===== 테마: retro ===== */
body[data-theme=retro]{--bg:#0d0a06;--panel:#161007;--line:#3a2c14;--tx:#ffd9a0;
  --dim:#9c7b4a;--acc:#ffb020;--seg-off:#221808;--logline:#1c1409;
  --gauge-fg:#ffcf7d;--gauge-dim:#9c7b4a}
body[data-theme=retro] #gear{font-size:calc(var(--u)*8.5);color:#ffcf7d;
  text-shadow:0 0 calc(var(--u)*1.6) rgba(255,176,32,.45)}
body[data-theme=retro] #gearA{color:#ffcf7d;
  text-shadow:0 0 calc(var(--u)*1.6) rgba(255,176,32,.45)}
body[data-theme=retro] .vnum{color:#ffcf7d;font-family:Consolas,monospace}
body[data-theme=retro] .led{border-radius:2px;height:calc(var(--u)*2.4)}
body[data-theme=retro] .panel{border-radius:calc(var(--u)*.9);
  box-shadow:inset 0 0 calc(var(--u)*3.6) rgba(255,176,32,.05)}
/* ===== 테마: minimal ===== */
body[data-theme=minimal]{--bg:#000;--panel:#000;--line:#000;--tx:#ddd;
  --dim:#555;--acc:#888;--seg-off:#111;--logline:#0a0a0a;
  --gauge-fg:#ccc;--gauge-dim:#444}
body[data-theme=minimal] .panel{border:none}
body[data-theme=minimal] .events,body[data-theme=minimal] .rpmnum{display:none}
body[data-theme=minimal] #gear{font-size:calc(var(--u)*19);font-weight:300}
body[data-theme=minimal] .led{height:calc(var(--u)*1.1);border:none;border-radius:2px}
body[data-theme=minimal] .revmeta{display:none}
/* ===== 테마: neon (스캔라인을 앞 레이어로 — 불투명 그라데이션이 가리지 않게) ===== */
body[data-theme=neon]{--bg:#0d0221;--panel:#170b33;--line:#3b1a6e;--tx:#f3e9ff;
  --dim:#8f7bb8;--acc:#ff2bd6;--seg-off:#1d1040;--logline:#1f1244;
  --gauge-fg:#2be2ff;--gauge-dim:#8f7bb8;
  background-image:repeating-linear-gradient(transparent 0 39px,rgba(255,43,214,.07) 39px 40px),
   linear-gradient(#0d0221 60%,#1b0640)}
body[data-theme=neon] #gear{background:linear-gradient(180deg,#2be2ff,#ff2bd6);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 calc(var(--u)*1.3) rgba(255,43,214,.5))}
body[data-theme=neon] #gearA{color:#2be2ff;
  filter:drop-shadow(0 0 calc(var(--u)*1.3) rgba(255,43,214,.5))}
body[data-theme=neon] .led{border-radius:calc(var(--u)*.9);
  box-shadow:inset 0 0 6px rgba(0,0,0,.6)}
body[data-theme=neon] .panel{box-shadow:0 0 calc(var(--u)*2.2) rgba(59,26,110,.35)}
</style></head>
<body data-theme="pit" data-display="digital">
<div id="ambient"></div><div id="flash"></div>
<header>
  <span class="brand">RS50 × FH6</span>
  <span class="badge off" id="mode">대기</span>
  <span class="dot" id="teldot"></span>
  <div class="switchers">
    <nav class="sw" id="displaysw"></nav>
    <nav class="sw" id="themes"></nav>
  </div>
</header>
<main>
<section class="cluster">
  <div class="panel tacho" id="tacho">
    <svg viewBox="0 0 200 200">
      <g id="ticks"></g>
      <path id="redzone" fill="none" stroke="#ff3b3b" stroke-width="6" opacity=".8"/>
      <line id="needle" x1="100" y1="100" x2="100" y2="24"
            stroke-width="3.5" stroke-linecap="round"
            style="transform-origin:100px 100px;
                   filter:drop-shadow(0 0 3px rgba(0,0,0,.6))"/>
      <circle id="hub" cx="100" cy="100" r="7"/>
      <text id="gunit" x="100" y="168" text-anchor="middle"
            font-size="9" letter-spacing="2">% REDLINE</text>
    </svg>
    <div id="gearA">-</div>
  </div>
  <div class="panel block gearblk"><small>GEAR</small><div id="gear">-</div></div>
  <div class="panel block"><span class="vnum" id="speed">0</span><small>KM/H</small></div>
  <div class="panel block driftblk">
    <span class="vnum"><span id="darrow"></span><span id="drift">0</span>°</span>
    <small>DRIFT <span id="dpeak"></span></small></div>
  <div class="panel block gblk">
    <div class="gtrack"><div class="gtick"></div><div id="gdot"></div></div>
    <small>LAT G <span id="gval">0.0</span></small></div>
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
const N=10;
/* 프리셋 색은 /state의 seg_colors로 동기화 (물리 휠과 항상 일치); 폴백 = f1 */
let SEG=['var(--grn)','var(--grn)','var(--grn)','var(--red)','var(--red)',
         'var(--red)','var(--red)','var(--blu)','var(--blu)','var(--blu)'];
let BLINK_COLOR='var(--pur)';
const THEMES=[['pit','PIT'],['f1','F1'],['retro','RETRO'],['minimal','OLED'],['neon','NEON']];
const DISPLAYS=[['digital','DIGITAL'],['analog','ANALOG']];
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
/* --u의 픽셀 환산 (JS 인라인 글로우용) */
const upx=()=>Math.min(innerWidth/100,innerHeight/56.25);

function buildSwitch(navId, items, dataKey, storeKey, defval){
  const nav=$(navId);
  items.forEach(([key,label])=>{
    const b=document.createElement('button');
    b.textContent=label; b.dataset.v=key;
    b.onclick=()=>set(key);
    nav.appendChild(b);
  });
  function set(v){
    document.body.dataset[dataKey]=v;
    localStorage.setItem(storeKey,v);
    [...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  }
  const stored=localStorage.getItem(storeKey);
  set(items.some(([k])=>k===stored)?stored:defval);  // 무효 저장값 방어
}
buildSwitch('themes',THEMES,'theme','rs50-theme','pit');
buildSwitch('displaysw',DISPLAYS,'display','rs50-display','digital');

/* rev 스트립 */
const strip=$('strip');
for(let i=0;i<N;i++){const d=document.createElement('div');d.className='led';strip.appendChild(d);}
const leds=[...strip.children];

/* 타코 눈금: 스윕 -120°..+120°, 단위 = 레드라인 대비 % (짝수눈금 0..100) */
const tickG=$('ticks');
for(let i=0;i<=10;i++){
  const a=(-120+i*24)*Math.PI/180, r1=86, r2=i%2?78:72;
  const x1=100+r1*Math.sin(a), y1=100-r1*Math.cos(a);
  const x2=100+r2*Math.sin(a), y2=100-r2*Math.cos(a);
  tickG.innerHTML+=`<line class="tick${i>=9?' red':''}" x1="${x1}" y1="${y1}"
    x2="${x2}" y2="${y2}" stroke-width="${i%2?1.5:3}"/>`
   + (i%2?'':`<text class="tlabel" x="${100+58*Math.sin(a)}"
      y="${100-58*Math.cos(a)+3}" text-anchor="middle" font-size="10">${i*10}</text>`);
}
function drawRedzone(from){
  const a0=(-120+from*240)*Math.PI/180, a1=120*Math.PI/180, r=90;
  $('redzone').setAttribute('d',`M ${100+r*Math.sin(a0)} ${100-r*Math.cos(a0)}
   A ${r} ${r} 0 0 1 ${100+r*Math.sin(a1)} ${100-r*Math.cos(a1)}`);
}
drawRedzone(0.95);

/* ===== 서버 폴링(150ms, 목표값) + 60fps 보간 렌더 ===== */
let T={ratio:0,rpm:0,speed_kmh:0,max_rpm:0,alive:false,gear:null,mode:'AUTO',
       start_ratio:.5,blink_ratio:.95,blink_hz:5,lat_g:0,drift_deg:0,events:[]};
let D={ratio:0,rpm:0,speed:0,drift:0,latg:0};
let driftPeak=0, driftPeakTs=0;
let lastEvents='', lastGear=null, fails=0, inflight=false, zoneDrawn=false;

async function poll(){
  if(inflight)return;               // 요청 겹침/역순 도착 방지
  inflight=true;
  try{
    T=await (await fetch('/state')).json();
    fails=0;
    if(!zoneDrawn&&T.blink_ratio){drawRedzone(T.blink_ratio);zoneDrawn=true;}
    if(T.seg_colors){SEG=T.seg_colors.ltr;BLINK_COLOR=T.seg_colors.blink;}
    const gtxt=T.gear===0?'R':(T.gear>10?'N':(T.gear||'-'));
    if(gtxt!==lastGear){
      for(const el of [$('gear'),$('gearA')]){
        el.classList.add('pop');setTimeout(()=>el.classList.remove('pop'),140);
      }
      lastGear=gtxt;
    }
    $('gear').textContent=gtxt; $('gearA').textContent=gtxt;
    $('maxrpm').textContent=Math.round(T.max_rpm);
    const b=$('mode');
    if(!T.alive){b.textContent='대기';b.className='badge off';}
    else if(T.mode==='AUTO'){b.textContent='AUTO';b.className='badge auto';}
    else{b.textContent='MANUAL';b.className='badge manual';}
    $('teldot').className='dot'+(T.alive?' on':'');
    const ev=T.events.map(e=>`<div><b>${esc(e[0])}</b> ${esc(e[1])}</div>`).reverse().join('');
    if(ev!==lastEvents){$('log').innerHTML=ev;lastEvents=ev;}
  }catch(e){
    if(++fails>=3){                 // 앱 종료/네트워크 단절을 명시적으로 표시
      T.alive=false;
      const b=$('mode');b.textContent='연결 끊김';b.className='badge lost';
      $('teldot').className='dot';
    }
  }finally{inflight=false;}
}
setInterval(poll,150); poll();

let lastRender=0, prevTs=null;
function render(ts){
  lastRender=performance.now();
  const dt=prevTs===null?1/60:Math.min(0.1,(ts-prevTs)/1000);
  prevTs=ts;
  const k=1-Math.exp(-dt*9);        // 프레임레이트 무관 보간
  D.ratio+=((T.alive?T.ratio:0)-D.ratio)*k;
  D.rpm  +=((T.alive?T.rpm:0)-D.rpm)*k;
  D.speed+=((T.alive?T.speed_kmh:0)-D.speed)*k;
  D.drift+=((T.alive?T.drift_deg:0)-D.drift)*k;
  D.latg +=((T.alive?T.lat_g:0)-D.latg)*k;

  $('rpm').textContent=Math.round(D.rpm);
  $('speed').textContent=Math.round(D.speed);
  $('ratio').textContent=Math.round(D.ratio*100)+'%';
  /* 드리프트 각 + 4초 피크 홀드 */
  const ad=Math.abs(D.drift);
  $('drift').textContent=ad.toFixed(0);
  $('darrow').textContent=ad<3?'':(D.drift<0?'◀':'▶');
  const nowMs=performance.now();
  if(ad>driftPeak||nowMs-driftPeakTs>4000){driftPeak=ad;driftPeakTs=nowMs;}
  $('dpeak').textContent=driftPeak>=10?('PK '+driftPeak.toFixed(0)+'°'):'';
  /* 횡G: ±2G 스케일 */
  $('gval').textContent=Math.abs(D.latg).toFixed(1);
  const gx=Math.max(-1,Math.min(1,D.latg/2));
  $('gdot').style.left=(50+gx*46)+'%';
  $('needle').style.transform=`rotate(${-120+Math.min(1,Math.max(0,D.ratio))*240}deg)`;

  const t=ts/1000, u=upx();
  const overRev=T.alive&&T.ratio>=T.blink_ratio;
  const blinkOn=overRev&&Math.floor(t*2*(T.blink_hz||5))%2===0;

  if(!T.alive){
    /* 아이들: 물리 휠과 동일한 파란 물결 미러 (ledctl._wave_frame 공식) */
    leds.forEach((el,i)=>{
      const ph=Math.sin(2*Math.PI*(t*0.8-i/N*1.4));
      const br=0.06+0.55*Math.max(0,ph)**2;
      el.style.background=`rgba(59,108,255,${(br*1.4).toFixed(2)})`;
      el.style.boxShadow=br>0.3?`0 0 ${(br*u*1.3).toFixed(0)}px rgba(59,108,255,.7)`:'none';
    });
  }else{
    const lit=D.ratio<=T.start_ratio?0:
      Math.min(N,Math.max(1,Math.round((D.ratio-T.start_ratio)/(T.blink_ratio-T.start_ratio)*N)));
    leds.forEach((el,i)=>{
      if(blinkOn){el.style.background=BLINK_COLOR;el.style.boxShadow=`0 0 ${(u*1.5).toFixed(0)}px ${BLINK_COLOR}`;}
      else if(overRev){el.style.background='var(--seg-off)';el.style.boxShadow='none';}
      else if(i<lit){el.style.background=SEG[i];el.style.boxShadow=`0 0 ${u.toFixed(0)}px ${SEG[i]}`;}
      else{el.style.background='var(--seg-off)';el.style.boxShadow='none';}
    });
  }
  $('shift').textContent=overRev?'SHIFT ▲':'';
  $('ambient').style.opacity=T.alive?Math.max(0,(D.ratio-0.75)/0.25*0.9).toFixed(2):0;
  $('flash').style.opacity=blinkOn?0.85:0;
}
function loop(ts){render(ts);requestAnimationFrame(loop);}
requestAnimationFrame(loop);
/* rAF가 멎는 환경(백그라운드 탭/일부 렌더러) 폴백 */
setInterval(()=>{if(performance.now()-lastRender>200)render(performance.now());},250);
</script></body></html>"""


SIDE_TMPL = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RS50 __SIDE__</title>
<style>
:root{--u:min(1vw,1.78vh);
  --grn:#2bd45f;--red:#ff3b3b;--blu:#3b6cff;--pur:#b93bff;--amb:#ffb020;
  --seg-off:#1a2029}
*{margin:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{height:100%}
body{background:var(--bg);color:var(--tx);display:flex;flex-direction:column;
     padding:calc(var(--u)*2);gap:calc(var(--u)*1.6);overflow:hidden}
#flash{position:fixed;inset:0;pointer-events:none;z-index:1;opacity:0;
  box-shadow:inset 0 0 calc(var(--u)*16) calc(var(--u)*3) var(--pur);
  transition:opacity .06s}
.top{display:flex;align-items:center;gap:calc(var(--u)*1.2)}
.brand{font-weight:800;letter-spacing:3px;font-size:calc(var(--u)*1.4);color:var(--dim)}
.dot{width:calc(var(--u)*1);height:calc(var(--u)*1);border-radius:50%;background:#444;
     margin-left:auto}
.dot.on{background:var(--grn);box-shadow:0 0 calc(var(--u)*1) var(--grn)}
.badge{font-size:calc(var(--u)*1.5);font-weight:800;letter-spacing:2px;
  padding:calc(var(--u)*.6) calc(var(--u)*1.5);border-radius:calc(var(--u)*.8)}
.badge.auto{background:#0d2d18;color:var(--grn)}
.badge.manual{background:#332309;color:var(--amb);animation:pulse 1.6s infinite}
.badge.off{background:#22262e;color:var(--dim)}
.badge.lost{background:#33090c;color:var(--red)}
@keyframes pulse{50%{box-shadow:0 0 calc(var(--u)*1.4) rgba(255,176,32,.5)}}
main{flex:1;display:flex;flex-direction:column;justify-content:center;
     align-items:center;gap:calc(var(--u)*2);min-height:0}
.big{text-align:center}
.big small{display:block;font-size:calc(var(--u)*1.6);color:var(--dim);
           letter-spacing:4px;margin-bottom:calc(var(--u)*.6)}
#gear{font-size:calc(var(--u)*30);font-weight:800;line-height:.95;
      transition:transform .12s}
#speed{font-size:calc(var(--u)*17);font-weight:800;line-height:1;
       font-variant-numeric:tabular-nums}
#drift{font-size:calc(var(--u)*24);font-weight:800;line-height:1;color:var(--acc);
       font-variant-numeric:tabular-nums}
#darrow{font-size:calc(var(--u)*10);vertical-align:middle}
.sub{font-size:calc(var(--u)*2.6);color:var(--dim);font-variant-numeric:tabular-nums}
.sub b{color:var(--tx)}
.pop{transform:scale(1.12)!important}
/* 횡G 대형 미터 */
.gwrap{width:min(80%,calc(var(--u)*56))}
.gtrack{position:relative;height:calc(var(--u)*2.4);background:var(--seg-off);
  border:1px solid var(--line);border-radius:calc(var(--u)*1.2)}
.gtick{position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--dim);opacity:.5}
#gdot{position:absolute;top:50%;left:50%;width:calc(var(--u)*2);height:calc(var(--u)*2);
  border-radius:50%;background:var(--acc);transform:translate(-50%,-50%);
  box-shadow:0 0 calc(var(--u)*1.4) var(--acc)}
.glabel{display:flex;justify-content:space-between;color:var(--dim);
  font-size:calc(var(--u)*1.3);margin-top:calc(var(--u)*.4)}
/* 이벤트 (right 전용) */
.events{width:100%;max-height:calc(var(--u)*22);overflow:hidden;
  font:calc(var(--u)*1.5)/1.8 Consolas,monospace}
.events div{color:var(--dim);animation:fadein .4s ease}
.events div b{color:var(--tx)}
@keyframes fadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1}}
/* rev 바: 바깥(모니터 끝) -> 중앙(게임) 방향으로 차오름 */
.rev{display:flex;gap:calc(var(--u)*.5);height:calc(var(--u)*7);
     flex-direction:__FLEXDIR__}
.rev div{flex:1;border-radius:calc(var(--u)*.6);background:var(--seg-off);
  border:1px solid var(--line);transition:background .05s,box-shadow .05s}
/* 테마 */
body[data-theme=pit]{--bg:#0b0e14;--panel:#141922;--line:#232b38;--tx:#e6edf3;
  --dim:#8b98a9;--acc:#3b6cff}
body[data-theme=f1]{--bg:#08080a;--line:#26262c;--tx:#fff;--dim:#77777f;--acc:#e10600;
  background-image:repeating-linear-gradient(45deg,#0a0a0d 0 3px,#08080a 3px 6px)}
body[data-theme=f1] #gear,body[data-theme=f1] #speed{font-style:italic}
body[data-theme=retro]{--bg:#0d0a06;--line:#3a2c14;--tx:#ffd9a0;--dim:#9c7b4a;
  --acc:#ffb020;--seg-off:#221808}
body[data-theme=minimal]{--bg:#000;--line:#111;--tx:#ddd;--dim:#555;--acc:#888;
  --seg-off:#111}
body[data-theme=neon]{--bg:#0d0221;--line:#3b1a6e;--tx:#f3e9ff;--dim:#8f7bb8;
  --acc:#ff2bd6;--seg-off:#1d1040;
  background-image:repeating-linear-gradient(transparent 0 39px,rgba(255,43,214,.07) 39px 40px),
   linear-gradient(#0d0221 60%,#1b0640)}
body[data-theme=neon] #gear{background:linear-gradient(180deg,#2be2ff,#ff2bd6);
  -webkit-background-clip:text;background-clip:text;color:transparent}
</style></head>
<body data-theme="pit">
<div id="flash"></div>
<div class="top"><span class="brand">RS50 · __LABEL__</span>
  <span class="badge off" id="mode">대기</span><span class="dot" id="teldot"></span></div>
<main id="main"></main>
<div class="rev" id="rev"></div>
<script>
const SIDE='__SIDE__', N=24;
document.body.dataset.theme=localStorage.getItem('rs50-theme')||'pit';
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

/* 사이드별 레이아웃 구성 */
if(SIDE==='left'){
  $('main').innerHTML=`
    <div class="big"><small>GEAR</small><div id="gear">-</div></div>
    <div class="big"><small>KM/H</small><div id="speed">0</div></div>
    <div class="sub"><b id="rpm">0</b> / <span id="maxrpm">0</span> RPM
      · <b id="ratio">0</b>%</div>
    <div class="gwrap"><div class="gtrack"><div class="gtick"></div><div id="gdot"></div></div>
      <div class="glabel"><span>-2G</span><span>LAT <b id="gval">0.0</b>G</span><span>+2G</span></div></div>`;
}else{
  $('main').innerHTML=`
    <div class="big"><small>DRIFT ANGLE</small>
      <div><span id="darrow"></span><span id="drift">0</span>°</div>
      <div class="sub">PEAK <b id="dpeak">-</b></div></div>
    <div class="sub">CLASS <b id="carclass">-</b> · PI <b id="carpi">-</b></div>
    <div class="events" id="log"></div>`;
}
const rev=$('rev');
for(let i=0;i<N;i++){const d=document.createElement('div');rev.appendChild(d);}
const segs=[...rev.children];

let T={ratio:0,alive:false,start_ratio:.5,blink_ratio:.9,seg_colors:null,events:[]};
let D={ratio:0,rpm:0,speed:0,drift:0,latg:0};
let lastGear=null,lastEvents='',fails=0,inflight=false,peak=0,peakTs=0;
const CLS=['D','C','B','A','S1','S2','X','X'];

async function poll(){
  if(inflight)return; inflight=true;
  try{
    T=await (await fetch('/state')).json(); fails=0;
    const b=$('mode');
    if(!T.alive){b.textContent='대기';b.className='badge off';}
    else if(T.mode==='AUTO'){b.textContent='AUTO';b.className='badge auto';}
    else{b.textContent='MANUAL';b.className='badge manual';}
    $('teldot').className='dot'+(T.alive?' on':'');
    if(SIDE==='left'){
      const g=T.gear===0?'R':(T.gear>10?'N':(T.gear||'-'));
      if(g!==lastGear){const el=$('gear');el.classList.add('pop');
        setTimeout(()=>el.classList.remove('pop'),140);lastGear=g;}
      $('gear').textContent=g;
      $('maxrpm').textContent=Math.round(T.max_rpm);
    }else{
      $('carclass').textContent=CLS[T.car_class]||'-';
      $('carpi').textContent=T.car_pi||'-';
      const ev=T.events.slice(-9).map(e=>`<div><b>${esc(e[0])}</b> ${esc(e[1])}</div>`)
        .reverse().join('');
      if(ev!==lastEvents){$('log').innerHTML=ev;lastEvents=ev;}
    }
  }catch(e){
    if(++fails>=3){T.alive=false;
      const b=$('mode');b.textContent='연결 끊김';b.className='badge lost';}
  }finally{inflight=false;}
}
setInterval(poll,150); poll();

let lastRender=0,prevTs=null;
function render(ts){
  lastRender=performance.now();
  const dt=prevTs===null?1/60:Math.min(0.1,(ts-prevTs)/1000); prevTs=ts;
  const k=1-Math.exp(-dt*9);
  D.ratio+=((T.alive?T.ratio:0)-D.ratio)*k;
  D.rpm+=((T.alive?T.rpm:0)-D.rpm)*k;
  D.speed+=((T.alive?T.speed_kmh:0)-D.speed)*k;
  D.drift+=((T.alive?T.drift_deg:0)-D.drift)*k;
  D.latg+=((T.alive?T.lat_g:0)-D.latg)*k;
  if(SIDE==='left'){
    $('speed').textContent=Math.round(D.speed);
    $('rpm').textContent=Math.round(D.rpm);
    $('ratio').textContent=Math.round(D.ratio*100);
    $('gval').textContent=Math.abs(D.latg).toFixed(1);
    $('gdot').style.left=(50+Math.max(-1,Math.min(1,D.latg/2))*46)+'%';
  }else{
    const ad=Math.abs(D.drift);
    $('drift').textContent=ad.toFixed(0);
    $('darrow').textContent=ad<3?'':(D.drift<0?'◀':'▶');
    const nowMs=performance.now();
    if(ad>peak||nowMs-peakTs>5000){peak=ad;peakTs=nowMs;}
    $('dpeak').textContent=peak>=10?peak.toFixed(0)+'°':'-';
  }
  /* rev 바 (바깥->중앙) */
  const over=T.alive&&T.ratio>=T.blink_ratio;
  const lit=D.ratio<=T.start_ratio?0:
    Math.min(N,Math.max(1,Math.round((D.ratio-T.start_ratio)/(T.blink_ratio-T.start_ratio)*N)));
  const SC=T.seg_colors&&T.seg_colors.ltr;
  segs.forEach((el,i)=>{
    if(over){const c=(T.seg_colors&&T.seg_colors.blink)||'var(--pur)';
      el.style.background=c;el.style.boxShadow=`0 0 14px ${c}`;}
    else if(T.alive&&i<lit){
      const c=SC?SC[Math.min(9,Math.floor(i*10/N))]:'var(--grn)';
      el.style.background=c;el.style.boxShadow=`0 0 10px ${c}`;}
    else{el.style.background='var(--seg-off)';el.style.boxShadow='none';}
  });
  $('flash').style.opacity=over?0.8:0;
}
function loop(ts){render(ts);requestAnimationFrame(loop);}
requestAnimationFrame(loop);
setInterval(()=>{if(performance.now()-lastRender>200)render(performance.now());},250);
</script></body></html>"""


def _side_page(side):
    label = "LEFT" if side == "left" else "RIGHT"
    flexdir = "row" if side == "left" else "row-reverse"
    return (SIDE_TMPL.replace("__SIDE__", side)
            .replace("__LABEL__", label)
            .replace("__FLEXDIR__", flexdir))


def _finite(x):
    return x if isinstance(x, (int, str, bool, list, type(None))) \
        else (x if math.isfinite(x) else 0.0)


def _sanitize(d):
    """NaN/Infinity는 JSON 표준 위반(response.json() 거부) -> 0으로 치환."""
    return {k: (_sanitize(v) if isinstance(v, dict) else _finite(v))
            for k, v in d.items()}


class WebUI(threading.Thread):
    def __init__(self, provider, port=8777, host="127.0.0.1", log=print):
        """provider() -> dict (JSON 직렬화 가능 상태 스냅샷)"""
        super().__init__(daemon=True, name="webui")
        self.provider = provider
        self.port = port
        self.host = host
        self.log = log

    def run(self):
        provider = self.provider

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep-alive (150ms 폴링 TCP 재접속 방지)

            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/state":
                    body = json.dumps(_sanitize(provider())).encode()
                    ctype = "application/json"
                elif self.path == "/":
                    body = PAGE.encode()
                    ctype = "text/html; charset=utf-8"
                elif self.path in ("/left", "/right"):
                    body = _side_page(self.path[1:]).encode()
                    ctype = "text/html; charset=utf-8"
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        class Server(ThreadingHTTPServer):
            # Windows에서 SO_REUSEADDR는 이중 바인드를 조용히 허용 -> 비활성화
            allow_reuse_address = False

        try:
            srv = Server((self.host, self.port), Handler)
        except OSError as e:
            self.log(f"[web] 대시보드 포트 {self.port} 사용 불가({e}) — 웹 UI 비활성")
            return
        srv.serve_forever()
