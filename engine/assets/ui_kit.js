/* Interface kit (3.0) shared by the setup page, the review and its host: icons, element builders and brief messages.
   Presentation only. */
(function(root){
'use strict';
// 16 × 16 line icons, drawn with the current text colour. "!" marks a filled shape.
const ICONS={
 check:'M3.5 8.5l3 3 6-7',close:'M4 4l8 8M12 4l-8 8',plus:'M8 3v10M3 8h10',minus:'M3 8h10',
 left:'M10 3.5L5.5 8l4.5 4.5',right:'M6 3.5L10.5 8 6 12.5',down:'M3.5 6L8 10.5 12.5 6',
 fit:'M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10',
 eye:'M1.5 8S3.9 3.5 8 3.5 14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8zM8 6.2a1.8 1.8 0 100 3.6 1.8 1.8 0 000-3.6z',
 eyeOff:'M2.5 2.5l11 11M6.3 4a6.6 6.6 0 011.7-.5c4.1 0 6.5 4.5 6.5 4.5a11 11 0 01-2.1 2.6M9.9 12.2a6.5 6.5 0 01-1.9.3C3.9 12.5 1.5 8 1.5 8a11.3 11.3 0 012.8-3.1',
 layers:'M8 2.2l6 3.1-6 3.1-6-3.1 6-3.1zM2.5 8.2L8 11l5.5-2.8M2.5 10.9L8 13.7l5.5-2.8',
 contrast:'M8 2.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11z|!M8 2.5a5.5 5.5 0 010 11z',
 folder:'M2 4.5A1.5 1.5 0 013.5 3h2.6l1.4 1.5h5A1.5 1.5 0 0114 6v5.5a1.5 1.5 0 01-1.5 1.5h-9A1.5 1.5 0 012 11.5v-7z',
 reveal:'M9.5 2.5h4v4M13.5 2.5l-6 6M11.5 9.2v3.3a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1h3.3',
 undo:'M5.8 3.2L2.8 6.2l3 3M2.8 6.2h6.4a3.5 3.5 0 010 7H7.5',
 ruler:'M2 10.5L10.5 2 14 5.5 5.5 14 2 10.5zM4.9 9.4l1.3 1.3M6.9 7.4l1.3 1.3M8.9 5.4l1.3 1.3',
 test:'M8 1.8v2.4M8 11.8v2.4M1.8 8h2.4M11.8 8h2.4M3.6 3.6l1.7 1.7M10.7 10.7l1.7 1.7M12.4 3.6l-1.7 1.7M5.3 10.7l-1.7 1.7',
 play:'!M5 3.3v9.4a.5.5 0 00.8.4l6.6-4.7a.5.5 0 000-.8L5.8 2.9a.5.5 0 00-.8.4z',stop:'!M4.5 3.5h7a1 1 0 011 1v7a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1z',
 table:'M2.5 3.5h11v9h-11zM2.5 6.5h11M2.5 9.5h11M6.5 3.5v9',download:'M8 2.5V10M4.8 6.8L8 10l3.2-3.2M3 13h10',
 images:'M2.5 4.5h8.5v7.5H2.5zM2.5 10l2.4-2.4 2 2 1.5-1.5L11 10.7M13.5 6.5v7H5M6.3 6.7v.1',
 warning:'M8 2.5l6 10.5H2L8 2.5zM8 6.7v2.9M8 11.3v.1',info:'M8 2.2a5.8 5.8 0 100 11.6A5.8 5.8 0 008 2.2zM8 7.3v3.6M8 5.1v.1',
 keyboard:'M2.5 4h11a1 1 0 011 1v6a1 1 0 01-1 1h-11a1 1 0 01-1-1V5a1 1 0 011-1zM4.2 6.8h.1M6.7 6.8h.1M9.2 6.8h.1M11.7 6.8h.1M4.7 9.5h6.6',
 pointer:'M6 1.8v2M1.8 6h2M3 3l1.4 1.4M6.8 6.8l6.9 2.4-3 1.3-1.3 3-2.6-6.7z',
 grid:'M2.5 2.5H7V7H2.5zM9 2.5h4.5V7H9zM2.5 9H7v4.5H2.5zM9 9h4.5v4.5H9z',
 sliders:'M2.5 4.5h6.3M12.2 4.5h1.3M2.5 8h1.8M7.7 8h5.8M2.5 11.5h5.3M11.2 11.5h2.3M10.5 3a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM6 6.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM9.5 10a1.5 1.5 0 100 3 1.5 1.5 0 000-3z',
 refresh:'M13 8a5 5 0 11-1.5-3.6M13 2.8v2.7h-2.7',clock:'M8 2.2a5.8 5.8 0 100 11.6A5.8 5.8 0 008 2.2zM8 4.8V8l2.2 1.4',
 rows:'M2.5 3.5h11v3.5h-11zM2.5 9h11v3.5h-11z'};
const NS='http://www.w3.org/2000/svg';
function icon(name,size){
 const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 16 16');svg.setAttribute('class','icon');svg.setAttribute('aria-hidden','true');
 if(size){svg.style.width=size+'px';svg.style.height=size+'px';}
 for(const part of (ICONS[name]||'').split('|')){
  const path=document.createElementNS(NS,'path'),solid=part.startsWith('!');
  path.setAttribute('d',solid?part.slice(1):part);if(solid)path.setAttribute('class','solid');svg.append(path);
 }
 return svg;
}
function el(tag,props={},...children){
 const e=document.createElement(tag);
 for(const[k,v]of Object.entries(props)){
  if(k==='text')e.textContent=v;else if(k==='class')e.className=v;else if(k==='icon')e.append(icon(v));else if(k==='data')Object.assign(e.dataset,v);
  else if(k in e)e[k]=v;else e.setAttribute(k,v);
 }
 e.append(...children.filter(c=>c!=null));return e;
}
function svgEl(tag,attrs={}){const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,String(v));return e;}
// The Windows app shows the same pages. Where macOS wording differs (⌘, ⌥, Finder) the markup carries the Windows
// wording as data-win (text) or data-win-title (tooltip); data-mac-only marks what only a Mac has.
const windows=typeof navigator!=='undefined'&&/Windows NT/.test(navigator.userAgent||'');
// Elements written in the page as <i data-icon="name"></i> become icons, so the markup stays readable.
function decorate(scope=document){
 for(const holder of scope.querySelectorAll('[data-icon]')){
  const svg=icon(holder.dataset.icon,Number(holder.dataset.size)||0);
  for(const name of holder.classList)svg.classList.add(name);
  holder.replaceWith(svg);
 }
 if(!windows)return;
 for(const node of scope.querySelectorAll('[data-win]'))node.textContent=node.dataset.win;
 for(const node of scope.querySelectorAll('[data-win-title]'))node.title=node.dataset.winTitle;
 for(const node of scope.querySelectorAll('[data-mac-only]'))node.remove();
}
let toastNode=null,toastTimer=0;
function toast(message,kind=''){
 toastNode?.remove();clearTimeout(toastTimer);
 if(!message)return;
 toastNode=el('div',{class:'toast'+(kind?' '+kind:''),role:kind==='error'?'alert':'status',text:String(message)});
 document.body.append(toastNode);const mine=toastNode;
 toastTimer=setTimeout(()=>{if(toastNode===mine){mine.remove();toastNode=null;}},kind==='error'?9000:4500);
}
root.LabUI={icon,el,svgEl,decorate,toast,ICONS,windows};
})(globalThis);
