/* VAULT - core/menu.js
   The side menu and the top bar. Menu items are ordinary links (/dashboard, /devices, ...); the server renders
   the menu for the signed-in role and highlights the open screen (presentation/templates/base.html, core/pages.py).
   This file only adds: the menu button, the RADIUS / AAA drop-down and the account menu. */

/* ---- the menu button (three lines, top left of the top bar) ----
   desktop: minimise / expand the side menu (icons only when minimised), remembered in this browser;
   phones and tablets: the side menu slides in over the page and closes on outside tap or Esc */
const NAV_DRAWER=matchMedia("(max-width:1024px)");
function closeSide(){document.body.classList.remove("nav-open");if(NAV_DRAWER.matches)$("#menuBtn").setAttribute("aria-expanded","false")}
function setMin(on){
  document.body.classList.toggle("side-min",on);
  if(!NAV_DRAWER.matches){const b=$("#menuBtn"),t=on?"Expand menu":"Minimize menu";b.setAttribute("aria-expanded",!on);b.title=t;b.setAttribute("aria-label",t)}
  try{localStorage.setItem("nb_side_min",on?"1":"0")}catch(e){}
}
function paintMenuBtn(){
  const b=$("#menuBtn");
  if(NAV_DRAWER.matches){b.title="Menu";b.setAttribute("aria-label","Open menu");b.setAttribute("aria-expanded",document.body.classList.contains("nav-open"))}
  else setMin(document.body.classList.contains("side-min"));
}
$("#menuBtn").onclick=()=>{
  if(NAV_DRAWER.matches){const o=document.body.classList.toggle("nav-open");$("#menuBtn").setAttribute("aria-expanded",o)}
  else setMin(!document.body.classList.contains("side-min"));
};
NAV_DRAWER.addEventListener("change",()=>{closeSide();paintMenuBtn()});
$("#scrim").onclick=closeSide;
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeSide()});
paintMenuBtn();
/* back to where the menu was scrolled on the last screen (core/transition.js saves it) */
try{const y=+sessionStorage.getItem("vault_nav_y"),n=$(".side nav");if(n&&y>0)n.scrollTop=y}catch(e){}

/* ---- RADIUS / AAA drop-down: opens on click and remembers it; always open while one of its pages is shown ---- */
document.querySelectorAll(".side .dd").forEach(dd=>{
  const t=dd.querySelector(".dd-t"),m=dd.querySelector(".dd-m"),key="nb_dd_"+(dd.dataset.dd||"");
  const set=(open,remember=true)=>{m.hidden=!open;t.setAttribute("aria-expanded",open);if(remember)try{localStorage.setItem(key,open?"1":"0")}catch(e){}};
  t.onclick=()=>set(m.hidden);
  let saved=false;try{saved=localStorage.getItem(key)==="1"}catch(e){}
  set(dd.classList.contains("has-on")||saved,false);
});

/* ---- account menu in the top bar (sound, change password, sign out) ---- */
const userMenu=$("#userMenu");
document.addEventListener("click",e=>{
  if(!userMenu.open)return;
  if(!userMenu.contains(e.target)||e.target.closest("#pwBtn,#outBtn"))userMenu.open=false;   /* the sound switch keeps the menu open */
});
document.addEventListener("keydown",e=>{if(e.key==="Escape")userMenu.open=false});

/* timers and state shared by several page scripts, declared here because this file loads first */
let dashTimer=0;      /* refresh timer of the dashboard */
let devPageId=null;   /* id of the device shown on its own page (/devices/<id>) */
