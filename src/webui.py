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
body[data-theme=gt]{--bg:#0a0d13;--panel:#0f141c;--line:#1c2431;--tx:#eef4fa;
  --dim:#5d6b7e;--acc:#2fd6cc;--seg-off:#151b25;
  background-image:radial-gradient(120% 90% at 50% -10%,#131a26 0,#0a0d13 60%)}
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
const THEMES=[['pit','PIT'],['gt','GT'],['f1','F1'],['retro','RETRO'],['minimal','OLED'],['neon','NEON']];
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
     padding:calc(var(--u)*1.6);padding-bottom:calc(var(--u)*7);
     gap:calc(var(--u)*1.4);overflow:hidden}
#flash{position:fixed;inset:0;pointer-events:none;z-index:1;opacity:0;
  box-shadow:inset 0 0 calc(var(--u)*5) calc(var(--u)*.8) var(--pur);
  transition:opacity .08s}
.top{display:flex;align-items:center;gap:calc(var(--u)*1);flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:3px;font-size:calc(var(--u)*1.3);color:var(--dim)}
.dot{width:calc(var(--u)*.9);height:calc(var(--u)*.9);border-radius:50%;background:#444}
.dot.on{background:var(--grn);box-shadow:0 0 calc(var(--u)*1) var(--grn)}
.badge{font-size:calc(var(--u)*1.3);font-weight:800;letter-spacing:2px;
  padding:calc(var(--u)*.5) calc(var(--u)*1.2);border-radius:calc(var(--u)*.7)}
.badge.auto{background:#0d2d18;color:var(--grn)}
.badge.manual{background:#332309;color:var(--amb);animation:pulse 1.6s infinite}
.badge.off{background:#22262e;color:var(--dim)}
.badge.lost{background:#33090c;color:var(--red)}
@keyframes pulse{50%{box-shadow:0 0 calc(var(--u)*1.4) rgba(255,176,32,.5)}}
.switchers{margin-left:auto;display:flex;gap:calc(var(--u)*1.4)}
.sw{display:flex;gap:calc(var(--u)*.4)}
.sw button{background:var(--panel);color:var(--dim);border:1px solid var(--line);
  border-radius:calc(var(--u)*.6);padding:calc(var(--u)*.4) calc(var(--u)*.9);
  font-size:calc(var(--u)*.95);letter-spacing:1px;cursor:pointer}
.sw button.on{color:var(--tx);border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.panel{background:var(--panel);border:1px solid var(--line);
  border-radius:calc(var(--u)*1.2)}
main{flex:1;min-height:0;display:grid;gap:calc(var(--u)*1.2)}
body[data-side=left] main{grid-template-columns:1fr 1fr;grid-template-rows:1fr}
body[data-side=right] main{grid-template-columns:1fr 1fr;
  grid-template-rows:1fr auto auto}
.cell{min-height:0;min-width:0;display:flex;flex-direction:column;
  align-items:stretch;justify-content:center;gap:calc(var(--u)*.8)}
.sq{position:relative;flex:1 1 0;width:100%;min-height:0;min-width:0}
.sq svg,.sq canvas{position:absolute;inset:0;width:100%;height:100%}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--u)*1);
  width:100%;height:100%;min-height:0}
.big{text-align:center;flex:0 0 auto}
.big small{display:block;font-size:calc(var(--u)*1.5);color:var(--dim);
           letter-spacing:4px;margin-bottom:calc(var(--u)*.5)}
#gear{font-size:calc(var(--u)*17);font-weight:800;line-height:.95;
      transition:transform .12s}
#speed{font-size:calc(var(--u)*16);font-weight:200;line-height:1;
       letter-spacing:calc(var(--u)*-0.4);font-variant-numeric:tabular-nums}

#drift{font-size:calc(var(--u)*13);font-weight:800;line-height:1;color:var(--acc);
       font-variant-numeric:tabular-nums}
#driftA{font-size:calc(var(--u)*6.5);font-weight:800;color:var(--acc);
        font-variant-numeric:tabular-nums}
#darrow,#darrowA{font-size:.55em;vertical-align:middle}
.sub{font-size:calc(var(--u)*2.2);color:var(--dim);font-variant-numeric:tabular-nums}
.sub b{color:var(--tx)}
.pop{transform:scale(1.12)!important}
/* 게이지 (SVG) */
.gauge{position:relative}
.gauge svg{display:block}
.tick{stroke:var(--gauge-dim)} .tick.red{stroke:var(--red)}
.tlabel{fill:var(--gauge-dim)}
.needle{stroke:var(--gauge-fg);filter:drop-shadow(0 0 3px rgba(0,0,0,.6))}
.ghost{stroke:var(--acc);opacity:.55}
.hub{fill:var(--gauge-fg)}
.gunit{fill:var(--gauge-dim)}

#spdTxt{position:absolute;left:50%;top:63%;transform:translate(-50%,-50%);
  font-size:calc(var(--u)*4);font-weight:200;font-variant-numeric:tabular-nums}
#gearA{position:absolute;left:50%;top:63%;transform:translate(-50%,-50%);
  font-size:calc(var(--u)*5.5);font-weight:800;transition:transform .12s}
#gearA.pop{transform:translate(-50%,-50%) scale(1.12)!important}
/* 횡G */
.gwrap{width:min(92%,calc(var(--u)*54));flex:0 0 auto;margin:0 auto}
.gtrack{position:relative;height:calc(var(--u)*2.2);background:var(--seg-off);
  border:1px solid var(--line);border-radius:calc(var(--u)*1.1)}
.gtick{position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--dim);opacity:.5}
#gdot{position:absolute;top:50%;left:50%;width:calc(var(--u)*1.8);height:calc(var(--u)*1.8);
  border-radius:50%;background:var(--acc);transform:translate(-50%,-50%);
  box-shadow:0 0 calc(var(--u)*1.3) var(--acc)}
.glabel{display:flex;justify-content:space-between;color:var(--dim);
  font-size:calc(var(--u)*1.2);margin-top:calc(var(--u)*.4)}
/* 이벤트 */
.events{display:none}
.events div{color:var(--dim);animation:fadein .4s ease}
.events div b{color:var(--tx)}
@keyframes fadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1}}
/* 표시 모드 전환 */
body[data-display=digital] .ana{display:none!important}
body[data-display=analog] .dig{display:none!important}
/* ===== 위젯 ===== */
.wrow{display:flex;gap:calc(var(--u)*1.4);align-items:stretch;justify-content:center;
  flex-wrap:wrap;width:100%}
