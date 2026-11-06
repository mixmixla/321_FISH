const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.dataset={};this.className='';this.style={setProperty(k,v){this[k]=v;}};}
 append(...items){items.forEach(e=>this.appendChild(e));}appendChild(e){this.children.push(e);e.parent=this;return e;}
 setAttribute(k,v){this.attrs[k]=String(v);}get isConnected(){return this===root||!!this.parent?.isConnected;}
 set textContent(v){this.text=String(v);this.children=[];}get textContent(){return(this.text||'')+this.children.map(e=>e.textContent).join('');}
}
const all=(e,cls)=>[...(e.className.split(' ').includes(cls)?[e]:[]),...e.children.flatMap(c=>all(c,cls))];
let root=new Element('main');const ctx={document:{createElement:t=>new Element(t)},state:{uid:7,groom:'j1',token:'A'},GRENDER:{},gnick:u=>'P'+u,calls:[],gameAPI:(op,args)=>{ctx.calls.push(JSON.parse(JSON.stringify(args.action)));return Promise.resolve({ok:true});}};
function render(frame=data.initial){root.children.forEach(e=>e.parent=null);root.children=[];ctx.GRENDER.balatro(root,ctx.state.gst.state);}
function frame(f=data.initial){ctx.state.gst={room:{room_id:'j1',game:'balatro',status:'playing',round:1,players:[7,8],spectators:[]},state:f.state};ctx.state.gpriv=f.private;ctx.state.jokerView=null;ctx.state.uid=7;ctx.state.groom='j1';ctx.state.token='A';ctx.calls=[];render();}
ctx.renderGamePanel=()=>render();vm.createContext(ctx);vm.runInContext(data.js,ctx);
const click=e=>{assert.ok(e);if(!e.disabled)e.onclick?.();};
frame();assert.equal(all(root,'jt-hand')[0].children.length,8);assert.equal(all(root,'jt-joker').length,2);
const cid=data.initial.private.hand[0].id;click(all(root,'jt-hand')[0].children[0]);assert.deepEqual(ctx.calls,[{op:'select',cid}]);
click(all(root,'jt-hand')[0].children[0]);assert.equal(ctx.calls.length,1);
frame(data.selected);click(all(root,'jt-settle')[0]);assert.deepEqual(ctx.calls,[{op:'play'}]);
frame();click(all(root,'jt-discard')[0]);assert.equal(ctx.calls.length,0);click(all(root,'jt-hand')[0].children[0]);assert.deepEqual(ctx.calls,[{op:'discard',cid}]);
frame();click(all(root,'jt-joker')[0]);assert.equal(all(root,'jt-inspector').length,1);assert.equal(ctx.calls.length,0);
assert.ok(!all(root,'jt-hand')[0].children.some(e=>e.onclick));click(all(root,'jt-close')[0]);assert.equal(all(root,'jt-inspector').length,0);
for(const mutate of [()=>ctx.state.token='B',()=>ctx.state.groom='j2',()=>ctx.state.gst.room={...ctx.state.gst.room},()=>ctx.state.gst.state={...ctx.state.gst.state},()=>ctx.state.gpriv={...ctx.state.gpriv}]){
 frame();const old=all(root,'jt-hand')[0].children[0];mutate();old.onclick();assert.equal(ctx.calls.length,0);
}
for(const uid of [8,99]){frame(data.played);ctx.state.uid=uid;ctx.state.gpriv=data.initial.private;ctx.state.jokerView=null;render();assert.equal(all(root,'jt-own-hand').length,0);assert.equal(all(root,'jt-poker').length,data.played.state.last_play.cards.length);assert.equal(ctx.calls.length,0);}
frame();ctx.state.gst.room.status='ended';render();assert.equal(all(root,'jt-own-hand').length,0);assert.ok(root.textContent.includes('本局已结束'));assert.ok(all(root,'jt-head')[0].textContent.includes('本局结束'));assert.ok(!root.textContent.includes('等待本人私有手牌'));
console.log(JSON.stringify({select:true,discard_pile:true,actual_settlement:true,read_only_joker:true,private_cards_hidden:true,stale_callbacks_blocked:true}));
