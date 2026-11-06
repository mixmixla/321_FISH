// Run production card helpers and Gem City renderer against a small DOM harness.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.value='';this.isConnected=true;this.style={setProperty(k,v){this[k]=v}};
  this.classList={add:(...names)=>{this.className=[...new Set([...this.className.split(' '),...names])].join(' ')},
   toggle:(name,on)=>{const set=new Set(this.className.split(' '));if(on)set.add(name);else set.delete(name);this.className=[...set].join(' ')}};}
 append(...nodes){nodes.forEach(n=>this.appendChild(n));}
 appendChild(n){this.children.push(n);n.parentElement=this;if(this.tagName==='select'&&this.children.length===1)this.value=String(n.value);return n;}
 setAttribute(k,v){this.attrs[k]=v;}
 set textContent(value){this.text=String(value);this.children=[];}get textContent(){return (this.text||'')+this.children.map(c=>c.textContent).join('');}
 set innerHTML(value){this.html=value;this.children=[];if(this.tagName==='select')this.value='';}get innerHTML(){return this.html||'';}
}
const all=(root,cls)=>[...(root.className.split(' ').includes(cls)?[root]:[]),...root.children.flatMap(child=>all(child,cls))];
const click=e=>{if(!e.disabled&&e.onclick)e.onclick({stopPropagation(){}})};
const ctx={document:{createElement:tag=>new Element(tag),createTextNode:text=>{const e=new Element('text');e.textContent=text;return e;}},
 Image:class{},state:{uid:7,groom:'r1',gpriv:null,gst:null},BG:{},esc:String,resIcon:()=>'',bgImg:()=>'',gnick:uid=>'玩家'+uid,
 scoreHTML:()=>'',gTitle:()=>new Element('h2'),gameAPI:(op,payload)=>ctx.calls.push(JSON.parse(JSON.stringify(payload.action))),calls:[]};
vm.createContext(ctx);vm.runInContext(data.js,ctx);vm.runInContext('const GRENDER={'+data.gemcity+'};',ctx);
const cards=Array.from({length:4},(_,art)=>({tier:1,art,title:'市场'+art,disc:'e',pts:1,cost:{o:1}}));
const scene={game:'gemcity',status:'playing',players:[7,8],turn_uid:7,winner_uid:null,bank:{o:5,d:5,r:5,e:5,s:5,g:5},
 tokens:{7:{o:5,d:0,r:0,e:0,s:0,g:1}},discount:{7:{o:0}},score:{7:0,8:0},colors:{o:'黑玛瑙'},
 market:{1:cards,2:cards.map(c=>({...c,tier:2})),3:cards.map(c=>({...c,tier:3}))},nobles:[{e:4},{d:4},{o:4},{r:4},{s:4}],noble_art:[0,1,2,3,4]};
