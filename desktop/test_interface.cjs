const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const file=path.join(__dirname,'interface.html');
const test=require('node:test');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.style={setProperty(k,v){this[k]=v;}};this.hidden=false;this.disabled=false;this.checked=false;this._value='';this.textContent='';this.className='';this.classList={contains:c=>this.className.split(' ').includes(c),toggle:(c,on)=>{const a=new Set(this.className.split(' ').filter(Boolean));on?a.add(c):a.delete(c);this.className=[...a].join(' ');},remove:c=>this.classList.toggle(c,false),add:c=>this.classList.toggle(c,true)};}
 set value(v){this._value=String(v);}get value(){return this._value||this.children.find(c=>c.tagName==='option')?.value||'';}
 get options(){return this.children;}
 append(...nodes){this.children.push(...nodes);}add(n){this.append(n);}replaceChildren(...n){this.children=n;this._value='';}
 setAttribute(){}showModal(){}close(){}
}
const els={},get=id=>els[id]??=new Element(),walk=e=>e.children.flatMap(c=>[c,...walk(c)]),messages=[];
const document={getElementById:get,createElement:tag=>new Element(tag),querySelectorAll(query){
 const all=query.split(',').flatMap(s=>{const [root,selector]=s.split(' ');const nodes=walk(get(root.slice(1)));return nodes.filter(n=>selector==='input:checked'?n.tagName==='input'&&n.checked:selector==='input[data-measure]'?n.tagName==='input'&&n.dataset.measure:selector==='.field'?n.className.split(' ').includes('field'):n.tagName===selector);});return [...new Set(all)];
}};
const window={webkit:{messageHandlers:{lab:{postMessage:m=>messages.push(m)}}}};
const context=vm.createContext({document,window,Option:function(label,value){const e=new Element('option');e.textContent=label;e.value=value;return e;},console});
const html=fs.readFileSync(file,'utf8');vm.runInContext(html.slice(html.lastIndexOf('<script>')+8,html.lastIndexOf('</script>')),context);

function populated(){
 window.receiveNative({event:'ready',output:'/temporary-output'});
 window.receiveNative({event:'chosen',role:'input',path:'/temporary-input'});
 window.receiveNative({event:'busy',task:'inspect'});
 window.receiveNative({event:'inventory',path:'inventory.json',groups:[{count:1,records:[{index:0,name:'original.tif',shape:[1,64,64],dtype:'uint16',metadata:{}}],previews:['data:image/png;base64,']}],rejected:[]});
 window.receiveNative({event:'idle',task:'inspect',code:0});
 get('confirmed').checked=true;get('confirmed').onchange();assert.equal(get('run').disabled,false);
}
function cleared(){
 assert.equal(get('run').disabled,true);assert.equal(get('channelCard').hidden,true);
 assert.equal(get('confirmed').checked,false);assert.equal(get('previews').children.length,0);
 assert.equal(get('previewStatus').textContent,'');
}
test('re-scan immediately invalidates confirmation and stale controls; failure stays blocked',()=>{
 populated();get('inspect').onclick();cleared();
 window.receiveNative({event:'busy',task:'inspect'});
 window.receiveNative({event:'error',message:'Invalid ZIP'});
 window.receiveNative({event:'idle',task:'inspect',code:1});cleared();
});
test('empty inventory cannot revive prior previews or run controls; fresh import recovers',()=>{
 populated();window.receiveNative({event:'inventory',path:'empty.json',groups:[],rejected:[{name:'broken.tif',error:'corrupt'}]});cleared();
 window.receiveNative({event:'preview',inventory:'inventory.json',index:0,previews:['stale']});cleared();populated();
});

test('channel groups without previews request them on demand; a preview failure is reported',()=>{
 messages.length=0;
 window.receiveNative({event:'chosen',role:'input',path:'/mixed'});window.receiveNative({event:'busy',task:'inspect'});
 window.receiveNative({event:'inventory',path:'mixed.json',groups:[
  {count:2,records:[{index:0,name:'two.tif',shape:[2,64,64],dtype:'uint16',metadata:{}}],previews:null,preview_error:'ValueError: unreadable'},
  {count:3,records:[{index:1,name:'three.tif',shape:[3,64,64],dtype:'uint16',metadata:{}}],previews:null}],rejected:[]});
 window.receiveNative({event:'idle',task:'inspect',code:0});
 assert.ok(messages.some(m=>m.action==='preview'&&m.index===0));
 assert.match(get('previewStatus').textContent,/unreadable/);
 window.receiveNative({event:'idle',task:'preview',code:1});
 get('group').value='1';get('group').onchange();
 assert.ok(messages.some(m=>m.action==='preview'&&m.index===1));
});

function inventoryOf(count){
 return {event:'inventory',path:'batch.json',rejected:[],groups:[{count:2,previews:['data:a','data:b'],
  records:Array.from({length:count},(_,i)=>({index:i,name:`DN/Image ${i+1}.tif`,shape:[2,64,64],dtype:'uint16',metadata:{}}))}]};
}
function imported(count=3){
 window.receiveNative({event:'ready',output:'',version:'2.0'});
 window.receiveNative({event:'chosen',role:'input',path:'/batch'});window.receiveNative({event:'busy',task:'inspect'});
 window.receiveNative(inventoryOf(count));window.receiveNative({event:'idle',task:'inspect',code:0});
}
const fieldBoxes=()=>walk(get('fields')).filter(n=>n.tagName==='input');

