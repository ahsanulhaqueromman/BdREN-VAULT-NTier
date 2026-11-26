/* VAULT - pages/commands.js
   Session Log (/radius/commands): who logged in to which network device and what they did there, read from
   the devices' syslog (vault-syslog receiver) and the RADIUS logins. Three views of the same sessions, laid out
   like the Change Reports page:
     Sessions   one card per login (the default): user on device, from -> to, changes and commands; opening
                it shows that session's log. A new login after a logout is a new card ("Session 2 of 2").
     By device  one card per device; opening it lists every session on it, newest first: which user, from
                where, login -> every command in order -> logout. #device=<address> opens a card.
     By user    one card per user; opening it lists that user's sessions on every device. #user=<name>
   #session=<user|address|start> opens one session (the Dashboard's Active Sessions card links here).
   Inside a card "Changes only" hides the view-only commands. Searches run on the server; Export CSV
   downloads every matching action (up to 50,000). Refreshes itself every 10 seconds while the page is open. */
let cmdData=null,cmdSess=null,cmdTab="session",cmdDetail={},cmdJump=null,cmdJumped="",cmdOnlyChg=new Set();
const cmdPer=d=>(d&&d.period&&d.period.label)||"";
const CMD_STATUS={active:["Active","UP"],closed:["Logged out","k-logout"],"no-logout":["No logout","k-command"],failed:["Failed login","k-fail"]};
const CMD_VIEW={
  session:{title:"Session log",help:"One card per login, active sessions first, then newest login first: who, on which device, from when to when and what they did. A new login after a logout is a new card. Open a card to see every command.",noun:"session"},
  device:{title:"Sessions by device",help:"One card per device. Open it to see who logged in, every command they ran and when they logged out, session by session.",noun:"device",
          key:s=>s.device_ip,param:"device"},
  user:{title:"Sessions by user",help:"One card per user. Open it to see everything that user did on every device, session by session.",noun:"user",
        key:s=>s.username,param:"user"}};
