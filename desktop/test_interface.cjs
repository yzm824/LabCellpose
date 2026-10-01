const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const file=path.join(__dirname,'interface.html');
const test=require('node:test');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.style={};this.hidden=false;this.disabled=false;this.checked=false;this._value='';this.textContent='';this.className='';this.classList={contains:c=>this.className.split(' ').includes(c),toggle:(c,on)=>{const a=new Set(this.className.split(' ').filter(Boolean));on?a.add(c):a.delete(c);this.className=[...a].join(' ');},remove:c=>this.classList.toggle(c,false),add:c=>this.classList.toggle(c,true)};}
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
