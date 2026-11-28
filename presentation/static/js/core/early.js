/* Runs before the page is drawn: restore collapsed-sidebar and theme choices (no inline script for strict CSP). */
try{
  if(localStorage.getItem("nb_side_min")==="1")document.body.classList.add("side-min");
  var t=localStorage.getItem("dbms_theme");
  if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;
}catch(e){}