const CMD_IC={
  user:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>',
  device:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 17h.01M10 17h.01M12 13V8m-4 0h8M9 4h6"/></svg>'};
const cmdHours=()=>periodQuery("#cmdHours");
const cmdSearch=()=>$("#cmdSQ").value.trim();
const cmdFromHash=()=>{const m=/^#(user|device|session)=(.+)$/.exec(location.hash);try{return m?{kind:m[1],key:decodeURIComponent(m[2])}:null}catch(e){return null}};
const cmdDur=s=>{if(s==null)return "-";if(s<60)return `${s} s`;if(s<3600)return `${Math.round(s/60)} min`;const h=Math.floor(s/3600),m=Math.round(s%3600/60);return m?`${h} h ${m} min`:`${h} h`};
const cmdDevice=(name,ip)=>`<span class="dn">${esc(name||ip)}</span>${name?`<span class="sub m">${esc(ip)}</span>`:""}`;
const cmdPlural=(n,w)=>`${fmtNum(n)} ${w}${n===1?"":"s"}`;
const cmdPill=st=>{const [label,cls]=CMD_STATUS[st]||[st,""];return `<span class="pill ${cls}">${esc(label)}</span>`};
const cmdDate=s=>esc(fmtBdDateTime(s).split(", ")[0]);
const cmdId=(kind,key)=>kind+":"+key;
const cmdOpenCards=()=>[...document.querySelectorAll("#cmdSessList details[open]")].map(d=>({kind:d.dataset.kind,key:d.dataset.key}));
/* the sessions of one device or one user, with their commands (same period and search as the list) */
const cmdFetch=(kind,key)=>{
  const sq=cmdSearch();
  /* a session's key is "user|device address|start": fetch that user's sessions on that device */
  const by=kind==="session"?(([u,ip])=>({user:u,device:ip}))(key.split("|")):{[CMD_VIEW[kind].param]:key};
  return api("/api/radius/commands/sessions?"+new URLSearchParams({...cmdHours(),...by,...(sq?{q:sq}:{})}))
    .then(d=>{cmdDetail[cmdId(kind,key)]=d}).catch(e=>{cmdDetail[cmdId(kind,key)]={error:e}});
};

async function loadCommands(){
  /* a #user= / #device= / #session= link opens its card once; the 10-second refresh keeps it open but does not
     scroll back to it */
  const jump=location.hash!==cmdJumped?cmdFromHash():null;
  if(jump){cmdTab=jump.kind;cmdJump=jump;cmdJumped=location.hash}
  const sq=cmdSearch(),hours=cmdHours();
  const want=[...cmdOpenCards().filter(c=>c.kind===cmdTab),...(jump?[jump]:[])];
  try{
    const [act,sess]=await Promise.all([
      api("/api/radius/commands?"+new URLSearchParams(hours)),
      api("/api/radius/commands/sessions?"+new URLSearchParams({...hours,...(sq?{q:sq}:{})})),
      ...want.map(c=>cmdFetch(c.kind,c.key))]);
    cmdData=act;cmdSess=sess;
    const keep=new Set(want.map(c=>cmdId(c.kind,c.key)));
    for(const k of Object.keys(cmdDetail))if(!keep.has(k))delete cmdDetail[k];
    renderCmdStatus();renderCmdKpis();renderCmdSources();renderCmdView();renderCmdSessions();
  }catch(e){
    $("#cmdSessList").innerHTML=errorState("Could not load the session log",e);
    ["#cmdKpis","#cmdSources","#cmdStatus"].forEach(s=>{const el=$(s);if(el)el.innerHTML=""});
    $("#cmdSCount").textContent="";
  }
}
function renderCmdView(){
  const v=CMD_VIEW[cmdTab];
  $("#cmdSessTitle").textContent=v.title;$("#cmdSessHelp").textContent=v.help;
  $("#cmdTabs").querySelectorAll("[data-cmd-tab]").forEach(b=>{const on=b.dataset.cmdTab===cmdTab;b.classList.toggle("on",on);b.setAttribute("aria-selected",on)});
}

/* a warning note: what happened, a "What to do" button that opens the steps, and (when the note can be
   cleared) a Dismiss button under the steps, to click once they are done */
function cmdNote(title,text,steps,dismiss){
  return `<div class="rad-note"><b>${title}</b> ${text}<details class="rad-help"><summary class="b rad-act">What to do</summary>
    <ol>${steps.map(s=>`<li>${s}</li>`).join("")}</ol>
    ${dismiss?`<div class="rad-acts"><button class="b rad-act" type="button" data-cmd-dismiss="${dismiss}">Done, dismiss</button></div>`
             :`<p class="rad-help-end">This note goes away by itself once it is fixed.</p>`}</details></div>`;
}
const CMD_DISMISSED={rejected:"It comes back only if a device that is not on NAS Clients sends again.",
                     dropped:"It comes back only if a device sends too many messages again."};
function renderCmdStatus(){
  const r=cmdData.receiver||{},box=$("#cmdStatus");
  const notes=[],setup=`<a href="${esc(PAGE_URL["radius-setup"]||"/radius/setup")}">Device Setup</a>`;
  if(!r.seen)notes.push(cmdNote("The syslog receiver is not installed yet.","It listens for the devices' logs on UDP 514.",[
    `Run this once on the server:<code>sudo bash /opt/vault/deploy/maintenance/enable_syslog.sh</code>`,
    `Turn on command logging on each device: ${setup}, step "Command logging".`]));
  else if(!r.running)notes.push(cmdNote("The syslog receiver is not running",
    `${r.heartbeat?`(last seen ${esc(fmtWhen(r.heartbeat).replace(/<[^>]+>/g," ").replace(/\s+/g," ").trim())}). `:""}Logs that arrive now are lost.`,[
    `See why it stopped:<code>sudo systemctl status vault-syslog --no-pager</code><code>sudo journalctl -u vault-syslog -n 30 --no-pager</code>`,
    `Start it again:<code>sudo systemctl restart vault-syslog</code>`]));
  else if(!(cmdData.sources||[]).length)notes.push(cmdNote("Waiting for the first device.",`The receiver is listening on UDP ${esc(r.port||514)}, but no device has sent a log yet.`,[
    `Add the device to NAS Clients: only devices on NAS Clients are accepted.`,
    `Turn on command logging on it: ${setup}, step "Command logging".`]));
  if(r.rejected){
    const ip=r.rejected_last_ip,add=ip&&PAGE_URL["radius-nas"]?` <a class="b rad-act" href="${esc(PAGE_URL["radius-nas"]+"?add="+encodeURIComponent(ip))}">Add ${esc(ip)} to NAS Clients</a>`:"";
    notes.push(cmdNote(`${fmtNum(r.rejected)} log message${r.rejected===1?" was":"s were"} ignored`,
      `because the sender is not on NAS Clients${ip?` (last one from <span class="m">${esc(ip)}</span>)`:""}.`,[
      `If ${ip?`<span class="m">${esc(ip)}</span>`:"the sender"} is one of your devices, add that address to NAS Clients (often its loopback or management interface).${add}`,
      `If it is an old address the device no longer sends from, or not your device, nothing has to change.`,
      `Then dismiss this note.`],"rejected"));
  }
  if(r.dropped)notes.push(cmdNote(`${fmtNum(r.dropped)} message${r.dropped===1?" was":"s were"} dropped`,"because a device sent more than 200 per second.",[
    `Lower the log level that device sends to VAULT, for example on Cisco <code>logging trap notifications</code>`,
    `Then dismiss this note.`],"dropped"));
  box.innerHTML=notes.join("");
  box.querySelectorAll("[data-cmd-dismiss]").forEach(b=>b.onclick=async()=>{
    const note=b.dataset.cmdDismiss;b.disabled=true;
    try{await api(`/api/radius/commands/notes/${note}/dismiss`,J("POST",{}));cmdData.receiver[note]=0;renderCmdStatus();toast(CMD_DISMISSED[note],{title:"Note dismissed"})}
    catch(e){b.disabled=false;toast(e.message,{type:"error"})}
  });
}
function renderCmdKpis(){
  const t=cmdSess.totals||{},per=cmdPer(cmdSess);
  const by={};(cmdSess.sessions||[]).forEach(s=>{if(s.changes)by[s.username]=(by[s.username]||0)+s.changes});
  const top=Object.entries(by).sort((a,b)=>b[1]-a[1])[0];
  radKpis("#cmdKpis",[
    ["Sessions",t.sessions||0,t.active?`${fmtNum(t.active)} active now`:`Device logins ${per}`,"g"],
    ["Changes",t.changes||0,top?`Most by ${top[0]} (${fmtNum(top[1])})`:"No configuration changed",t.changes?"warn":""],
    ["Commands",t.commands||0,"Show / display and other view-only commands"],
    ["Users",t.users||0,`On ${fmtNum(t.devices||0)} device${t.devices===1?"":"s"}`]]);
}

/* ---- the list: one card per device (or per user) ---- */
function cmdKeep(s){
  const f=$("#cmdSFilter").value;
  return f==="changes"?s.changes>0:f==="active"?s.status==="active":f==="risky"?s.risky>0:true;
}
function cmdGroups(){
  const by=new Map(),key=CMD_VIEW[cmdTab].key;
  for(const s of (cmdSess.sessions||[]).filter(cmdKeep)){        /* server order: active first, then newest login; a card takes the place of its first session */
    const k=key(s);let g=by.get(k);
    if(!g)by.set(k,g={key:k,name:cmdTab==="device"?(s.device||s.device_ip):s.username,ip:s.device_ip,named:!!s.device,
      sessions:0,failed:0,changes:0,commands:0,active:0,users:new Set(),devices:new Set(),last:s.end||s.last,lastStart:s.start});
    if(s.failed)g.failed++;else g.sessions++;
    g.changes+=s.changes;g.commands+=s.commands;g.risky=(g.risky||0)+(s.risky||0);
    if(s.status==="active")g.active++;
    g.users.add(s.username);g.devices.add(s.device||s.device_ip);
  }
  return [...by.values()];
}
function renderCmdSessions(){
  if(cmdTab==="session")return renderCmdSessionCards();
  const list=cmdGroups(),all=cmdSess.sessions||[],filtered=cmdSearch()||$("#cmdSFilter").value,noun=CMD_VIEW[cmdTab].noun;
  const n=list.reduce((a,g)=>a+g.sessions+g.failed,0);
  $("#cmdSCount").textContent=list.length?`${cmdPlural(list.length,noun)} · ${cmdPlural(n,"session")}`:"";
  if(!list.length){$("#cmdSessList").innerHTML=`<div class="empty"><b>${filtered&&all.length?"No matching sessions":"No sessions "+esc(cmdPer(cmdSess))}</b>${filtered?"Try another user, device, address or command, or a longer period.":"A session appears when a user logs in to a device that sends its logs to VAULT."}</div>`;return}
  const jump=cmdJump&&cmdJump.kind===cmdTab?cmdJump.key:"";
  if(jump){const i=list.findIndex(g=>g.key===jump);if(i>=0)PAGES.cmdSess=Math.floor(i/SIZES.cmdSess)+1}
  const open=new Set([...cmdOpenCards().filter(c=>c.kind===cmdTab).map(c=>c.key),...(jump?[jump]:[])]);
  const {rows,bar}=paginate("cmdSess",list);
  morph($("#cmdSessList"),rows.map(g=>cmdCard(g,open.has(g.key))).join("")+bar);
  cmdJump=null;
  if(jump){
    const el=[...document.querySelectorAll("#cmdSessList details")].find(d=>d.dataset.key===jump);
    if(el){el.open=true;cmdScrollTo(el)}
  }
}
function cmdCard(g,isOpen){
  const work=g.changes+g.commands,chgPct=work?Math.round(g.changes/work*100):0;
  const badges=(g.sessions?`<span class="rep-badge ${g.changes?"chg":"same"}">${cmdPlural(g.sessions,"session")}</span>`:"")+
    (g.failed?`<span class="rep-badge fail">${cmdPlural(g.failed,"failed login")}</span>`:"")+
    (g.active?'<span class="rep-badge is-live">Active now</span>':"")+
    (g.risky?`<span class="rep-badge fail" title="Reload, erase, delete, format ... commands">${cmdPlural(g.risky,"risky command")}</span>`:"");
  const users=[...g.users],devs=[...g.devices];
  const names=a=>esc(a.slice(0,2).join(", "))+(a.length>2?` +${a.length-2} more`:"");
  const sub=cmdTab==="device"?`${g.named?`<span class="m">${esc(g.ip)}</span> · `:""}<span class="cmd-who-ic">${CMD_IC.user}</span>${names(users)}`:
    `<span class="cmd-who-ic">${CMD_IC.device}</span>${names(devs)}`;
  const title=cmdTab==="device"?users.join(", "):devs.join(", ");
  const last=g.lastStart?["Last login",g.lastStart]:["Last activity",g.last];
  return `<details class="rep-card cmd-card${g.changes?" has-chg":""}${g.active?" is-live":""}" data-kind="${cmdTab}" data-key="${esc(g.key)}"${isOpen?" open":""}>
    <summary>
      <span class="rep-dev"><b>${esc(g.name)}</b><small title="${esc(title)}">${sub}</small></span>
      <span class="cmd-badges">${badges}</span>
      <span class="rep-bar" title="${cmdPlural(g.changes,"change")} / ${cmdPlural(g.commands,"view command")}"><i class="chg" style="width:${chgPct}%"></i><i class="cmdv" style="width:${work?100-chgPct:0}%"></i></span>
      <span class="rep-lines"><span class="cmd-c">${cmdPlural(g.changes,"change")}</span><span class="cmd-v">${fmtNum(g.commands)} view</span></span>
      <span class="rep-last">${last[0]}<br> <b>${cmdDate(last[1])}</b> <span class="t">${esc(bdClock(last[1]))}</span></span>
      <svg class="rep-chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
    </summary>
    <div class="rep-body">${isOpen?cmdBody(cmdTab,g.key):""}</div></details>`;
}

/* ---- Sessions view: one card per login (user on a device, login -> logout) ---- */
function renderCmdSessionCards(){
  const all=cmdNumber(cmdSess.sessions||[]),list=all.filter(cmdKeep),filtered=cmdSearch()||$("#cmdSFilter").value;
  $("#cmdSCount").textContent=list.length?cmdPlural(list.length,"session"):"";
  if(!list.length){$("#cmdSessList").innerHTML=`<div class="empty"><b>${filtered&&all.length?"No matching sessions":"No sessions "+esc(cmdPer(cmdSess))}</b>${filtered?"Try another user, device, address or command, or a longer period.":"A session appears when a user logs in to a device that sends its logs to VAULT."}</div>`;return}
  /* #session=<key> (from the Dashboard): open that session; if its key moved (the login was not seen, so the
     key follows the newest action), open the same user's active session on that device instead */
  let jump=cmdJump&&cmdJump.kind==="session"?cmdJump.key:"";
  if(jump&&!list.some(s=>s.key===jump)){const [u,ip]=jump.split("|"),alt=list.find(s=>s.username===u&&s.device_ip===ip);
    if(alt){cmdDetail[cmdId("session",alt.key)]=cmdDetail[cmdId("session",jump)];jump=alt.key}}
  if(jump){const i=list.findIndex(s=>s.key===jump);if(i>=0)PAGES.cmdSess=Math.floor(i/SIZES.cmdSess)+1}
  const open=new Set([...cmdOpenCards().filter(c=>c.kind==="session").map(c=>c.key),...(jump?[jump]:[])]);
  const {rows,bar}=paginate("cmdSess",list);
  morph($("#cmdSessList"),rows.map(s=>cmdSessCard(s,open.has(s.key))).join("")+bar);
  cmdJump=null;
  if(jump){
    const el=[...document.querySelectorAll("#cmdSessList details")].find(d=>d.dataset.key===jump);
    if(el){el.open=true;cmdScrollTo(el)}
  }
}
function cmdSessCard(s,isOpen){
  const work=s.changes+s.commands,chgPct=work?Math.round(s.changes/work*100):0;
  const at=s.start||s.end||s.last,until=s.failed?"":s.status==="active"?"now":s.end?bdClock(s.end):"no logout";
  return `<details class="rep-card cmd-card cmd-scard st-${esc(s.status)}${s.changes?" has-chg":""}${s.status==="active"?" is-live":""}" data-kind="session" data-key="${esc(s.key)}"${isOpen?" open":""}>
    <summary>
      <span class="cmd-sid"><span class="cmd-av-s">${esc(s.username.slice(0,1).toUpperCase())}</span>
        <span class="rep-dev"><b>${esc(s.username)} <span class="cmd-on">on</span> ${esc(s.device||s.device_ip)}</b>
        <small>${s.device?`<span class="m">${esc(s.device_ip)}</span>`:""}${s.source_ip?`${s.device?" · ":""}from <span class="m">${esc(s.source_ip)}</span>`:""}</small></span></span>
      <span class="cmd-badges">${cmdPill(s.status)}${s.risky?`<span class="rep-badge fail" title="Reload, erase, delete, format ... commands">${cmdPlural(s.risky,"risky command")}</span>`:""}${s.of>1&&!s.failed?`<span class="cmd-no">Session ${s.no} of ${s.of}</span>`:""}</span>
      <span class="rep-bar" title="${cmdPlural(s.changes,"change")} / ${cmdPlural(s.commands,"view command")}"><i class="chg" style="width:${chgPct}%"></i><i class="cmdv" style="width:${work?100-chgPct:0}%"></i></span>
      <span class="rep-lines">${s.failed?'<span class="bad-t">Login refused</span>':`<span class="cmd-c">${cmdPlural(s.changes,"change")}</span><span class="cmd-v">${fmtNum(s.commands)} view</span>`}</span>
      <span class="rep-last cmd-when"><b>${s.start?esc(bdClock(s.start)):"Before period"}${until?` → ${esc(until)}`:""}</b><br><span>${cmdDate(at)}${s.failed?"":" · "+cmdDur(s.duration)}</span></span>
      <svg class="rep-chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
    </summary>
    <div class="rep-body">${isOpen?cmdBody("session",s.key):""}</div></details>`;
}
/* inside a session card: the log of that one session */
function cmdSessBody(key){
  const d=cmdDetail[cmdId("session",key)];
  const s=(d.sessions||[]).find(x=>x.key===key);
  if(!s)return `<p class="rep-note" style="padding:12px 0">This session is no longer in the chosen period. Refresh the page.</p>`;
  const only=cmdOnlyChg.has(cmdId("session",key));
  return `<div class="rep-head"><span>What ${esc(s.username)} did on ${esc(s.device||s.device_ip)}</span>
      <span class="cmd-head-r"><span class="cmd-sum"><b class="cmd-c">${cmdPlural(s.changes,"change")}</b> · ${cmdPlural(s.commands,"view command")}</span>
      ${s.changes&&s.commands?`<button type="button" class="b cmd-only${only?" on":""}" data-only aria-pressed="${only}">Changes only</button>`:""}</span></div>
    <div class="cmd-tl cmd-one${only?" only-chg":""}"><pre class="rep-prev cmd-log">${cmdLog(s)}</pre>
      <p class="cmd-links"><button type="button" class="cmd-user" data-go="user" data-key="${esc(s.username)}">All sessions of ${esc(s.username)} →</button>
        <button type="button" class="cmd-user" data-go="device" data-key="${esc(s.device_ip)}">Everyone on ${esc(s.device||s.device_ip)} →</button></p></div>`;
}

/* ---- inside a card: each session as login -> commands -> logout ---- */
function cmdBody(kind,key){
  const d=cmdDetail[cmdId(kind,key)];
  if(!d)return `<div class="loading-block" role="status"><span class="spin"></span>Loading sessions…</div>`;
  if(d.error)return errorState("Could not load these sessions",d.error);
  if(kind==="session")return cmdSessBody(key);
  const list=(d.sessions||[]).filter(cmdKeep);
  if(!list.length)return `<p class="rep-note" style="padding:12px 0">No sessions ${esc(cmdPer(d))}.</p>`;
  const chg=list.reduce((n,s)=>n+s.changes,0),only=cmdOnlyChg.has(cmdId(kind,key));
  /* who did what here (by device) / where they did it (by user): one chip per person or device */
  const other=kind==="device"?"user":"device",by=new Map();
  for(const s of list){
    const k=kind==="device"?s.username:s.device_ip;let w=by.get(k);
    if(!w)by.set(k,w={key:k,name:kind==="device"?s.username:(s.device||s.device_ip),sessions:0,changes:0,failed:0});
    s.failed?w.failed++:w.sessions++;w.changes+=s.changes;
  }
  const who=[...by.values()].sort((a,b)=>b.changes-a.changes||b.sessions-a.sessions).map(w=>
    `<button type="button" class="cmd-chip${w.changes?" has-chg":""}" data-go="${other}" data-key="${esc(w.key)}" title="Open ${esc(w.name)}">
      <span class="cmd-av-s${other==="device"?" dev":""}">${other==="device"?CMD_IC.device:esc(w.name.slice(0,1).toUpperCase())}</span>
      <span><b>${esc(w.name)}</b><small>${w.changes?`<span class="cmd-c">${cmdPlural(w.changes,"change")}</span> · `:"No changes · "}${w.sessions?cmdPlural(w.sessions,"session"):""}${w.failed?`${w.sessions?" · ":""}<span class="bad-t">${cmdPlural(w.failed,"failed login")}</span>`:""}</small></span></button>`).join("");
  return `<div class="cmd-who"><span class="cmd-who-t">${kind==="device"?"Who logged in":"Devices used"}</span>${who}</div>
    <div class="rep-head"><span>Sessions: active first, then newest login first</span>
      <span class="cmd-head-r"><span class="cmd-sum">${cmdPlural(list.length,"session")} · <b class="cmd-c">${cmdPlural(chg,"change")}</b></span>
      <button type="button" class="b cmd-only${only?" on":""}" data-only aria-pressed="${only}">Changes only</button></span></div>
    <ol class="rep-tl cmd-tl${only?" only-chg":""}">${cmdNumber(list).map(s=>cmdSessionItem(s,kind)).join("")}</ol>`;
}
/* each visit of one user to one device is its own session: number them in time order (1 = earliest) */
function cmdNumber(list){
  const seen={},total={};
  for(const s of list)total[s.username+"|"+s.device_ip]=(total[s.username+"|"+s.device_ip]||0)+1;
  for(const s of [...list].reverse()){const k=s.username+"|"+s.device_ip;seen[k]=(seen[k]||0)+1;s.no=seen[k];s.of=total[k]}
  return list;
}
/* one session's log: logged in -> every command in order -> logged out */
/* a configuration change that takes something away: undo (Huawei), no (Cisco), delete / deactivate (Juniper),
   unset (FortiGate), remove (MikroTik). Shown as "- remove" in red; every other change as "+ add" in green. */
const CMD_REMOVE=/^(undo|no|delete|deactivate|unset|purge)\b|(^\/|\s)remove\b/i;
/* commands that apply or store the configuration rather than add a line to it: commit (Huawei VRP 8, Juniper,
   XR), save (Huawei), write / copy running-config startup-config (Cisco), execute cfg save (FortiGate) */
const CMD_COMMIT=/^commit\b/i, CMD_SAVE=/^(?:save\b|wr(?:ite)?(?:\s+(?:mem(?:ory)?|startup-config))?$|copy\s+run\S*\s+start\S*|execute\s+cfg\s+save\b)/i;
const cmdMark=e=>{if(e.kind!=="change")return ["cmd","view"];const c=(e.command||"").trim().replace(/^do\s+/i,"");
  if(/^configuration finished\b/i.test(c))return ["chg save","✓ done"];   // Cisco: left configuration mode
  return CMD_COMMIT.test(c)?["chg save","✓ commit"]:CMD_SAVE.test(c)?["chg save","✓ save"]:CMD_REMOVE.test(c)?["chg del","− remove"]:["chg add","+ add"]};
function cmdLog(s){
  const line=(t,cls,text)=>`<span class="l ${cls}"><time>${t?esc(bdClock(t,true)):""}</time><span>${text}</span></span>`;
  let log;
  if(s.failed)log=line(s.start,"fail",`✕ Login refused${s.source_ip?" from "+esc(s.source_ip):""}`);
  else{
    const steps=s.events.filter(e=>e.kind==="change"||e.kind==="command").map(e=>{
      const bad=e.result&&!/^succ/i.test(e.result);
      const [cls0,tag0]=cmdMark(e),risk=e.risky,cls=risk?"risk":cls0,tag=risk?"⚠ risky":tag0;
      return line(e.ts,cls,`<i>${tag}</i>${esc(e.command)}${bad?` <em>(${esc(e.result)})</em>`:""}`)}).join("");
    log=(s.start?line(s.start,"in",`▶ Logged in${s.source_ip?" from "+esc(s.source_ip):""}`):line(null,"in","▶ Logged in before this period"))+
      (steps||`<span class="l none"><time></time><span>No commands in this session</span></span>`)+
      (s.status==="closed"?line(s.end,"out",`◀ Logged out · ${cmdDur(s.duration)} on the device`):
       s.status==="active"?line(null,"now","● Still logged in"):line(s.last,"out","◀ No logout recorded (last activity)"));
  }
  return log;
}
function cmdSessionItem(s,kind){
  const at=s.start||s.events[0]?.ts||s.end||s.last;
  const until=s.failed?"":s.status==="active"?"now":s.end?bdClock(s.end):"no logout";
  const log=cmdLog(s);
  /* by device: the session is about a user; by user: about a device. Each name opens the other view. */
  const who=kind==="device"?`<span class="cmd-av-s">${esc(s.username.slice(0,1).toUpperCase())}</span><button type="button" class="cmd-user" data-go="user" data-key="${esc(s.username)}" title="Everything ${esc(s.username)} did">${esc(s.username)}</button>`:
    `<span class="cmd-av-s dev">${CMD_IC.device}</span><button type="button" class="cmd-user" data-go="device" data-key="${esc(s.device_ip)}" title="Everyone on this device">${esc(s.device||s.device_ip)}</button>${s.device?` <span class="m">${esc(s.device_ip)}</span>`:""}`;
  return `<li class="st-${esc(s.status)}${s.changes?" has-chg":""}">
    <div class="rep-when"><b>${cmdDate(at)}</b><span class="cmd-range">${s.start?esc(bdClock(s.start)):"Before this period"}${until?` <i aria-hidden="true">→</i> ${esc(until)}`:""}</span>
      ${s.of>1&&!s.failed?`<span class="cmd-no">Session ${s.no} of ${s.of}</span>`:""}</div>
    <div class="rep-what">
      <p class="cmd-sline">${who}
        ${s.source_ip&&kind==="device"?`<span>from <span class="m">${esc(s.source_ip)}</span></span>`:""}
        ${s.failed?"":`<span>${cmdDur(s.duration)}</span>`}
        ${s.changes?`<span class="cmd-c">${cmdPlural(s.changes,"change")}</span>`:""}${s.commands?`<span>${cmdPlural(s.commands,"view command")}</span>`:""}</p>
      <pre class="rep-prev cmd-log">${log}</pre></div>
    <div class="rep-act">${cmdPill(s.status)}</div></li>`;
}
/* opening a card loads its sessions */
$o("#cmdSessList").addEventListener("toggle",e=>{
  const d=e.target;if(!d.matches||!d.matches("details[data-kind]")||!d.open)return;
  const {kind,key}=d.dataset,body=d.querySelector(".rep-body");
  body.innerHTML=cmdBody(kind,key);
  if(!cmdDetail[cmdId(kind,key)])cmdFetch(kind,key).then(()=>{if(d.open)body.innerHTML=cmdBody(kind,key)});
},true);
$o("#cmdSessList").addEventListener("click",e=>{
  const only=e.target.closest("[data-only]");
  if(only){
    const d=only.closest("details"),id=cmdId(d.dataset.kind,d.dataset.key),on=!cmdOnlyChg.has(id);
    on?cmdOnlyChg.add(id):cmdOnlyChg.delete(id);
    only.classList.toggle("on",on);only.setAttribute("aria-pressed",on);d.querySelector(".cmd-tl")?.classList.toggle("only-chg",on);
    return;
  }
  const go=e.target.closest("[data-go]");
  if(go){e.preventDefault();cmdOpen(go.dataset.go,go.dataset.key)}
});
/* bring an opened card to the top of the screen once the page around it has settled */
function cmdScrollTo(el){requestAnimationFrame(()=>setTimeout(()=>{
  el.scrollIntoView({behavior:"smooth",block:"start"});
  setTimeout(()=>{if(Math.abs(el.getBoundingClientRect().top)>40)el.scrollIntoView({behavior:"instant",block:"start"})},900);   /* smooth scroll was interrupted */
},250))}
function cmdOpen(kind,key){
  history.pushState(null,"",`#${kind}=${encodeURIComponent(key)}`);
  PAGES.cmdSess=1;loadCommands();
}
addEventListener("popstate",()=>{if(PAGE==="radius-commands")loadCommands()});

/* ---- devices that send logs ---- */
function renderCmdSources(){
  const list=cmdData.sources||[],box=$("#cmdSources");
  if(!list.length){box.innerHTML=`<div class="empty"><b>No device has sent logs yet</b>Devices appear here with their first message.</div>`;return}
  const {rows,bar}=paginate("cmdSources",list);
  box.innerHTML=`<div class="tbl"><table><thead><tr><th>Device</th><th>Last message</th><th>Messages</th><th>User actions</th><th>Status</th></tr></thead><tbody>`+
    rows.map(s=>`<tr><td>${cmdDevice(s.device,s.ip)}</td>
      <td class="when">${fmtWhen(s.last_seen)}</td><td>${fmtNum(s.received)}</td><td>${fmtNum(s.recognized)}</td>
      <td>${s.recognized?'<span class="pill UP">Running</span>':`<span class="pill k-change">No user actions yet</span>`}
        ${!s.recognized&&s.sample?`<details class="cmd-sample"><summary>Last message received</summary><code>${esc(s.sample)}</code></details>`:""}</td></tr>`).join("")+`</tbody></table></div>`+bar;
}

PAGES.cmdSources=PAGES.cmdSess=1;
for(const k of ["cmdSources","cmdSess"]){const v=+localStorage.getItem("dbms_page_size_"+k);SIZES[k]=PAGE_SIZES.includes(v)?v:10}
REDRAW.cmdSources=renderCmdSources;REDRAW.cmdSess=renderCmdSessions;
let cmdT=0;
$o("#cmdSQ").addEventListener("input",()=>{clearTimeout(cmdT);cmdT=setTimeout(()=>{PAGES.cmdSess=1;loadCommands()},350)});
$o("#cmdSFilter").addEventListener("change",()=>{PAGES.cmdSess=1;renderCmdSessions()});
periodPicker("#cmdHours",()=>{PAGES.cmdSess=1;loadCommands()});
$o("#cmdRefresh").addEventListener("click",()=>loadCommands());
$o("#cmdTabs").addEventListener("click",e=>{
  const b=e.target.closest("[data-cmd-tab]");if(!b||b.dataset.cmdTab===cmdTab)return;
  cmdTab=b.dataset.cmdTab;PAGES.cmdSess=1;
  if(location.hash)history.pushState(null,"",location.pathname+location.search);
  renderCmdView();renderCmdSessions();
});
$o("#cmdCsv").addEventListener("click",()=>{
  const p=new URLSearchParams({...cmdHours(),format:"csv"}),q=cmdSearch();if(q)p.set("q",q);
  location.href="/api/radius/commands?"+p;
});

/* ---- Export PDF: a clean, print-quality session report in a new window, saved with the browser's "Save
   as PDF" - the same no-library, no-server-change approach as Change Reports (pages/reports.js). Follows
   the current period, search and "With changes / Active now" filter: every matching session in one table,
   then the full login -> command -> logout log of every session that did something. ---- */
let cmdPdfHtml="";     /* the last generated PDF document (kept for checking the layout) */
$o("#cmdPdf").onclick=async()=>{
  const btn=$("#cmdPdf");if(btn.disabled)return;btn.disabled=true;
  try{
    const p=new URLSearchParams({...cmdHours(),export:"1"}),q=cmdSearch();if(q)p.set("q",q);
    const data=await api("/api/radius/commands/sessions?"+p);
    const list=cmdNumber((data.sessions||[]).slice()).filter(cmdKeep);
    if(!list.length)return toast("No sessions match the current period, search or filter.",{type:"warning",title:"Nothing to export"});
    const t=data.totals||{},per=cmdPer(data);
    const who=(typeof ME!=="undefined"&&ME&&(ME.username||ME.name))||"";
    const now=new Date(),stamp=now.toLocaleString("en-GB",{timeZone:"Asia/Dhaka",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"});
    const n=v=>Number(v||0).toLocaleString("en-US");
    const day=v=>v?esc(fmtBdDateTime(v).split(", ")[0]):"";
    const rows=list.map((s,i)=>`<tr><td>${i+1}</td><td><b>${esc(s.username)}</b></td><td>${esc(s.device||s.device_ip)}<br><span class="m">${esc(s.device_ip)}</span></td>
      <td>${s.start?`${day(s.start)}<br>${esc(bdClock(s.start))}`:"Before period"}</td>
      <td>${s.failed?"-":s.status==="active"?"Still logged in":s.end?`${day(s.end)}<br>${esc(bdClock(s.end))}`:"No logout"}</td>
      <td class="c">${s.failed?"-":esc(cmdDur(s.duration))}</td>
      <td class="c">${s.failed?'<span class="fail">Login refused</span>':`<span class="${s.status}">${esc((CMD_STATUS[s.status]||[s.status])[0])}</span>`}</td>
      <td class="c">${s.changes?`<span class="add">${s.changes}</span>`:'<span class="none">0</span>'}</td><td class="c">${fmtNum(s.commands)}</td></tr>`).join("");
    const mark=e=>{if(e.kind==="login")return ["in","▶ Logged in"+(e.source_ip?" from "+esc(e.source_ip):"")];
      if(e.kind==="logout")return ["out","◀ Logged out"];
      if(e.kind!=="change")return ["cmd",`<span class="tag view">view</span>${esc(e.command)}`];
      const [cls,tag]=cmdMark(e);return [cls.includes("del")?"del":cls.includes("save")?"save":"add",`<span class="tag ${cls.includes("del")?"del":cls.includes("save")?"save":"add"}">${tag.replace(/^[+−✓]\s*/,"")}</span>${esc(e.command)}`];
    };
    const details=list.filter(s=>s.failed||s.changes||s.commands).map(s=>{
      const lines=s.failed?[['fail',`✕ Login refused${s.source_ip?" from "+esc(s.source_ip):""}`]]:
        [...(s.start?[['in',`▶ Logged in${s.source_ip?" from "+esc(s.source_ip):""}`]]:[['in','▶ Logged in before this period']]),
         ...s.events.filter(e=>e.kind==="change"||e.kind==="command").map(e=>{const [cls,html]=mark(e);return [cls,html]}),
         s.status==="closed"?['out',`◀ Logged out · ${esc(cmdDur(s.duration))} on the device`]:
         s.status==="active"?['now','● Still logged in']:['out','◀ No logout recorded (last activity)']];
      return `<section class="sess"><h3>${esc(s.username)} <small>on ${esc(s.device||s.device_ip)} (${esc(s.device_ip)})</small></h3>
        <p class="meta">${s.start?`${day(s.start)} ${esc(bdClock(s.start))}`:"Before period"} → ${s.failed?"refused":s.status==="active"?"now":s.end?`${day(s.end)} ${esc(bdClock(s.end))}`:"no logout"}${!s.failed&&s.duration!=null?` · ${esc(cmdDur(s.duration))}`:""} · <span class="add">${s.changes} change${s.changes===1?"":"s"}</span> · ${fmtNum(s.commands)} view command${s.commands===1?"":"s"}</p>
        <div class="log">${lines.map(([cls,html])=>`<div class="ln ${cls}">${html}</div>`).join("")}</div></section>`;
    }).join("");
    const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Session Log Report</title><style>
      @page{size:A4;margin:16mm 14mm 18mm}
      @page{@bottom-right{content:"Page " counter(page) " of " counter(pages);font:9px Arial,sans-serif;color:#64748b}@bottom-left{content:"VAULT - Session Log Report";font:9px Arial,sans-serif;color:#64748b}}
      *{box-sizing:border-box}body{margin:0;font:11px/1.45 "Segoe UI",Arial,sans-serif;color:#0f1b2d;-webkit-print-color-adjust:exact;print-color-adjust:exact}
      .bar{height:6px;background:linear-gradient(90deg,#2f5bea,#0ea5c6);border-radius:3px;margin-bottom:14px}
      header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;padding-bottom:10px;border-bottom:1px solid #d8e0ec;margin-bottom:14px}
      h1{margin:0;font-size:20px;letter-spacing:-.02em}header p{margin:3px 0 0;color:#5b6b82}
      .ids{text-align:right;color:#5b6b82;font-size:10px;line-height:1.6}.ids b{color:#0f1b2d}
      .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
      .kpi{border:1px solid #d8e0ec;border-top:3px solid #2f5bea;border-radius:6px;padding:7px 9px}.kpi small{display:block;color:#5b6b82;font-size:9.5px}.kpi b{font-size:16px}
      .kpi:nth-child(2){border-top-color:#8a5600}.kpi:nth-child(3){border-top-color:#0ea5c6}.kpi:nth-child(4){border-top-color:#0e9566}
      h2{font-size:13px;margin:18px 0 8px;padding-bottom:4px;border-bottom:2px solid #2f5bea;color:#1e3a8a}
      table{width:100%;border-collapse:collapse;font-size:10px}th{background:#eef2f9;color:#334155;text-align:left;font-weight:700;padding:6px 7px;border-bottom:1px solid #cfd8e6}
      td{padding:5px 7px;border-bottom:1px solid #e6ebf3;vertical-align:top}tr{break-inside:avoid}tbody tr:nth-child(even) td{background:#f8fafc}
      .m{font-family:Consolas,monospace;color:#5b6b82;font-size:9px}.c{text-align:center}
      .add{color:#0e9566;font-weight:700}.del{color:#d63447;font-weight:700}.none{color:#94a3b8}.fail{color:#d63447;font-weight:700}
      .active{color:#0e9566;font-weight:700}.closed{color:#5b6b82}.no-logout{color:#8a5600;font-weight:700}
      .sess{break-inside:avoid-page;margin:0 0 12px;padding:9px 11px;border:1px solid #d8e0ec;border-left:4px solid #2f5bea;border-radius:6px}
      .sess h3{margin:0;font-size:12.5px}.sess h3 small{font-weight:400;color:#5b6b82}.meta{margin:2px 0 6px;color:#5b6b82;font-size:10px}
      .log{padding:6px 8px;background:#0b1222;border-radius:4px;font:9.5px/1.8 Consolas,monospace;color:#d4deec}
      .ln{display:flex;gap:8px}.tag{display:inline-block;min-width:38px;text-align:center;border-radius:3px;padding:0 4px;margin-right:4px;font-size:8.5px;font-weight:700}
      .tag.view{background:#1e293b;color:#93a3bd}.tag.add{background:#0e3426;color:#7be0a8}.tag.del{background:#3b1820;color:#ff9aa2}.tag.save{background:#0e2a52;color:#9cc0ff}
      .ln.in,.ln.now{color:#7be0a8}.ln.out{color:#93a3bd}.ln.fail{color:#ff9aa2}
      .note{margin-top:16px;padding:8px 10px;border-radius:6px;background:#f1f5fb;color:#475569;font-size:9.5px}
      @media screen{body{max-width:900px;margin:24px auto;padding:0 20px}.tip{position:sticky;top:0;margin:-24px -20px 16px;padding:10px 20px;background:#0f1a30;color:#e7eefc;font-size:12px}}
      @media print{.tip{display:none}}
    </style></head><body>
    <div class="tip">To save as PDF: in the print window choose <b>Destination: Save as PDF</b>, then Save.</div>
    <div class="bar"></div>
    <header><div><h1>Session Log Report</h1><p>VAULT · ${esc(per)}</p></div>
      <div class="ids">Generated <b>${esc(stamp)}</b> (Bangladesh time)${who?`<br>By <b>${esc(who)}</b>`:""}<br>Sessions in report <b>${n(list.length)}</b>${q?`<br>Search “${esc(q)}”`:""}</div></header>
    <div class="kpis"><div class="kpi"><small>Sessions</small><b>${n(t.sessions)}</b></div><div class="kpi"><small>Changes</small><b class="add">${n(t.changes)}</b></div>
      <div class="kpi"><small>Commands</small><b>${n(t.commands)}</b></div><div class="kpi"><small>Users</small><b>${n(t.users)}</b></div></div>
    <h2>Summary</h2>
    <table><thead><tr><th>#</th><th>User</th><th>Device</th><th>Login</th><th>Logout</th><th class="c">Duration</th><th class="c">Status</th><th class="c">Changes</th><th class="c">Commands</th></tr></thead><tbody>${rows}</tbody></table>
    ${details?`<h2>Session details</h2>${details}`:""}
    <p class="note">One card per login (a new login after a logout is a new session). Read from the devices' own syslog and RADIUS logins/accounting; a device without command logging turned on shows logins only. Period, search and filter follow what was chosen on the Session Log page.</p>
    </body></html>`;
    cmdPdfHtml=html;
    document.getElementById("cmdPdfFrame")?.remove();
    const f=document.createElement("iframe");
    f.id="cmdPdfFrame";f.title="Session log report for printing";f.setAttribute("aria-hidden","true");
    f.style.cssText="position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
    document.body.append(f);
    const d=f.contentWindow.document;d.open();d.write(html);d.close();
    toast("Choose “Save as PDF” as the destination in the print window.",{type:"info",title:"Preparing the PDF"});
    setTimeout(()=>{try{f.contentWindow.focus();f.contentWindow.print()}catch(e){toast("The print window could not open. Use Ctrl+P on the report instead.",{type:"error",title:"PDF export failed"})}},350);
  }catch(e){toast(e.message,{type:"error",title:"Could not build the report"})}
  finally{btn.disabled=false}
};

/* the 10s refresh can reorder or resize an open card's session list (a session's status/position can change
   between refreshes) - keep the page where the user left it instead of letting that silently scroll them */
if(PAGE==="radius-commands")setInterval(()=>{
  if(document.hidden||!cmdData)return;
  const y=window.scrollY;
  loadCommands().then(()=>{if(Math.abs(window.scrollY-y)>1)window.scrollTo(0,y)});
},10000);