canvas.widget{background:var(--panel);border:1px solid var(--line);
  border-radius:calc(var(--u)*1.2)}
#trace{width:100%;height:calc(var(--u)*9)}
.tires{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--u)*.7);
  width:100%;flex:0 0 auto}
.tire{background:var(--panel);border:1px solid var(--line);
  border-radius:calc(var(--u)*.9);padding:calc(var(--u)*.8);
  display:flex;flex-direction:column;gap:calc(var(--u)*.4)}
.tire .tl{display:flex;justify-content:space-between;
  font-size:calc(var(--u)*1.1);color:var(--dim);letter-spacing:1px}
.tire .tt{font-size:calc(var(--u)*2);font-weight:800;font-variant-numeric:tabular-nums}
.tbar{position:relative;height:calc(var(--u)*.9);background:var(--seg-off);
  border-radius:calc(var(--u)*.45);overflow:hidden}
.tbar div{position:absolute;left:0;top:0;bottom:0;border-radius:inherit}
.score{display:flex;gap:calc(var(--u)*2.2);font-size:calc(var(--u)*1.5);
  color:var(--dim);font-variant-numeric:tabular-nums;align-items:baseline}
.score b{color:var(--acc);font-size:calc(var(--u)*2.2)}
/* rev 바: 바깥(모니터 끝) -> 중앙(게임) — 상/하단 존 + SEG/불꽃 스타일 */
.revzone{position:relative;flex:0 0 auto;height:calc(var(--u)*2.4)}
body[data-revstyle=flame] .revzone{height:calc(var(--u)*3.4)}
body[data-revpos=top] #revBot{display:none}
.rev{display:flex;gap:calc(var(--u)*.9);height:100%;
     width:min(96%,calc(var(--u)*86));margin:0 auto;flex-direction:__FLEXDIR__}
.flamec{position:absolute;top:0;bottom:0;left:50%;transform:translateX(-50%);
  width:min(96%,calc(var(--u)*86));height:100%}
body[data-side=right] .flamec{transform:translateX(-50%) scaleX(-1)}
body[data-revstyle=seg] .flamec{display:none}
body[data-revstyle=flame] .rev{visibility:hidden}
.rev div{flex:1;border-radius:calc(var(--u)*1.2);background:var(--seg-off);
  border:1px solid var(--line);transition:background .05s,box-shadow .05s}
