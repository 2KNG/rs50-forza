"""웹 대시보드 — 게임 옆 브라우저/폰에서 상태 관찰용.

stdlib http.server 기반 (의존성 없음). / = 대시보드, /state = JSON 폴링(150ms).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RS50 x FH6</title>
<style>
  :root { --bg:#0b0e14; --panel:#141922; --line:#232b38; --tx:#e6edf3;
          --dim:#8b98a9; --grn:#2bd45f; --red:#ff3b3b; --blu:#3b6cff;
          --pur:#b93bff; --amb:#ffb020; }
  * { margin:0; box-sizing:border-box; font-family:'Segoe UI',system-ui,sans-serif; }
  body { background:var(--bg); color:var(--tx); min-height:100vh; padding:18px;
         display:flex; flex-direction:column; gap:14px; }
  .top { display:flex; gap:14px; align-items:stretch; flex-wrap:wrap; }
  .panel { background:var(--panel); border:1px solid var(--line);
           border-radius:14px; padding:16px 20px; }
  .gear { font-size:96px; font-weight:800; line-height:1; min-width:130px;
          text-align:center; font-variant-numeric:tabular-nums; }
  .gear small { display:block; font-size:12px; color:var(--dim); font-weight:600;
                letter-spacing:2px; margin-bottom:2px; }
  .kv { display:flex; flex-direction:column; justify-content:center; gap:8px;
        min-width:150px; }
  .kv .v { font-size:34px; font-weight:700; font-variant-numeric:tabular-nums; }
  .kv .k { font-size:11px; color:var(--dim); letter-spacing:1.5px; }
  .mode { display:flex; align-items:center; justify-content:center; min-width:190px; }
  .badge { font-size:22px; font-weight:800; letter-spacing:2px; padding:12px 22px;
           border-radius:10px; }
  .badge.auto { background:#0d2d18; color:var(--grn); border:1px solid #1d5c33; }
  .badge.manual { background:#332309; color:var(--amb); border:1px solid #6b4d15; }
  .badge.off { background:#22262e; color:var(--dim); border:1px solid var(--line); }
  .strip { display:flex; gap:8px; padding:18px; }
  .led { flex:1; height:46px; border-radius:8px; background:#1a2029;
         border:1px solid var(--line); transition:background .06s, box-shadow .06s; }
  .rpmrow { display:flex; justify-content:space-between; color:var(--dim);
            font-size:13px; padding:0 20px 12px; font-variant-numeric:tabular-nums; }
  .log { flex:1; overflow-y:auto; max-height:300px; font:13px/1.7 Consolas,monospace; }
  .log div { color:var(--dim); border-bottom:1px solid #10141b; padding:2px 4px; }
  .log div b { color:var(--tx); font-weight:600; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%;
         margin-right:7px; background:#444; }
  .dot.on { background:var(--grn); box-shadow:0 0 8px var(--grn); }
  h3 { font-size:12px; color:var(--dim); letter-spacing:2px; margin-bottom:8px; }
</style></head><body>
<div class="top">
  <div class="panel gear"><small>GEAR</small><span id="gear">-</span></div>
  <div class="panel kv"><span class="v" id="speed">0</span><span class="k">KM/H</span></div>
  <div class="panel kv"><span class="v" id="rpm">0</span><span class="k">RPM / <span id="maxrpm">0</span></span></div>
  <div class="panel mode"><span class="badge off" id="mode">대기</span></div>
  <div class="panel kv"><span class="v"><span class="dot" id="teldot"></span></span>
    <span class="k">TELEMETRY</span></div>
</div>
<div class="panel" style="padding:0">
  <div class="strip" id="strip"></div>
  <div class="rpmrow"><span id="ratio">0%</span><span id="ledinfo"></span></div>
</div>
<div class="panel"><h3>EVENTS</h3><div class="log" id="log"></div></div>
<script>
const N=10, COLORS=[...Array(3).fill('var(--grn)'),...Array(4).fill('var(--red)'),
                    ...Array(3).fill('var(--blu)')];
const strip=document.getElementById('strip');
for(let i=0;i<N;i++){const d=document.createElement('div');d.className='led';strip.appendChild(d);}
const leds=[...strip.children];
let lastEvents='';
async function tick(){
  try{
    const s=await (await fetch('/state')).json();
    document.getElementById('gear').textContent = s.gear===0?'R':(s.gear>10?'N':s.gear||'-');
    document.getElementById('speed').textContent = Math.round(s.speed_kmh);
    document.getElementById('rpm').textContent = Math.round(s.rpm);
    document.getElementById('maxrpm').textContent = Math.round(s.max_rpm);
    document.getElementById('ratio').textContent = Math.round(s.ratio*100)+'%';
    const b=document.getElementById('mode');
    if(!s.alive){b.textContent='대기';b.className='badge off';}
    else if(s.mode==='AUTO'){b.textContent='AUTO';b.className='badge auto';}
    else{b.textContent='MANUAL';b.className='badge manual';}
    document.getElementById('teldot').className = 'dot'+(s.alive?' on':'');
    // rev strip 미러링
    const lit = s.ratio<=s.start_ratio?0:
      Math.min(N, Math.max(1, Math.round((s.ratio-s.start_ratio)/(s.blink_ratio-s.start_ratio)*N)));
    const blink = s.alive && s.ratio>=s.blink_ratio && (Date.now()>>6)%2===0;
    leds.forEach((el,i)=>{
      if(blink){el.style.background='var(--pur)';el.style.boxShadow='0 0 14px var(--pur)';}
      else if(s.alive && i<lit){el.style.background=COLORS[i];el.style.boxShadow='0 0 10px '+COLORS[i];}
      else{el.style.background='#1a2029';el.style.boxShadow='none';}
    });
    document.getElementById('ledinfo').textContent =
      s.alive ? (s.ratio>=s.blink_ratio?'SHIFT!':'') : 'idle';
    const ev=s.events.map(e=>`<div><b>${e[0]}</b> ${e[1]}</div>`).reverse().join('');
    if(ev!==lastEvents){document.getElementById('log').innerHTML=ev;lastEvents=ev;}
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
