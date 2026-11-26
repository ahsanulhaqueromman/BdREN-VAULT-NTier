/* VAULT - pages/dashboard.js
   Dashboard page: KPI cards and the SVG charts.
   Loaded by templates/base.html on every screen; all scripts share one global scope (see core/helpers.js). */

/* ---- dashboard: graphs are plain SVG (no library), colours come from the CSS variables so dark mode works ---- */
async function loadDashboard(){
  clearTimeout(dashTimer);
  try{renderDashboard(await api("/api/dashboard"))}catch(e){toast(e.message,{type:"error",title:"Dashboard could not refresh"})}
  dashTimer=setTimeout(()=>{if(!document.hidden)loadDashboard()},30000);
}
$o("#dashRefresh").onclick=loadDashboard;
// Dashboard KPI shortcuts: make key totals useful navigation targets.
$o("#kpis").addEventListener("click",e=>{const card=e.target.closest("[data-go]");if(card)showTab(card.dataset.go)});
const noData=t=>`<div class="nodata">${t}</div>`;
function barChart(days){
  const W=640,H=210,L=30,B=26,T=10,n=days.length,max=Math.max(4,...days.map(d=>d.ok+d.same+d.bad)),bw=(W-L)/n;
  if(!days.some(d=>d.ok+d.same+d.bad))return noData("No backups in the last 14 days");
  let g="";
  for(let i=0;i<=4;i++){const y=T+(H-T-B)*(1-i/4);g+=`<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" class="gl"/><text x="${L-6}" y="${y+4}" class="ax" text-anchor="end">${Math.round(max*i/4)}</text>`}
  days.forEach((d,i)=>{
    const x=L+i*bw+bw*.18,w=bw*.64;let y=H-B;
    [["ok",d.ok],["same",d.same],["bad",d.bad]].forEach(([k,v])=>{if(!v)return;const h=v/max*(H-T-B);y-=h;g+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" class="s-${k}" rx="2"><title>${d.d}: ${v} ${k==="ok"?"saved":k==="same"?"unchanged":"failed"}</title></rect>`});
    if(i%2===0||n<8)g+=`<text x="${x+w/2}" y="${H-8}" class="ax" text-anchor="middle">${d.d.slice(5)}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Backups per day" style="width:100%;height:auto">${g}</svg>`;
}
function donut(st,total){
  if(!total)return noData("No devices yet");
  const parts=[["SUCCESS","Saved","var(--ok)"],["UNCHANGED","Unchanged","var(--info)"],["FAILED","Failed","var(--bad)"],["NONE","Not run","var(--idle)"]];
  const r=52,C=2*Math.PI*r;let off=0,arcs="";
  parts.forEach(([k,,c])=>{const v=st[k];if(!v)return;const len=v/total*C;arcs+=`<circle cx="70" cy="70" r="${r}" fill="none" stroke="${c}" stroke-width="18" stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-off}" transform="rotate(-90 70 70)"/>`;off+=len});
  const done=st.SUCCESS+st.UNCHANGED;
  return `<div class="donut"><svg viewBox="0 0 140 140" width="150" height="150" role="img" aria-label="Backup result per device"><circle cx="70" cy="70" r="${r}" fill="none" stroke="var(--line)" stroke-width="18"/>${arcs}
    <text x="70" y="68" text-anchor="middle" class="dn1">${Math.round(done/total*100)}%</text><text x="70" y="86" text-anchor="middle" class="ax">healthy</text></svg>
    <ul>${parts.map(([k,l,c])=>`<li><i style="background:${c}"></i>${l}<b>${st[k]}</b></li>`).join("")}</ul></div>`;
}
function lineChart(ping){
  if(ping.length<2)return noData("Collecting data. The first points appear after a couple of minutes.");
  const W=640,H=210,L=40,B=26,T=10,n=ping.length,pts=ping.map((p,i)=>[L+i/(n-1)*(W-L-6),T+(H-T-B)*(1-(p.total?p.up/p.total:0))]);
  let g="";
  [0,25,50,75,100].forEach(v=>{const y=T+(H-T-B)*(1-v/100);g+=`<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" class="gl"/><text x="${L-6}" y="${y+4}" class="ax" text-anchor="end">${v}%</text>`});
  const line=pts.map((p,i)=>(i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join(" ");
  g+=`<path d="${line} L${pts[n-1][0]} ${H-B} L${pts[0][0]} ${H-B}Z" class="area"/><path d="${line}" class="ln" pathLength="1"/>`;
  [0,Math.floor(n/2),n-1].forEach(i=>g+=`<text x="${pts[i][0]}" y="${H-8}" class="ax" text-anchor="${i===0?"start":i===n-1?"end":"middle"}">${bdClock(ping[i].ts)}</text>`);
  pts.forEach((p,i)=>g+=`<circle cx="${p[0]}" cy="${p[1]}" r="6" fill="transparent"><title>${bdClock(ping[i].ts)}: ${ping[i].up}/${ping[i].total} online${ping[i].avg_ms!=null?", avg "+ping[i].avg_ms+" ms":""}</title></circle>`);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Devices online over 24 hours" style="width:100%;height:auto">${g}</svg>`;
}
/* one device row: coloured dot, name + IP (and the reason), time on the right; opens the device page */
const devRow=(d,kind,right,why)=>{const label=esc(d.name||d.ip),href=d.id?`/devices/${d.id}`:"/devices";
  return `<li><a href="${href}"><i class="dot ${kind}" aria-hidden="true"></i><span class="nm"><b>${label}</b><span>${d.name?esc(d.ip):""}${why?`${d.name?" · ":""}<em title="${esc(why)}">${esc(why)}</em>`:""}</span></span><span class="when">${right}</span></a></li>`};
const more=(n,shown,href,what)=>n>shown?`<a class="dl-more" href="${href}">+ ${fmtNum(n-shown)} more ${what}</a>`:"";
function attentionHTML(a){
  if(!a)return noData("No data");
  const parts=[];
  if(a.offline.length)parts.push(`<h4><span>Offline now</span><b class="r">${fmtNum(a.offline_count)}</b></h4><ul class="dl">${a.offline.map(d=>devRow(d,"bad",`<span class="tagx bad">Offline</span>`)).join("")}</ul>${more(a.offline_count,a.offline.length,"/devices","offline")}`);
  if(a.failed.length)parts.push(`<h4><span>Last backup failed</span><b class="r">${fmtNum(a.failed_count)}</b></h4><ul class="dl">${a.failed.map(d=>devRow(d,"warn",d.ts?esc(fmtBdDateTime(d.ts)):"",d.message)).join("")}</ul>${more(a.failed_count,a.failed.length,"/devices","failed")}`);
  if(a.retry_count)parts.push(`<p class="dl-note">${fmtNum(a.retry_count)} device${a.retry_count===1?"":"s"} will be retried automatically. <a class="link" href="/jobs">Backup Jobs</a></p>`);
  if(!parts.length)return `<div class="allgood"><i aria-hidden="true"></i><b>All clear</b><span>${a.offline_count==null?"Every last backup succeeded. Online status appears once the ping monitor has run.":"Every device answers ping and every last backup succeeded."}</span></div>`;
  return parts.join("");
}
function changesHTML(rows){
  if(!rows||!rows.length)return noData("No configuration changes saved yet");
  /* name, then IP, then the date on its own line (the card can be narrow) */
  return `<ul class="dl">${rows.map(r=>`<li><a href="${r.id?`/devices/${r.id}`:"/backups"}"><i class="dot ok" aria-hidden="true"></i><span class="nm"><b>${esc(r.name||r.ip)}</b>${r.name?`<span>${esc(r.ip)}</span>`:""}<small>${esc(fmtBdDateTime(r.ts))}</small></span><span></span></a></li>`).join("")}</ul>`;
}
/* Active Sessions (administrators): one row per open session, user initials, device, where from, how long */
function sshHTML(x){
  if(!x.rows.length)return `<div class="ssh-empty"><i aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg></i><b>No one is signed in</b><span>Nobody has a session open on a device right now.</span></div>`;
  const dur=s=>s<60?"just now":s<3600?Math.floor(s/60)+" min":Math.floor(s/3600)+" h "+String(Math.floor(s%3600/60)).padStart(2,"0")+" m";
  const ini=u=>esc((u.match(/[a-z0-9]/gi)||["?"]).slice(0,2).join("").toUpperCase());
  return `<ul class="ssh-list">${x.rows.map(r=>`<li><a href="/radius/commands#session=${encodeURIComponent(r.key)}" title="Open this session in the Session Log: every command ${esc(r.user)} runs">
    <span class="ssh-av" aria-hidden="true">${ini(r.user)}<i></i></span>
    <span class="ssh-who"><b>${esc(r.user)}</b><span>${esc(r.device||r.ip)}${r.device&&r.device!==r.ip?` <em>${esc(r.ip)}</em>`:""}</span>
      ${r.from?`<small>from ${esc(r.from)}</small>`:""}</span>
    <span class="ssh-meta"><strong>${dur(r.for_s)}</strong><small>since ${esc(bdClock(r.since))}</small>${r.changes?`<span class="tagx warn">${fmtNum(r.changes)} change${r.changes===1?"":"s"}</span>`:r.commands?`<span class="tagx">${fmtNum(r.commands)} cmd${r.commands===1?"":"s"}</span>`:""}</span></a></li>`).join("")}</ul>${more(x.count,x.rows.length,"/radius/commands","sessions")}`;
}
function renderSsh(x){
  setHTML("#ssh",sshHTML(x));
  const lv=$("#sshLive");lv.hidden=!x.count;lv.querySelector("span").textContent=fmtNum(x.count)+" live";
  $("#sshSub").textContent=x.count?`${fmtNum(x.users)} user${x.users===1?"":"s"} on ${fmtNum(x.devices)} device${x.devices===1?"":"s"}, right now`:"Who is signed in to a device right now";
}
/* the card asks for itself every 10 s (the rest of the Dashboard every 30 s), so a new login shows quickly */
let sshTimer=0;
function sshPoll(on){
  clearInterval(sshTimer);if(!on)return;
  sshTimer=setInterval(async()=>{
    if(document.hidden||PAGE!=="dashboard")return;
    try{const r=await api("/api/dashboard/ssh");if(r.ssh)renderSsh(r.ssh)}catch(e){}
  },10000);
}
function accessHTML(x){
  const kpi=(label,val,cls,sub)=>`<div class="kpi"><small>${label}</small><strong class="${cls}">${val}</strong><span class="d">${sub}</span></div>`;
  return kpi("Login attempts",fmtNum(x.total),"","Accepted and rejected")
    +kpi("Accepted",fmtNum(x.accepted),"g",x.total?Math.round(x.accepted/x.total*100)+"% of attempts":"No attempts")
    +kpi("Rejected",fmtNum(x.rejected),x.rejected?"r":"g","Wrong password or no access")
    +kpi("Users",fmtNum(x.users),"","Different usernames")
    +(x.device_logging?kpi("Devices",fmtNum(x.devices),"","Signed in to"):"")
    +kpi("Outside allowed devices",fmtNum(x.violations),x.violations?"r":"g",x.violations?"Check Authentication Audit":"None");
}
let wasRunning=null;
function renderDashboard(d){
  if(wasRunning&&!d.job_running&&!manualJob)sfx.play("done");wasRunning=d.job_running;
  const ok=d.status.SUCCESS+d.status.UNCHANGED,last=d.ping[d.ping.length-1];
  const up24=d.ping.length?(d.ping.reduce((a,p)=>a+(p.total?p.up/p.total:0),0)/d.ping.length*100).toFixed(1)+"%":"-";
  const completed=Math.min(d.total, d.status.SUCCESS+d.status.UNCHANGED);
  const failed=d.status.FAILED||0, neverRun=d.status.NONE||0;
  const j=d.last_job,jc=(j&&j.counts)||{};
  const dur=s=>s==null?"":s<60?s+" s":s<3600?Math.round(s/60)+" min":(s/3600).toFixed(1)+" h";
  const lastRun=!j?"Never":!j.finished?"Running now":esc(fmtBdDateTime(j.started));
  const lastRunSub=!j?"No backup has run yet":!j.finished?`${fmtNum(j.done)} of ${fmtNum(j.total)} devices done`
    :`${fmtNum((jc.SUCCESS||0)+(jc.UNCHANGED||0))} ok · ${fmtNum(jc.FAILED||0)} failed${j.duration_s!=null?" · "+dur(j.duration_s):""}`;
  setHTML("#kpis",`<button type="button" class="kpi kpi-link" data-go="devices" aria-label="View all devices"><span class="kpi-top"><small>Total devices</small><span class="kpi-arrow" aria-hidden="true">↗</span></span><strong>${fmtNum(d.total)}</strong><span class="d">All configured devices</span></button>
   <div class="kpi"><small>Online (last check)</small><strong class="g">${last?ofTotal(last.up,last.total):"-"}</strong><span class="d">${last&&last.avg_ms!=null?"Average ping "+last.avg_ms+" ms":"Reachable by ping"}</span></div>
   <div class="kpi"><small>Uptime, 24 h</small><strong>${up24}</strong><span class="d">Average monitored availability</span></div>
   <button type="button" class="kpi kpi-link kpi-link-success" data-go="backups" aria-label="View backups"><span class="kpi-top"><small>Last backup OK</small><span class="kpi-arrow" aria-hidden="true">↗</span></span><strong class="${failed?"":"g"}">${ofTotal(completed,d.total)}</strong><span class="d">${failed||neverRun?`${fmtNum(failed)} failed · ${fmtNum(neverRun)} not run`:"Saved or unchanged"}</span></button>
   <button type="button" class="kpi kpi-link" data-go="jobs" aria-label="View backup jobs"><span class="kpi-top"><small>Last backup run</small><span class="kpi-arrow" aria-hidden="true">↗</span></span><strong class="sm2">${lastRun}</strong><span class="d">${lastRunSub}</span></button>
   <div class="kpi"><small>Auto backup</small><strong class="sm2">${d.job_running?"Running now":d.sched_on?"Next: "+esc(fmtBdDateTime(d.next_run)):"Off"}</strong><span class="d">Scheduled status</span></div>`);
  const att=d.attention;
  setHTML("#attention",attentionHTML(att));
  const st=$("#dashStatus");
  if(st){const issues=att?(att.offline_count||0)+(att.failed_count||0):0;
    const online=last&&last.total?` · ${fmtNum(last.up)} of ${fmtNum(last.total)} online`:"";
    st.className="dash-status "+(!d.total?"idle":issues?"bad":"ok");
    st.textContent=!d.total?"No devices yet":issues?`${fmtNum(issues)} need attention${online}`:`All systems normal${online}`;
    st.hidden=false;}
  if(att)$("#attSub").textContent=att.offline_count==null?"Failed backups now; online status appears once the ping monitor has run":"Offline devices and failed backups, right now";
  $("#sshCard").hidden=!d.ssh;$("#changesCard").hidden=!!d.ssh;
  if(d.ssh)renderSsh(d.ssh);else setHTML("#changes",changesHTML(d.changes));
  sshPoll(!!d.ssh);
  $("#accessCard").hidden=!d.access;
  if(d.access)setHTML("#access",accessHTML(d.access));
  setHTML("#chDays",barChart(d.days));
  setHTML("#chDonut",donut(d.status,d.total));
  setHTML("#chUp",lineChart(d.ping));
  $("#upSub").textContent=d.ping_seconds?`Last 24 hours, checked every ${d.ping_seconds} s in the background`:"Background ping monitor is off";
  const mx=Math.max(1,...d.vendors.map(v=>v[1]));
  setHTML("#chVendor",d.vendors.length?`<div class="hb">`+d.vendors.map(([n,c])=>`<div><span>${esc(n)}</span><div class="bar2"><i class="v-${slug(n)}" style="width:${c/mx*100}%"></i></div><b>${c}</b></div>`).join("")+`</div>`:noData("No devices yet"));
  const h=d.health||{},disk=h.disk||{};
  const fmtBytes=n=>{n=Number(n||0);if(n<1024)return n+" B";const u=["KB","MB","GB","TB"];let i=-1;do{n/=1024;i++}while(n>=1024&&i<u.length-1);return n.toFixed(1)+" "+u[i]};
  const diskLabel=disk.status==="critical"?"Critical":disk.status==="warning"?"Low space":disk.status==="ok"?"Healthy":"Unknown";
  const diskClass=disk.status==="critical"?"r":disk.status==="warning"?"sm2":"g";
  const keep=h.retention_months?h.retention_months+" months":"Forever",sl=h.syslog;
  setHTML("#systemHealth",`<div class="kpi" title="Warning below 15% free; critical below 5% or 2 GB"><small>Disk</small><strong class="${diskClass}">${esc(diskLabel)}${disk.used_percent==null?"":" · "+esc(disk.used_percent)+"% used"}</strong><span class="d">${disk.free_bytes?esc(fmtBytes(disk.free_bytes))+" free of "+esc(fmtBytes(disk.total_bytes)):"Could not read disk capacity"}</span></div>
   <div class="kpi"><small>Database size</small><strong>${h.database_bytes==null?"Unavailable":esc(fmtBytes(h.database_bytes))}</strong><span class="d">${esc(h.database_engine||"Database")}${h.database_name?" · "+esc(h.database_name):""} (data + indexes)</span></div>
   <div class="kpi"><small>Backup storage</small><strong class="${h.backup_dir_exists?"g":"r"}">${h.backup_dir_exists?"Available":"Missing"}</strong><span class="d">Configured backup directory</span></div>
   <div class="kpi"><small>Logs kept for</small><strong>${esc(keep)}</strong><span class="d">${h.retention_months?"Older logs and backups are deleted daily":"Nothing is deleted automatically"}</span></div>
   ${sl?`<div class="kpi"><small>Session Log receiver</small><strong class="${sl.running?"g":"r"}">${sl.running?"Running":sl.seen?"Not running":"Not set up"}</strong><span class="d">${sl.heartbeat?"Last report "+esc(fmtBdDateTime(sl.heartbeat)):"Receives device syslog"}</span></div>`:""}`);
  /* charts animate in on the first draw only; later 30-second refreshes update quietly (see app.css "Motion") */
  if(!renderDashboard.drawn){renderDashboard.drawn=true;setTimeout(()=>$("#dashboard")?.classList.add("charts-ready"),1600)}
}