/* 좁은 창(폰/세로) 폴백: 단일 컬럼 스택 + 스크롤 허용 */
@media (max-width: 900px){
  body{overflow-y:auto}
  body[data-side=left] main,body[data-side=right] main{
    display:flex;flex-direction:column}
  .sq{height:auto;aspect-ratio:1}
  .sq svg,.sq canvas{position:static}
}
/* 테마 */
body[data-theme=pit]{--bg:#0b0e14;--panel:#141922;--line:#232b38;--tx:#e6edf3;
  --dim:#8b98a9;--acc:#3b6cff;--gauge-fg:#e6edf3;--gauge-dim:#8b98a9}
body[data-theme=f1]{--bg:#08080a;--panel:#111114;--line:#26262c;--tx:#fff;
  --dim:#77777f;--acc:#e10600;--gauge-fg:#fff;--gauge-dim:#77777f;
  background-image:repeating-linear-gradient(45deg,#0a0a0d 0 3px,#08080a 3px 6px)}
body[data-theme=f1] .panel{border-left:3px solid var(--acc)}
body[data-theme=f1] #gear,body[data-theme=f1] #speed,body[data-theme=f1] #gearA
  {font-style:italic}
body[data-theme=retro]{--bg:#0d0a06;--panel:#161007;--line:#3a2c14;--tx:#ffd9a0;
  --dim:#9c7b4a;--acc:#ffb020;--seg-off:#221808;
  --gauge-fg:#ffcf7d;--gauge-dim:#9c7b4a}
body[data-theme=retro] #gear,body[data-theme=retro] #gearA{color:#ffcf7d;
  text-shadow:0 0 calc(var(--u)*1.6) rgba(255,176,32,.45)}
body[data-theme=minimal]{--bg:#000;--panel:#000;--line:#111;--tx:#ddd;--dim:#555;
  --acc:#888;--seg-off:#111;--gauge-fg:#ccc;--gauge-dim:#444}
body[data-theme=neon]{--bg:#0d0221;--panel:#170b33;--line:#3b1a6e;--tx:#f3e9ff;
  --dim:#8f7bb8;--acc:#ff2bd6;--seg-off:#1d1040;
  --gauge-fg:#2be2ff;--gauge-dim:#8f7bb8;
  background-image:repeating-linear-gradient(transparent 0 39px,rgba(255,43,214,.07) 39px 40px),
   linear-gradient(#0d0221 60%,#1b0640)}
body[data-theme=neon] #gear,body[data-theme=neon] #gearA{
  background:linear-gradient(180deg,#2be2ff,#ff2bd6);
  -webkit-background-clip:text;background-clip:text;color:transparent}
/* 숫자 폰트 토글 — AA(Segoe)/DIN(Bahnschrift=실차 계기판 표준)/01(Consolas) */
body[data-numfont=segoe]{--numfont:'Segoe UI',system-ui,sans-serif}
body[data-numfont=din]{--numfont:Bahnschrift,'Segoe UI',sans-serif}
body[data-numfont=mono]{--numfont:Consolas,monospace}
#speed,#gear,#gearA,#spdTxt,#drift,#driftA,#dpeak,#dpeakA,#gval,
#rpm,#maxrpm,#ratio,.tire .tt,.score b,.sub b,
#gtTt text,#gtSt text,#gtGear,#gtSpd,#gtTpct,#gtAvg,#gtMax,
.tlabel{font-family:var(--numfont)}
/* GT 테마 — 디자인 패널 우승작 (GT7 럭셔리 클러스터) */
body[data-theme=gt]{--bg:#0a0d13;--panel:#0f141c;--line:#1c2431;--tx:#eef4fa;
  --dim:#5d6b7e;--acc:#2fd6cc;--seg-off:#151b25;
  --gauge-fg:#dfe7f0;--gauge-dim:#4a5769;
  background-image:radial-gradient(120% 90% at 50% -10%,#131a26 0,#0a0d13 60%)}
.gauge svg.face-gt{display:none}
body[data-theme=gt] .gauge svg.face-gt{display:block}
body[data-theme=gt] .gauge svg.face-std{display:none}
body[data-theme=gt] #gearA,body[data-theme=gt] #spdTxt{display:none}
body[data-theme=gt] .panel{border-radius:calc(var(--u)*1.6)}
</style></head>
<body data-theme="pit" data-display="analog" data-side="__SIDE__" data-revpos="top" data-revstyle="seg" data-numfont="segoe">
<div id="flash"></div>
<div class="top">
  <span class="brand">RS50 · __LABEL__</span>
  <span class="badge off" id="mode">대기</span><span class="dot" id="teldot"></span>
  <div class="switchers">
    <nav class="sw" id="fontsw"></nav>
    <nav class="sw" id="barsw"></nav>
    <nav class="sw" id="fxsw"></nav>
    <nav class="sw" id="displaysw"></nav>
    <nav class="sw" id="themes"></nav>
  </div>
</div>
<div class="revzone" id="revTop"><div class="rev" id="rev"></div>
  <canvas class="flamec" id="flameTop"></canvas></div>
<main id="main"></main>
<div class="revzone" id="revBot"><div class="rev" id="revB"></div>
  <canvas class="flamec" id="flameBot"></canvas></div>
<script>
const SIDE='__SIDE__', N=12;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const THEMES=[['pit','PIT'],['gt','GT'],['f1','F1'],['retro','RETRO'],['minimal','OLED'],['neon','NEON']];
const DISPLAYS=[['digital','DIG'],['analog','ANA']];

function buildSwitch(navId, items, dataKey, storeKey, defval, qsKey){
  const nav=$(navId);
  items.forEach(([key,label])=>{
    const b=document.createElement('button');
    b.textContent=label;b.dataset.v=key;b.onclick=()=>set(key,true);
    nav.appendChild(b);
  });
  function set(v,persist){
    document.body.dataset[dataKey]=v;
    if(persist)localStorage.setItem(storeKey,v);
    [...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  }
  const q=new URLSearchParams(location.search).get(qsKey);
  const pick=[q,localStorage.getItem(storeKey)].find(x=>items.some(([k])=>k===x));
  set(pick||defval,false);
}
buildSwitch('themes',THEMES,'theme','rs50-theme','pit','th');
buildSwitch('displaysw',DISPLAYS,'display','rs50-display-'+SIDE,'analog','dsp');
buildSwitch('barsw',[['top','BAR\u2009\u25b2'],['both','BAR\u2009\u25b2\u25bc']],
  'revpos','rs50-revpos-'+SIDE,'top','bar');
buildSwitch('fxsw',[['seg','SEG'],['flame','FIRE']],
  'revstyle','rs50-revstyle-'+SIDE,'seg','fx');
buildSwitch('fontsw',[['segoe','AA'],['din','DIN'],['mono','01']],
  'numfont','rs50-numfont-'+SIDE,'segoe','fn');

/* ===== 레이아웃 ===== */
if(SIDE==='left'){
  $('main').innerHTML=`
    <div class="cell">
    <div class="gauge panel ana sq" id="tachoWrap" style="padding:calc(var(--u)*1)">
      <svg class="face-std" viewBox="0 0 200 200">
        <defs>
          <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.6" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <path d="M 22.1 145 A 90 90 0 1 1 177.9 145" fill="none"
              stroke="var(--seg-off)" stroke-width="9" stroke-linecap="round"/>
        <path id="tarc" d="M 22.1 145 A 90 90 0 1 1 177.9 145" fill="none"
              pathLength="100" stroke="var(--acc)" stroke-width="9"
              stroke-linecap="round" stroke-dasharray="0 100" filter="url(#glow)"/>
        <g id="ticks"></g>
        <path id="redzone" fill="none" stroke="#ff3b3b" stroke-width="4" opacity=".9"/>
        <line id="needle" class="needle" x1="100" y1="100" x2="100" y2="26"
              stroke-width="2.5" stroke-linecap="round" filter="url(#glow)"
              style="transform-origin:100px 100px"/>
        <circle class="hub" cx="100" cy="100" r="7"/>
        <text class="gunit" x="100" y="170" text-anchor="middle" font-size="9"
              letter-spacing="2">% REDLINE</text>
      </svg>
      <svg class="face-gt" viewBox="0 0 1000 1000">
        <defs>
          <filter id="gtglow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="7" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <pattern id="gthatch" patternUnits="userSpaceOnUse" width="12" height="12"
                   patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="12" stroke="#ffffff"
                  stroke-width="4" opacity="0.28"/>
          </pattern>
        </defs>
        <text x="40" y="985" font-size="22" letter-spacing="6" fill="var(--dim)">&#8212; TACHO</text>
        <text x="960" y="985" font-size="22" letter-spacing="6" fill="var(--dim)" text-anchor="end">CLUSTER &#183; __LABEL__</text>
        <path d="M 93 735 A 470 470 0 1 1 907 735" fill="none"
              stroke="var(--seg-off)" stroke-width="12" stroke-linecap="round"/>
        <path id="gtTarc" d="M 93 735 A 470 470 0 1 1 907 735" fill="none"
              pathLength="100" stroke="var(--acc)" stroke-width="12"
              stroke-linecap="round" stroke-dasharray="0 100" filter="url(#gtglow)"/>
        <path d="M 929.9 360.4 A 452 452 0 0 1 949.6 547.3" fill="none"
              stroke="var(--amb)" stroke-width="16" opacity=".9"/>
        <path d="M 949.6 547.3 A 452 452 0 0 1 891.4 726" fill="none"
              stroke="var(--red)" stroke-width="16"/>
        <path d="M 949.6 547.3 A 452 452 0 0 1 891.4 726" fill="none"
              stroke="url(#gthatch)" stroke-width="16"/>
        <g id="gtTt"></g>
        <circle cx="500" cy="500" r="195" fill="var(--panel)"
                stroke="var(--line)" stroke-width="2"/>
        <circle cx="500" cy="500" r="150" fill="none" stroke="var(--line)"
                stroke-width="1" opacity=".5"/>
        <g id="gtTng" style="transform-origin:500px 500px">
          <polygon points="492,305 508,305 502.5,85 497.5,85" fill="var(--red)"/>
          <line x1="500" y1="295" x2="500" y2="95" stroke="var(--tx)"
                stroke-width="2" opacity=".85"/>
        </g>
        <text x="500" y="430" font-size="26" letter-spacing="10" fill="var(--dim)" text-anchor="middle">GEAR</text>
        <text id="gtGear" x="500" y="648" font-size="230" font-weight="250" fill="var(--tx)" text-anchor="middle">-</text>
        <text id="gtTpct" x="500" y="890" font-size="88" font-weight="300" fill="var(--tx)" text-anchor="middle">0</text>
        <text x="500" y="945" font-size="26" letter-spacing="8" fill="var(--dim)" text-anchor="middle">% REDLINE</text>
      </svg>
      <div id="gearA">-</div>
    </div>
    <div class="big dig"><small>GEAR</small><div id="gear">-</div></div>
    <div class="big dig"><small>KM/H</small><div id="speed">0</div></div>
    <div class="sub dig"><b id="rpm">0</b> / <span id="maxrpm">0</span> RPM
      · <b id="ratio">0</b>%</div>
    </div>
    <div class="cell">
      <div class="gauge panel ana sq" id="spdWrap" style="padding:calc(var(--u)*1)">
        <svg class="face-std" viewBox="0 0 200 200">
          <defs>
          <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.6" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <path d="M 22.1 145 A 90 90 0 1 1 177.9 145" fill="none"
              stroke="var(--seg-off)" stroke-width="9" stroke-linecap="round"/>
          <path id="sarc" d="M 22.1 145 A 90 90 0 1 1 177.9 145" fill="none"
                pathLength="100" stroke="var(--acc)" stroke-width="9"
                stroke-linecap="round" stroke-dasharray="0 100" filter="url(#glow)"/>
          <g id="sticks"></g>
          <line id="sneedle" class="needle" x1="100" y1="100" x2="100" y2="26"
                stroke-width="2.5" stroke-linecap="round" filter="url(#glow)"
                style="transform-origin:100px 100px"/>
          <circle class="hub" cx="100" cy="100" r="7"/>
          <text class="gunit" x="100" y="170" text-anchor="middle" font-size="9"
                letter-spacing="2">KM/H</text>
        </svg>
        <svg class="face-gt" viewBox="0 0 1000 1000">
          <path d="M 93 735 A 470 470 0 1 1 907 735" fill="none"
                stroke="var(--seg-off)" stroke-width="12" stroke-linecap="round"/>
          <path id="gtSarc" d="M 93 735 A 470 470 0 1 1 907 735" fill="none"
                pathLength="100" stroke="var(--acc)" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="0 100" filter="url(#gtglow)"/>
          <g id="gtSt"></g>
          <g id="gtSng" style="transform-origin:500px 500px">
            <polygon points="493,470 507,470 502.5,122 497.5,122" fill="var(--red)"/>
          </g>
          <circle cx="500" cy="500" r="42" fill="var(--panel)"
                  stroke="var(--line)" stroke-width="2"/>
          <circle cx="500" cy="500" r="14" fill="var(--gauge-fg)"/>
          <text id="gtSpd" x="500" y="680" font-size="150" font-weight="250" fill="var(--tx)" text-anchor="middle">0</text>
          <text x="500" y="730" font-size="28" letter-spacing="8" fill="var(--dim)" text-anchor="middle">KM/H</text>
          <text x="60" y="880" font-size="24" letter-spacing="6" fill="var(--dim)">AVG</text>
          <text id="gtAvg" x="60" y="936" font-size="52" font-weight="300" fill="var(--tx)">-</text>
          <text x="940" y="880" font-size="24" letter-spacing="6" fill="var(--dim)" text-anchor="end">MAX</text>
          <text id="gtMax" x="940" y="936" font-size="52" font-weight="300" fill="var(--tx)" text-anchor="end">-</text>
        </svg>
        <div id="spdTxt">0</div>
      </div>
      <div class="sq"><canvas id="gg" class="widget"></canvas></div>
    </div>`;
  /* 타코 눈금 (0..100%) + 속도계 눈금 (0..300) — 스윕 -120..+120 */
  const tg=$('ticks');
  for(let i=0;i<=10;i++){
    const a=(-120+i*24)*Math.PI/180, r1=86, r2=i%2?78:72;
    tg.innerHTML+=`<line class="tick${i>=9?' red':''}"
      x1="${100+r1*Math.sin(a)}" y1="${100-r1*Math.cos(a)}"
      x2="${100+r2*Math.sin(a)}" y2="${100-r2*Math.cos(a)}"
      stroke-width="${i%2?1.5:3}"/>`
     +(i%2?'':`<text class="tlabel" x="${100+58*Math.sin(a)}"
        y="${100-58*Math.cos(a)+3}" text-anchor="middle" font-size="10">${i*10}</text>`);
  }
  const sg=$('sticks');
  for(let v=0;v<=300;v+=30){
    const a=(-120+v/300*240)*Math.PI/180, r1=86, r2=(v%60===0)?72:78;
    sg.innerHTML+=`<line class="tick" x1="${100+r1*Math.sin(a)}" y1="${100-r1*Math.cos(a)}"
      x2="${100+r2*Math.sin(a)}" y2="${100-r2*Math.cos(a)}"
      stroke-width="${v%60===0?3:1.5}"/>`
     +(v%60===0?`<text class="tlabel" x="${100+58*Math.sin(a)}"
        y="${100-58*Math.cos(a)+3}" text-anchor="middle" font-size="9">${v}</text>`:'');
  }
  /* GT 페이스 눈금: 3계층 (주/보조/미세) + 부유 숫자 */
  let gtm='';
  for(let v=0;v<=100;v++){
    const a=(-120+v*2.4)*Math.PI/180,si=Math.sin(a),co=Math.cos(a);
    let r1,r2,w0,op;
    if(v%10===0){r1=470;r2=436;w0=5;op=1;}
    else if(v%5===0){r1=468;r2=448;w0=2.5;op=.8;}
    else{r1=464;r2=454;w0=1.2;op=.35;}
    const rd=v>=90;
    gtm+=`<line x1="${500+r1*si}" y1="${500-r1*co}" x2="${500+r2*si}" y2="${500-r2*co}"
      stroke="${rd?'var(--red)':'var(--gauge-dim)'}" stroke-width="${w0}" opacity="${op}"/>`;
    if(v%10===0)gtm+=`<text x="${500+385*si}" y="${500-385*co+16}" font-size="46"
      font-weight="300" text-anchor="middle"
      fill="${rd?'var(--red)':'var(--gauge-fg)'}">${v}</text>`;
  }
  $('gtTt').innerHTML=gtm;
  let gts='';
  for(let v=0;v<=300;v+=5){
    const a=(-120+v*0.8)*Math.PI/180,si=Math.sin(a),co=Math.cos(a);
    let r1,r2,w0,op;
    if(v%50===0){r1=470;r2=436;w0=5;op=1;}
    else if(v%25===0){r1=468;r2=448;w0=2.5;op=.8;}
    else{r1=464;r2=454;w0=1.2;op=.35;}
    gts+=`<line x1="${500+r1*si}" y1="${500-r1*co}" x2="${500+r2*si}" y2="${500-r2*co}"
      stroke="var(--gauge-dim)" stroke-width="${w0}" opacity="${op}"/>`;
    if(v%50===0)gts+=`<text x="${500+385*si}" y="${500-385*co+16}" font-size="42"
      font-weight="300" text-anchor="middle" fill="var(--gauge-fg)">${v}</text>`;
  }
  $('gtSt').innerHTML=gts;
}else{
  $('main').innerHTML=`
    <div class="cell">
    <div class="gauge panel ana sq" id="driftGWrap" style="padding:calc(var(--u)*1)">
      <svg viewBox="0 0 240 150">
        <g id="dticks"></g>
        <line id="dghost" class="ghost" x1="120" y1="130" x2="120" y2="34"
              stroke-width="2" style="transform-origin:120px 130px"/>
        <line id="dneedle" class="needle" x1="120" y1="130" x2="120" y2="30"
              stroke-width="4" stroke-linecap="round"
              style="transform-origin:120px 130px"/>
        <circle class="hub" cx="120" cy="130" r="7"/>
        <text class="gunit" x="120" y="147" text-anchor="middle" font-size="9"
              letter-spacing="2">DRIFT °</text>
      </svg>
    </div>
    <div class="big ana"><span id="darrowA"></span><span id="driftA">0</span><span class="sub">° · PK <b id="dpeakA">-</b></span></div>
    <div class="big dig"><small>DRIFT ANGLE</small>
      <div><span id="darrow"></span><span id="drift">0</span>°</div>
      <div class="sub">PEAK <b id="dpeak">-</b></div></div>
    <div class="gwrap"><div class="gtrack"><div class="gtick"></div><div id="gdot"></div></div>
      <div class="glabel"><span>-2G</span><span>LAT <b id="gval">0.0</b>G</span><span>+2G</span></div></div>
    </div>
    <div class="cell">
      <div class="sq"><canvas id="map" class="widget"></canvas></div>
      <div class="tires" id="tires"></div>
    </div>
    <div class="cell" style="grid-column:1/3">
      <canvas id="trace" class="widget" style="flex:0 0 auto"></canvas>
    </div>
    <div class="cell" style="grid-column:1/3">
    <div class="score">
      <span>PK <b id="sPk">0</b>°</span><span>MAX <b id="sG">0.0</b>G</span>
      <span>드리프트 <b id="sHold">0.0</b>s</span>
      <span>CLASS <b id="carclass">-</b>·PI <b id="carpi">-</b></span>
    </div>
    </div>`;
  for(const wn of ['fl','fr','rl','rr']){
    const d=document.createElement('div');d.className='tire';
    d.innerHTML=`<div class="tl"><span>${wn.toUpperCase()}</span><span class="tt" id="tt_${wn}">-</span></div>
      <div class="tbar"><div id="ts_${wn}"></div></div>
      <div class="tbar"><div id="tu_${wn}" style="background:var(--dim);opacity:.7"></div></div>`;
    $('tires').appendChild(d);
  }
  const tg=$('dticks');
  for(let d=-60;d<=60;d+=15){
    const a=d/60*75*Math.PI/180, r1=96, r2=(d%30===0)?84:90;
    tg.innerHTML+=`<line class="tick" x1="${120+r1*Math.sin(a)}" y1="${130-r1*Math.cos(a)}"
      x2="${120+r2*Math.sin(a)}" y2="${130-r2*Math.cos(a)}"
      stroke-width="${d%30===0?3:1.5}"/>`
     +(d%30===0?`<text class="tlabel" x="${120+72*Math.sin(a)}"
        y="${130-72*Math.cos(a)+3}" text-anchor="middle" font-size="10">${Math.abs(d)}</text>`:'');
  }
}
const rev=$('rev'),revB=$('revB');
for(const cont of [rev,revB])
  for(let i=0;i<N;i++){cont.appendChild(document.createElement('div'));}
const segs=[...rev.children,...revB.children];

/* ===== 데이터 엔진 (폴링 + 60fps 보간 + rAF 폴백) ===== */
let T={ratio:0,alive:false,start_ratio:.5,blink_ratio:.9,seg_colors:null,events:[]};
let D={ratio:0,rpm:0,speed:0,drift:0,latg:0,longg:0};
/* 일반화 지수 스무더 — 채널별 반응속도(rate/s) 차등, NaN 방어 */
const SM={};
function sm(key,target,rate,dt){
  if(!isFinite(target))target=0;
  const v=isFinite(SM[key])?SM[key]:target;
  return SM[key]=v+(target-v)*(1-Math.exp(-dt*rate));
}
let lastGear=null,lastEvents='',fails=0,inflight=false,peak=0,peakTs=0,peakSign=1;
const CLS=['D','C','B','A','S1','S2','X','X'];

async function poll(){
  if(inflight)return; inflight=true;
  try{
    T=await (await fetch('/state')).json(); fails=0;
    const cl=(v,lo,hi)=>isFinite(v)?Math.min(hi,Math.max(lo,v)):0;
    T.ratio=cl(T.ratio,0,1.5);T.speed_kmh=cl(T.speed_kmh,0,600);
    T.rpm=cl(T.rpm,0,30000);T.max_rpm=cl(T.max_rpm,0,30000);
    T.lat_g=cl(T.lat_g,-4,4);T.long_g=cl(T.long_g,-4,4);
    T.drift_deg=cl(T.drift_deg,-90,90);
    const b=$('mode');
    if(!T.alive){b.textContent='대기';b.className='badge off';}
    else if(T.mode==='AUTO'){b.textContent='AUTO';b.className='badge auto';}
    else{b.textContent='MANUAL';b.className='badge manual';}
    $('teldot').className='dot'+(T.alive?' on':'');
    if(SIDE==='left'){
      const g=T.gear===0?'R':(T.gear>10?'N':(T.gear||'-'));
      if(g!==lastGear){for(const id of ['gear','gearA']){const el=$(id);
        el.classList.add('pop');setTimeout(()=>el.classList.remove('pop'),140);}
        lastGear=g;}
      $('gear').textContent=g;$('gearA').textContent=g;
      $('maxrpm').textContent=Math.round(T.max_rpm);
    }else{
      $('carclass').textContent=CLS[T.car_class]||'-';
      $('carpi').textContent=T.car_pi||'-';
    }
  }catch(e){
    if(++fails>=3){T.alive=false;
      const b=$('mode');b.textContent='연결 끊김';b.className='badge lost';}
  }finally{inflight=false;}
}
setInterval(poll,150); poll();

let lastRender=0,prevTs=null,spdSum=0,spdT=0,spdMax=0;
function render(ts){
  lastRender=performance.now();
  const dt=prevTs===null?1/60:Math.min(0.1,Math.max(0.001,(ts-prevTs)/1000));
  prevTs=ts;
  const k=1-Math.exp(-dt*9);
  for(const key in D)if(!isFinite(D[key]))D[key]=0;  // 오염 복구
  D.speed=Math.min(600,Math.max(0,D.speed));D.ratio=Math.min(1.5,Math.max(0,D.ratio));
  D.rpm=Math.min(30000,Math.max(0,D.rpm));
  D.drift=Math.min(90,Math.max(-90,D.drift));D.latg=Math.min(4,Math.max(-4,D.latg));
  D.longg=Math.min(4,Math.max(-4,D.longg));
  D.ratio+=((T.alive?T.ratio:0)-D.ratio)*k;
  D.rpm+=((T.alive?T.rpm:0)-D.rpm)*k;
  D.speed+=((T.alive?T.speed_kmh:0)-D.speed)*k;
  D.drift+=((T.alive?T.drift_deg:0)-D.drift)*k;
  D.latg+=((T.alive?T.lat_g:0)-D.latg)*k;
  D.longg+=((T.alive?T.long_g:0)-D.longg)*k;
  /* 입력/타이어/좌표 — 150ms 틱 -> 프레임 보간 (빠른 채널일수록 rate 높게) */
  sm('thr',(T.accel||0)/255,18,dt);sm('brk',(T.brake||0)/255,18,dt);
  sm('st',(T.steer||0)/127,18,dt);sm('hb',(T.handbrake||0)/255,18,dt);
  sm('px',T.pos_x||0,12,dt);sm('pz',T.pos_z||0,12,dt);
  const WH=T.wheels||{};
  for(const wn of ['fl','fr','rl','rr']){const d=WH[wn]||{};
    sm('t_'+wn,d.temp_c||0,4,dt);sm('c_'+wn,d.combined||0,10,dt);
    sm('u_'+wn,d.sus||0,14,dt);}

  if(SIDE==='left'){
    $('speed').textContent=Math.round(D.speed);
    $('spdTxt').textContent=Math.round(D.speed);
    $('rpm').textContent=Math.round(D.rpm);
    $('ratio').textContent=Math.round(D.ratio*100);
    $('needle').style.transform=
      `rotate(${-120+Math.min(1,Math.max(0,D.ratio))*240}deg)`;
    $('sneedle').style.transform=
      `rotate(${-120+Math.min(1,Math.max(0,D.speed/300))*240}deg)`;
    $('tarc').setAttribute('stroke-dasharray',
      `${Math.min(100,Math.max(0,D.ratio*100))} 100`);
    $('sarc').setAttribute('stroke-dasharray',
      `${Math.min(100,Math.max(0,D.speed/3))} 100`);
    /* GT 페이스 */
    const rr=Math.min(1,Math.max(0,D.ratio)),sv=Math.min(300,D.speed);
    $('gtTarc').setAttribute('stroke-dasharray',`${rr*100} 100`);
    $('gtTng').style.transform=`rotate(${-120+rr*240}deg)`;
    $('gtTpct').textContent=Math.round(D.ratio*100);
    $('gtGear').textContent=$('gear').textContent;
    $('gtSarc').setAttribute('stroke-dasharray',`${sv/3} 100`);
    $('gtSng').style.transform=`rotate(${-120+sv/300*240}deg)`;
    $('gtSpd').textContent=Math.round(D.speed);
    if(T.alive&&D.speed>1){spdSum+=D.speed*dt;spdT+=dt;
      spdMax=Math.max(spdMax,D.speed);}
    $('gtAvg').textContent=spdT>3?Math.round(spdSum/spdT):'-';
    $('gtMax').textContent=spdMax>1?Math.round(spdMax):'-';
  }else{
    const ad=Math.abs(D.drift);
    $('drift').textContent=ad.toFixed(0);
    $('driftA').textContent=ad.toFixed(0);
    const ar=ad<3?'':(D.drift<0?'◀':'▶');
    $('darrow').textContent=ar;$('darrowA').textContent=ar;
    const nowMs=performance.now();
    if(ad>peak||nowMs-peakTs>5000){peak=ad;peakTs=nowMs;peakSign=D.drift<0?-1:1;}
    const pk=peak>=10?peak.toFixed(0)+'°':'-';
    $('dpeak').textContent=pk;$('dpeakA').textContent=pk;
    const clamp=v=>Math.max(-60,Math.min(60,v));
    $('dneedle').style.transform=`rotate(${clamp(D.drift)/60*75}deg)`;
    $('dghost').style.transform=`rotate(${clamp(peak*peakSign)/60*75}deg)`;
    $('dghost').style.opacity=peak>=10?.55:0;
    $('gval').textContent=Math.abs(D.latg).toFixed(1);
    $('gdot').style.left=(50+Math.max(-1,Math.min(1,D.latg/2))*46)+'%';
  }
  sampleAndDraw(ts);
  /* rev 바 (바깥->중앙) */
  const over=T.alive&&T.ratio>=T.blink_ratio;
  /* 오버레브: 실차식 풀스트립 고속 점멸 (웹은 FFB 제약 없음 — 화끈하게) */
  const blinkOn=over&&Math.floor(ts/1000*2*(T.blink_hz||8))%2===0;
  const lit=D.ratio<=T.start_ratio?0:
    Math.min(N,Math.max(1,Math.round((D.ratio-T.start_ratio)/(T.blink_ratio-T.start_ratio)*N)));
  const SC=T.seg_colors&&T.seg_colors.ltr;
  segs.forEach((el,i)=>{
    if(over){const c=(T.seg_colors&&T.seg_colors.blink)||'var(--pur)';
      if(blinkOn){el.style.background=c;
        el.style.boxShadow=`0 0 14px ${c},0 0 34px ${c}`;}
      else{el.style.background='var(--seg-off)';el.style.boxShadow='none';}}
    else if(T.alive&&i<lit){
      const c=SC?SC[Math.min(9,Math.floor(i*10/N))]:'var(--grn)';
      el.style.background=c;el.style.boxShadow=`0 0 10px ${c}`;}
    else{el.style.background='var(--seg-off)';el.style.boxShadow='none';}
  });
  $('flash').style.opacity=blinkOn?0.65:0;
  if(document.body.dataset.revstyle==='flame'){
    drawFlame('flameTop',ts);
    if(document.body.dataset.revpos==='both')drawFlame('flameBot',ts);
  }
}
/* ===== 위젯 엔진 ===== */
const BUF=[];let lastSample=0,maxG=0,holdStart=null,holdBest=0;
function cv(id){const c=$(id);if(!c)return null;
  const r=c.getBoundingClientRect(),dpr=devicePixelRatio||1;
  if(c.width!==Math.round(r.width*dpr)){c.width=Math.round(r.width*dpr);
    c.height=Math.round(r.height*dpr);}
  const g=c.getContext('2d');g.setTransform(c.width/r.width,0,0,c.height/r.height,0,0);
  return {g,w:r.width,h:r.height};}
function css(v){return getComputedStyle(document.body).getPropertyValue(v).trim();}
function NF(){return css('--numfont')||"'Segoe UI'";}

function sampleAndDraw(ts){
  const now=performance.now();
  if(now-lastSample>=16){
    lastSample=now;
    BUF.push({t:now,thr:SM.thr||0,brk:SM.brk||0,
      st:SM.st||0,hb:SM.hb||0,
      lg:D.latg,gg:D.longg,
      px:SM.px||0,pz:SM.pz||0});
    while(BUF.length&&now-BUF[0].t>20000)BUF.shift();
    const ad=Math.abs(T.alive?T.drift_deg:0);
    if(T.alive&&Math.abs(T.lat_g||0)>maxG)maxG=Math.abs(T.lat_g);
    if(ad>15){if(holdStart===null)holdStart=now;
      holdBest=Math.max(holdBest,(now-holdStart)/1000);}
    else holdStart=null;
  }
  if(SIDE==='left'){drawGG();}
  else{drawTires();drawTrace();drawMap();
    $('sPk').textContent=peak>=10?peak.toFixed(0):'0';
    $('sG').textContent=maxG.toFixed(1);
    $('sHold').textContent=holdBest.toFixed(1);}
}

function drawFlame(id,ts){
  const c=cv(id);if(!c)return;const{g,w,h}=c;
  g.clearRect(0,0,w,h);
  if(!T.alive||!w)return;
  const over=T.ratio>=T.blink_ratio;
  const blinkOn=over&&Math.floor(ts/1000*2*(T.blink_hz||8))%2===0;
  if(over&&!blinkOn)return;              /* 점멸 OFF 위상 */
  const frac=over?1:Math.min(1,Math.max(0,
    (D.ratio-T.start_ratio)/(T.blink_ratio-T.start_ratio)));
  if(frac<=0.005)return;
  const wl=w*frac,t=ts/1000;
  const SC=(T.seg_colors&&T.seg_colors.ltr)||['#2bd45f','#ffb020','#ff3b3b'];
  const blinkC=(T.seg_colors&&T.seg_colors.blink)||'#b93bff';
  const grad=g.createLinearGradient(0,0,w,0);
  if(over){grad.addColorStop(0,blinkC);grad.addColorStop(.6,'#ffffff');
    grad.addColorStop(1,blinkC);}
  else SC.forEach((cc,i)=>grad.addColorStop(i/(SC.length-1),cc));
  /* 불꽃 실루엣: 3중 사인 일렁임 + 리딩엣지 감쇠 */
  const NPT=Math.max(28,Math.round(wl/9)),ys=[];
  for(let i=0;i<=NPT;i++){
    const fx=i/NPT;
    const n=.5*Math.sin(fx*wl*.08+t*9)+.3*Math.sin(fx*wl*.21-t*14)
           +.2*Math.sin(fx*wl*.44+t*23);
    const lead=fx>.82?Math.max(.25,1-(fx-.82)/.18*.9):1;
    const fh=h*(.30+.62*(over?1:.85)*(.5+.5*n))*lead;
    ys.push(h-Math.max(2,fh));
  }
  const leadC=over?blinkC:SC[Math.min(SC.length-1,Math.floor(frac*SC.length))];
  g.shadowColor=leadC;g.shadowBlur=16;
  g.fillStyle=grad;
  g.beginPath();g.moveTo(0,h);
  ys.forEach((y,i)=>g.lineTo(i/NPT*wl,y));
  g.lineTo(wl,h);g.closePath();g.fill();
  g.shadowBlur=0;
  /* 화이트 코어 (하단 열기) */
  g.globalAlpha=.28;g.fillStyle='#fff';
  g.beginPath();g.moveTo(0,h);
  ys.forEach((y,i)=>g.lineTo(i/NPT*wl,h-(h-y)*.42));
  g.lineTo(wl,h);g.closePath();g.fill();
  g.globalAlpha=1;
}

function drawTires(){
  for(const wn of ['fl','fr','rl','rr']){
    const t=SM['t_'+wn]||0;
    const tc=t<60?'var(--blu)':(t<95?'var(--grn)':(t<110?'var(--amb)':'var(--red)'));
    const tt=$('tt_'+wn);tt.textContent=Math.round(t)+'°';tt.style.color=tc;
    const cs=Math.min(3,SM['c_'+wn]||0);
    const sc=cs<1?'var(--grn)':(cs<2?'var(--amb)':'var(--red)');
    const sb=$('ts_'+wn);sb.style.width=(cs/3*100)+'%';sb.style.background=sc;
    $('tu_'+wn).style.width=(Math.min(1,Math.max(0,SM['u_'+wn]||0))*100)+'%';
  }
}

function drawGG(){
  const c=cv('gg');if(!c)return;const{g,w,h}=c;
  g.clearRect(0,0,w,h);
  const cx=w/2,cy=h/2,R=Math.min(w,h)/2-10,scale=R/2;
  /* M 스타일: 1G 강조 링 + 크로스헤어 */
  g.strokeStyle=css('--line');g.lineWidth=1;
  for(const gr of [0.5,1.5]){g.beginPath();g.arc(cx,cy,gr*scale,0,7);g.stroke();}
  g.strokeStyle=css('--dim');g.lineWidth=2.5;
  g.beginPath();g.arc(cx,cy,1*scale,0,7);g.stroke();
  g.lineWidth=1.8;
  g.beginPath();g.arc(cx,cy,2*scale,0,7);g.stroke();
  g.strokeStyle=css('--line');
  g.beginPath();g.moveTo(cx-R,cy);g.lineTo(cx+R,cy);
  g.moveTo(cx,cy-R);g.lineTo(cx,cy+R);g.stroke();
  g.fillStyle=css('--dim');g.font='13px Consolas';
  g.fillText('1G',cx+scale-16,cy-6);g.fillText('2G',cx+2*scale-24,cy-6);
  const now=performance.now(),acc=css('--acc');
  g.lineWidth=3;g.lineCap='round';g.lineJoin='round';g.strokeStyle=acc;
  for(let i=1;i<BUF.length;i++){
    const age=(now-BUF[i].t)/20000;
    g.globalAlpha=Math.max(0,0.85*(1-age));
    g.beginPath();
    g.moveTo(cx+BUF[i-1].lg*scale,cy-BUF[i-1].gg*scale);
    g.lineTo(cx+BUF[i].lg*scale,cy-BUF[i].gg*scale);g.stroke();}
  g.globalAlpha=1;
  {
    g.fillStyle=css('--tx');
    g.beginPath();g.arc(cx+D.latg*scale,cy-D.longg*scale,9,0,7);g.fill();
    /* 중앙 G값 대형 표기 (BMW M 방식) — 프레임당 라이브 스무딩값 */
    const cur=Math.hypot(D.latg,D.longg);
    g.font=`200 ${Math.round(R*0.4)}px ${NF()}`;
    g.textAlign='center';g.fillStyle=css('--tx');
    g.fillText(cur.toFixed(1),cx,cy-R*0.02);
    g.font=`${Math.max(11,Math.round(R*0.11))}px Consolas`;g.fillStyle=css('--dim');
    g.fillText('G · PK '+maxG.toFixed(1),cx,cy+R*0.16);
    g.textAlign='left';
  }
}

function drawMap(){
  const c=cv('map');if(!c)return;const{g,w,h}=c;
  g.clearRect(0,0,w,h);
  const pts=BUF.filter(p=>p.px||p.pz);
  g.fillStyle=css('--dim');g.font='10px Consolas';g.fillText('LINE',10,14);
  if(pts.length<2)return;
  let x0=1e12,x1=-1e12,z0=1e12,z1=-1e12;
  for(const p of pts){x0=Math.min(x0,p.px);x1=Math.max(x1,p.px);
    z0=Math.min(z0,p.pz);z1=Math.max(z1,p.pz);}
  const span=Math.max(x1-x0,z1-z0,10),pad=12;
  const sx=p=>pad+((p.px-x0)/span)*(w-2*pad);
  const sy=p=>h-pad-((p.pz-z0)/span)*(h-2*pad);
  const now=performance.now(),acc=css('--acc');
  g.lineWidth=2;g.lineCap='round';
  for(let i=1;i<pts.length;i++){
    const age=(now-pts[i].t)/20000;
    g.globalAlpha=Math.max(0.05,0.9*(1-age));
    g.strokeStyle=acc;
    g.beginPath();g.moveTo(sx(pts[i-1]),sy(pts[i-1]));
    g.lineTo(sx(pts[i]),sy(pts[i]));g.stroke();}
  g.globalAlpha=1;
  const lp={px:SM.px||0,pz:SM.pz||0};
  g.fillStyle=css('--tx');
  g.beginPath();g.arc(sx(lp),sy(lp),4,0,7);g.fill();
}

function drawTrace(){
  const c=cv('trace');if(!c)return;const{g,w,h}=c;
  g.clearRect(0,0,w,h);
  const now=performance.now(),WIN=10000;
  const x=t=>w-(now-t)/WIN*w;
  /* 핸드브레이크: 아날로그 채움 영역 (보라) */
  g.fillStyle=css('--pur');g.globalAlpha=0.3;
  g.beginPath();let hbStarted=false;
  for(const p of BUF){if(now-p.t>WIN)continue;
    const px=x(p.t),py=h-4-p.hb*(h-8);
    if(!hbStarted){g.moveTo(px,h);g.lineTo(px,py);hbStarted=true;}
    else g.lineTo(px,py);}
  if(hbStarted){g.lineTo(w,h);g.closePath();g.fill();}
  g.globalAlpha=1;
  g.strokeStyle=css('--line');g.beginPath();g.moveTo(0,h/2);g.lineTo(w,h/2);g.stroke();
  const series=[
    ['thr',v=>h-4-v*(h-8),css('--grn'),2],
    ['brk',v=>h-4-v*(h-8),css('--red'),2],
    ['st', v=>h/2-v*(h/2-6),css('--acc'),2.5],
  ];
  for(const [key,fy,color,lw] of series){
    g.strokeStyle=color;g.lineWidth=lw;g.beginPath();let started=false;
    for(const p of BUF){if(now-p.t>WIN)continue;
      const px=x(p.t),py=fy(p[key]);
      if(!started){g.moveTo(px,py);started=true;}else g.lineTo(px,py);}
    g.stroke();}
  g.fillStyle=css('--dim');g.font='10px Consolas';
  g.fillText('THR',10,14);g.fillStyle=css('--grn');g.fillRect(40,7,14,3);
  g.fillStyle=css('--dim');g.fillText('BRK',64,14);g.fillStyle=css('--red');g.fillRect(94,7,14,3);
  g.fillStyle=css('--dim');g.fillText('STEER',118,14);g.fillStyle=css('--acc');g.fillRect(160,7,14,3);
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
                path = self.path.split("?", 1)[0]  # ?th=... 쿼리 허용
                if path == "/state":
                    body = json.dumps(_sanitize(provider())).encode()
                    ctype = "application/json"
                elif path == "/":
                    body = PAGE.encode()
                    ctype = "text/html; charset=utf-8"
                elif path in ("/left", "/right"):
                    body = _side_page(path[1:]).encode()
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
