/* VAULT - core/start.js
   Runs last, when every other script is loaded: fills the open screen with data, follows a running backup,
   and starts the idle sign-out timer.

   PAGE_INIT maps each screen (body[data-page], set by the server from core/pages.py) to the function
   that loads its data. Adding a screen = one line here. */

const PAGE_INIT={
  dashboard:loadDashboard,
  devices:loadDevices,
  device:()=>loadDevicePage(Number(document.body.dataset.deviceId)),
  backups:loadBackups,
  reports:loadReport,
  jobs:loadJobs,
  logs:loadLogs,
  users:loadUsers,
  settings:loadSettings,
  "radius-users":loadRadUsers,
  "radius-nas":loadRadNas,
  "radius-audit":loadRadAudit,
  "radius-commands":loadCommands,
  "radius-setup":loadRadSetup,
};
/* load (or reload, from a "Try again" button) the data of the open screen */
function initPage(){const f=PAGE_INIT[PAGE];if(f)Promise.resolve().then(f).catch(e=>console.error(e))}

/* Links saved from the older one-page version (/#devices, /#device/12, /#radius-users) open the new address. */
(()=>{
  const h=location.hash.slice(1);if(!h)return;
  const m=/^device\/(\d+)$/.exec(h),to=m?"/devices/"+m[1]:PAGE_URL[h];
  if(to)location.replace(to);
})();

if(!document.body.dataset.denied)initPage();
loadMe().catch(()=>{});
resumeJob();

/* Automatic sign-out after real inactivity (background refreshes do not count as activity). */
(()=>{
  const timeout=Math.max(5*60*1000,Number(document.body.dataset.idleTimeoutMs)||15*60*1000);
  let timer=null,loggingOut=false;
  const activityEvents=["pointerdown","keydown","touchstart","scroll","click"];
  const logoutForIdle=async()=>{
    if(loggingOut)return;loggingOut=true;
    try{await fetch("/logout?reason=idle",{method:"POST",headers:{"X-CSRFToken":csrfToken(),"X-Requested-With":"XMLHttpRequest"},credentials:"same-origin",keepalive:true})}catch(e){}
    location.replace("/login?reason=idle");
  };
  const reset=()=>{if(loggingOut)return;clearTimeout(timer);timer=setTimeout(logoutForIdle,timeout)};
  activityEvents.forEach(ev=>addEventListener(ev,reset,{passive:true}));
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)reset()});
  reset();
})();

/* Heartbeat: tells the server once a minute that this browser is still open, so User Management can show who
   is signed in right now ("Active") on every screen, not only on the ones that refresh their data. It does
   not count as activity: the idle sign-out above still happens after real inactivity. */
setInterval(()=>{if(navigator.onLine!==false)fetch("/api/me",{credentials:"same-origin",headers:{"X-Requested-With":"XMLHttpRequest"}}).catch(()=>{})},60000);

/* Close buttons of the pop-ups (inline onclick is blocked by the Content-Security-Policy). */
document.addEventListener("click",e=>{const b=e.target.closest("[data-close-dlg]");if(b)document.getElementById(b.dataset.closeDlg).close()});

/* about this build (Ctrl+Alt+Shift+A): a card over the blurred page; Esc, a click outside or the X shuts it */
document.addEventListener("keydown",e=>{
  if(!(e.ctrlKey&&e.altKey&&e.shiftKey&&e.code==="KeyA"))return;
  e.preventDefault();
  if(document.querySelector(".abt-ov"))return;
  const d=t=>new TextDecoder().decode(Uint8Array.from(atob(t),c=>c.charCodeAt(0)));
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n};
  const ov=el("div","abt-ov"),card=el("div","abt-card");
  card.setAttribute("role","dialog");card.setAttribute("aria-modal","true");card.setAttribute("aria-label","About BdREN VAULT");
  const x=el("button","abt-x");x.type="button";x.setAttribute("aria-label","Close");
  x.innerHTML='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  const mark=el("div","abt-mark");
  const logo=document.querySelector(".brand .mark img");
  if(logo){const img=el("img");img.src=logo.src;img.alt="BdREN";mark.append(img)}
  const head=el("div","abt-head");head.append(mark,el("div","abt-app","BdREN VAULT"),el("div","abt-sub","Network Backup & AAA"));
  const div=el("div","abt-div");div.append(el("span"),el("i"),el("span"));
  const tags=el("div","abt-tags");["Configuration Backup","RADIUS / AAA","Session Log"].forEach(t=>tags.append(el("span","",t)));
  const foot=el("div","abt-foot");
  foot.append(el("span","","© "+new Date().getFullYear()+" "+d("QmFuZ2xhZGVzaCBSZXNlYXJjaCBhbmQgRWR1Y2F0aW9uIE5ldHdvcms=")),el("span","abt-key","Esc"));
  card.append(x,head,div,el("div","abt-by",d("RGVzaWduZWQgYW5kIGRldmVsb3BlZCBieQ==")),el("div","abt-name",d("TWQgQWhzYW51bCBIYXF1ZQ==")),el("div","abt-org",d("QmFuZ2xhZGVzaCBSZXNlYXJjaCBhbmQgRWR1Y2F0aW9uIE5ldHdvcmsgKEJkUkVOKQ==")),tags,foot);
  ov.append(card);document.body.append(ov);
  if(typeof sfx!=="undefined")sfx.play("about");
  const prev=document.activeElement;
  const shut=()=>{ov.classList.add("out");document.removeEventListener("keydown",onKey,true);setTimeout(()=>ov.remove(),200);prev&&prev.focus&&prev.focus()};
  const onKey=k=>{if(k.key==="Escape"){k.stopPropagation();shut()}};
  document.addEventListener("keydown",onKey,true);
  ov.addEventListener("click",k=>{if(k.target===ov)shut()});
  x.onclick=shut;x.focus();
});
