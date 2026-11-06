const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.value='';this.isConnected=true;this.style={setProperty(k,v){this[k]=v}};
  this.classList={add:(...names)=>{this.className=[...new Set([...this.className.split(' '),...names])].join(' ')},toggle:(name,on)=>{const s=new Set(this.className.split(' '));if(on)s.add(name);else s.delete(name);this.className=[...s].join(' ')}};}
 append(...nodes){nodes.forEach(n=>this.appendChild(n));}appendChild(n){this.children.push(n);n.parentElement=this;if(this.tagName==='select'&&this.children.length===1)this.value=String(n.value);return n;}
 setAttribute(k,v){this.attrs[k]=v;}set textContent(v){this.text=String(v);this.children=[];}get textContent(){return(this.text||'')+this.children.map(c=>c.textContent).join('');}
 set innerHTML(v){this.children=[];if(this.tagName==='select')this.value='';}
}
const all=(root,cls)=>[...(root.className.split(' ').includes(cls)?[root]:[]),...root.children.flatMap(child=>all(child,cls))];
const click=e=>{assert.ok(e,'missing control');if(!e.disabled&&e.onclick)e.onclick({stopPropagation(){}})};
const ctx={document:{createElement:tag=>new Element(tag)},Image:class{},state:{uid:7,groom:'r1'},gnick:uid=>'合成'+uid,gTitle:()=>new Element('h2'),calls:[],gameAPI:(op,payload)=>ctx.calls.push(JSON.parse(JSON.stringify(payload.action)))};
vm.createContext(ctx);vm.runInContext(data.js,ctx);const api=vm.runInContext('CardTableWeb',ctx);
const scene={game:'lovelove',status:'playing',cur:7,alive:[7,8,9],dead:[],discard:[[9,2]],deck_left:8,winner_uid:null};let root;
function render(s=scene,pv={hand:4,drawn:1}){ctx.state.gst={room:{room_id:'r1',game:'lovelove',status:s.status,round:1,players:[7,8,9]},state:s};ctx.state.gpriv=pv;ctx.calls=[];root=new Element('main');api.lovelove(root,s);}
render();click(all(root,'ct-love-hand')[0].children[1]);
assert.deepEqual(all(root,'ct-love-player').map(e=>e.dataset.uid),['8','9']);
const guesses=all(root,'ct-love-guess-card');assert.equal(guesses.length,8);
guesses.forEach((card,index)=>{assert.equal(card.dataset.value,String(index+1));assert.equal(all(card,'ct-art')[0].dataset.art,String(index));assert.equal(all(card,'ct-art')[0].dataset.artFile,'lovelove-court.webp?v=anime-court-v1');});
let submit=all(root,'ct-love-submit')[0];assert.equal(submit.disabled,true);click(all(root,'ct-love-player')[0]);assert.equal(submit.disabled,true);
click(guesses[5]);assert.equal(submit.disabled,false);assert.equal(ctx.calls.length,0);click(submit);click(submit);
assert.deepEqual(ctx.calls,[{op:'discard',play:1,target:8,val:6}]);
render(scene,{hand:5,drawn:4});click(all(root,'ct-love-hand')[0].children[0]);assert.equal(all(root,'ct-love-player')[0].dataset.uid,'7');
click(all(root,'ct-love-player')[0]);click(all(root,'ct-love-submit')[0]);assert.deepEqual(ctx.calls[0],{op:'discard',play:5,target:7});
render({...scene,cur:8},{hand:3,peek:{target:8,value:6}});assert.equal(all(root,'ct-love-peek').length,1);assert.ok(all(root,'ct-love-peek')[0].textContent.includes('当时查看'));assert.equal(all(root,'ct-love-controls').length,0);
ctx.state.uid=8;render({...scene,cur:8},{hand:6});assert.equal(all(root,'ct-love-peek').length,0);
ctx.state.uid=99;render(scene,{hand:3,drawn:1,peek:{target:8,value:6}});assert.equal(all(root,'ct-love-peek').length,0);assert.equal(all(root,'ct-love-private').length,0);assert.equal(all(root,'ct-role').length,1);
ctx.state.uid=7;render({...scene,status:'ended'},{hand:3,peek:{target:8,value:6}});assert.equal(all(root,'ct-love-peek').length,0);
render(scene,{hand:8,drawn:7});const choices=all(root,'ct-love-hand')[0].children;assert.equal(choices[0].disabled,true);click(choices[1]);click(all(root,'ct-love-submit')[0]);assert.deepEqual(ctx.calls,[{op:'discard',play:7}]);
console.log(JSON.stringify({visual_guard_action:true,all_eight_role_cells:true,prince_self:true,priest_only_actor:true,ended_peek_hidden:true,forced_countess:true}));