test('2.0: the badge shows the app version and an import selects every FOV',()=>{
 imported(3);
 assert.match(get('versionBadge').textContent,/2\.0$/);
 assert.equal(get('fieldCount').textContent,'3 of 3 FOVs selected');
 assert.equal(get('batchSummary').textContent,'3 FOVs × 1 segmentation input = 3 segmentation tasks. Quantify 2 fluorescence channels for each object set.');
});

test('2.1: Select all and Deselect all sit side by side and are unavailable when they would change nothing',()=>{
 imported(3);
 assert.equal(get('allFields').disabled,true);assert.equal(get('noFields').disabled,false);
 get('noFields').onclick();assert.equal(get('fieldCount').textContent,'0 of 3 FOVs selected');
 assert.equal(get('allFields').disabled,false);assert.equal(get('noFields').disabled,true);
 const boxes=fieldBoxes();boxes[2].checked=true;boxes[2].onchange();
 assert.equal(get('fieldCount').textContent,'1 of 3 FOVs selected');
 assert.equal(get('allFields').disabled,false);assert.equal(get('noFields').disabled,false);
 get('allFields').onclick();assert.equal(get('fieldCount').textContent,'3 of 3 FOVs selected');
 window.receiveNative({event:'busy',task:'run'});assert.equal(get('noFields').disabled,true);assert.equal(get('allFields').disabled,true);
 window.receiveNative({event:'idle',task:'run',code:0});assert.equal(get('noFields').disabled,false);
});

test('2.0: ticking FOVs never starts a preview, and a loading preview does not lock the selection',()=>{
 imported(3);messages.length=0;
 const boxes=fieldBoxes();boxes[1].checked=false;boxes[1].onchange();
 assert.equal(messages.filter(m=>m.action==='preview').length,0);
 assert.equal(get('fieldCount').textContent,'2 of 3 FOVs selected');
 walk(get('fields')).filter(n=>n.className==='field-name')[2].onclick();
 assert.ok(messages.some(m=>m.action==='preview'&&m.index===2));
 window.receiveNative({event:'busy',task:'preview'});
 assert.equal(fieldBoxes()[0].disabled,false);assert.equal(get('chooseInput').disabled,true);assert.equal(get('run').disabled,true);
 window.receiveNative({event:'idle',task:'preview',code:0});
});

test('2.0: the run button says what is still missing',()=>{
 imported(2);
 assert.equal(get('runHint').textContent,'To run: choose an output directory · tick the confirmation above.');
 window.receiveNative({event:'chosen',role:'output',path:'/out'});
 get('confirmed').checked=true;get('confirmed').onchange();
 assert.equal(get('runHint').textContent,'');assert.equal(get('run').disabled,false);
 get('noFields').onclick();assert.equal(get('runHint').textContent,'To run: select at least one FOV · tick the confirmation above.');
 window.receiveNative({event:'chosen',role:'input',path:'/empty'});window.receiveNative({event:'busy',task:'inspect'});
 window.receiveNative({event:'inventory',path:'empty.json',groups:[],rejected:[{name:'notes.pdf',error:'Not a TIFF image.'}]});
 window.receiveNative({event:'idle',task:'inspect',code:0});
 assert.equal(get('runHint').textContent,'To run: import supported images.');
 assert.equal(get('rejectedCount').textContent,'1 unsupported file');
});

test('2.0: progress shows tasks done and readable activity; saved results are not reported as a new analysis',()=>{
 imported(2);window.receiveNative({event:'chosen',role:'output',path:'/out'});get('confirmed').checked=true;get('confirmed').onchange();
 window.receiveNative({event:'busy',task:'run'});assert.equal(get('status').textContent,'Loading images and the Cellpose model…');
 window.receiveNative({event:'model_ready',device:'mps',total:2});assert.equal(get('status').textContent,'Segmenting on MPS… 0 of 2 tasks');
 window.receiveNative({event:'progress',done:1,total:2,field:'f0',image:'Image 1.tif',channel:'C1',objects:1,seconds:2.04});
 assert.equal(get('status').textContent,'Segmenting on MPS: 1 of 2 tasks done');
 assert.equal(get('progress').style['--done'],'0.5');assert.ok(get('progress').classList.contains('determinate'));
 assert.match(get('log').textContent,/Image 1\.tif · C1: 1 object \(2\.0 s\)$/);
 window.receiveNative({event:'progress',done:2,total:2,stage:'writing'});assert.equal(get('status').textContent,'Writing measurements and the review page…');
 window.receiveNative({event:'finished',result:'/out/r/results',objects:1234,rows:22212});
 assert.equal(get('resultSummary').textContent,'1,234 segmented objects · 22,212 measurement rows. Technical checks passed.');
 assert.equal(get('resultHeading').textContent,'Results are ready');
 window.receiveNative({event:'idle',task:'run',code:0});
 window.receiveNative({event:'finished',result:'/old/results',objects:1,rows:9,opened:true});
 assert.equal(get('resultHeading').textContent,'Saved results');
 assert.equal(get('status').textContent,'Saved results opened. Review masks and measurements.');
});