const collection=Array.from({length:31},(_,i)=>({...cards[i%4],title:'私藏'+i}));
function setScene(game,s,pv){ctx.state.gst={room:{room_id:'r1',game,status:'playing',round:1,players:[7,8]},state:s};ctx.state.gpriv=pv;ctx.calls=[];}
let root;
function gem(){root=new Element('main');vm.runInContext('GRENDER.gemcity',ctx)(root,scene);return root;}
ctx.renderGamePanel=gem;
setScene('gemcity',scene,{cards:31,collection,reserved:[{...cards[0],title:'保留私密'}]});gem();
assert.equal(all(root,'ct-market-row').length,3);assert.ok(all(root,'ct-market-row').every(row=>row.children.length===4));
assert.equal(all(root,'ct-album-grid')[0].children.length,31);assert.equal(all(root,'ct-patron').length,5);
click(all(all(root,'ct-album-grid')[0].children[0],'ct-face')[0]);
assert.equal(all(root,'ct-album-view')[0].hidden,false);assert.equal(all(root,'ct-album-grid')[0].hidden,true);
assert.equal(all(all(root,'ct-album-view')[0],'ct-art')[0].dataset.art,'0');assert.equal(ctx.calls.length,0);
click(all(root,'ct-album-back')[0]);assert.equal(all(root,'ct-album-grid')[0].hidden,false);assert.equal(ctx.calls.length,0);
let market=all(root,'ct-market-row')[0].children[0];
assert.equal(all(market,'ct-art')[0].dataset.art,'0');assert.equal(all(market,'ct-art')[0].dataset.artFile,'gemcity-tier1.webp');
click(all(market,'ct-reserve')[0]);assert.deepEqual(ctx.calls.pop(),{op:'reserve',tier:1,idx:0});
click(all(market,'ct-face')[0]);assert.deepEqual(ctx.calls.pop(),{op:'buy',tier:1,idx:0});
click(all(all(root,'ct-reserved-grid')[0],'ct-face')[0]);assert.deepEqual(ctx.calls.pop(),{op:'buy_res',idx:0});
const bank=color=>all(root,'ct-bank-chip').find(e=>e.dataset.gem===color);
click(bank('o'));click(bank('o'));assert.deepEqual(ctx.calls.pop(),{op:'take2',color:'o'});
click(bank('o'));click(bank('d'));click(bank('r'));assert.deepEqual(ctx.calls.pop(),{op:'take',colors:['o','d','r']});
click(bank('s'));const confirm=all(root,'ct-gem-tools')[0].children.flatMap(n=>n.children).find(e=>e.textContent==='💎 取 1 颗');
click(confirm);assert.deepEqual(ctx.calls.pop(),{op:'take',colors:['s']});
const oldBuy=all(market,'ct-face')[0];ctx.state.gst.state={...scene};click(oldBuy);assert.equal(ctx.calls.length,0);
ctx.state.uid=99;gem();assert.equal(all(root,'ct-personal').length,0);assert.ok(!root.textContent.includes('私藏')&&!root.textContent.includes('保留私密'));
ctx.state.uid=7;setScene('gemcity',scene,{cards:4,reserved:[]});delete cards[0].art;delete cards[0].title;gem();
assert.ok(all(root,'ct-no-art').length>0);assert.ok(root.textContent.includes('费用'));
const api=vm.runInContext('CardTableWeb',ctx);
function love(s,pv){setScene('lovelove',s,pv);root=new Element('main');api.lovelove(root,s);return root;}
let loveScene={game:'lovelove',status:'playing',cur:7,alive:[7,8],dead:[],discard:[[8,2]],deck_left:8,winner_uid:null};
love(loveScene,{hand:4,drawn:1});let picks=all(root,'ct-love-hand')[0].children;assert.equal(picks.length,2);
click(picks[1]);all(root,'ct-love-target')[0].value='8';all(root,'ct-love-guess')[0].value='6';click(all(root,'ct-love-submit')[0]);
assert.deepEqual(ctx.calls.pop(),{op:'discard',play:1,target:8,val:6});
const stale=all(root,'ct-love-submit')[0];ctx.state.gpriv={hand:8};click(stale);assert.equal(ctx.calls.length,0);
love({...loveScene,cur:8},{hand:4,drawn:8});assert.equal(all(root,'ct-love-hand')[0].children.length,1);assert.equal(all(root,'ct-love-controls').length,0);
love(loveScene,{hand:8,drawn:7});picks=all(root,'ct-love-hand')[0].children;assert.equal(picks[0].disabled,true);click(picks[1]);click(all(root,'ct-love-submit')[0]);assert.equal(ctx.calls.pop().play,7);
love(loveScene,{hand:5,drawn:2});click(all(root,'ct-love-hand')[0].children[0]);assert.ok(all(root,'ct-love-target')[0].children.some(o=>String(o.value)==='7'));
love(loveScene,{hand:6});assert.equal(all(root,'ct-love-hand')[0].children.length,1);
ctx.state.uid=99;love(loveScene,{hand:8,drawn:7});assert.equal(all(root,'ct-love-private').length,0);assert.equal(all(root,'ct-role').length,1);
console.log(JSON.stringify({market_cards:12,patrons:5,collection_cards:31,art_zero:true,gem_actions:true,drawn_guard:true,forced_countess:true,prince_self:true,spectator_private_hidden:true,legacy_cards:true,stale_controls_rejected:true}));
