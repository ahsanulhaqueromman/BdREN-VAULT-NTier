/* VAULT - core/transition.js (loaded in <head>, before the page is drawn)
   Moving between screens uses the browser's cross-page transition (app.css @view-transition). Its pagereveal
   event fires before the first frame, so this listener must exist before <body> is parsed; when the browser
   skips a transition (slow page, busy tab) it rejects the promises ("Transition was aborted"): harmless. */
addEventListener("pagereveal",e=>{const t=e.viewTransition;if(!t)return;t.ready.catch(()=>{});t.finished.catch(()=>{});t.updateCallbackDone.catch(()=>{})});
addEventListener("pageswap",e=>{const t=e.viewTransition;if(!t)return;t.ready.catch(()=>{});t.finished.catch(()=>{});t.updateCallbackDone.catch(()=>{})});
/* the side menu keeps its scroll position from screen to screen (menu.js puts it back), so a long menu does
   not jump to the top when an item lower down is opened */
addEventListener("pagehide",()=>{const n=document.querySelector(".side nav");try{if(n)sessionStorage.setItem("vault_nav_y",n.scrollTop)}catch(e){}});
