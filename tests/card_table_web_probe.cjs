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
vm.createContext(ctx);vm.runInContext(data.js,ctx);
const api=vm.runInContext('CardTableWeb',ctx);
const cards=Array.from({length:4},(_,i)=>({tier:1,art_set:'jewel-v2',art:12+i,title:'绿宝工坊'+i,disc:'e',pts:1,cost:{o:1}}));
const scene={game:'gemcity',status:'playing',players:[7,8],turn_uid:7,winner_uid:null,bank:{o:5,d:5,r:5,e:5,s:5,g:5},deck_left:{1:16,2:16,3:16},
 tokens:{7:{o:5,d:0,r:0,e:0,s:0,g:1}},discount:{7:{o:0}},score:{7:0,8:0},colors:{o:'黑玛瑙'},
 market:{1:cards,2:cards.map(c=>({...c,tier:2})),3:cards.map(c=>({...c,tier:3}))},nobles:[{e:4},{d:4},{o:4},{r:4},{s:4}],noble_art:[0,1,2,3,4]};
const collection=Array.from({length:31},(_,i)=>({...cards[i%4],title:'私藏'+i}));
function setScene(game,s,pv){ctx.state.gst={room:{room_id:'r1',game,status:'playing',round:1,players:[7,8]},state:s};ctx.state.gpriv=pv;ctx.state.ctGemMove=null;ctx.calls=[];}
let root;
function gem(){root=new Element('main');api.gemcity(root,ctx.state.gst.state);return root;}
ctx.renderGamePanel=gem;
function reset(over={},pv={cards:31,collection,reserved:[{...cards[0],title:'保留私密'}]}){setScene('gemcity',{...scene,...over},pv);gem();}
function chooseMarket(index=0){const market=all(root,'ct-market-row')[0].children[index];click(all(market,'ct-face')[0]);return market;}
reset();
assert.equal(all(root,'ct-market-row').length,3);assert.ok(all(root,'ct-market-row').every(row=>row.children.length===4));
assert.deepEqual(all(root,'ct-market-row').map(row=>row.dataset.tier),['3','2','1']);
assert.equal(all(root,'ct-album-grid')[0].children.length,31);assert.equal(all(root,'ct-patron').length,5);
click(all(all(root,'ct-album-grid')[0].children[0],'ct-face')[0]);
assert.equal(all(root,'ct-album-view')[0].hidden,false);assert.equal(all(root,'ct-album-grid')[0].hidden,true);
assert.equal(all(all(root,'ct-album-view')[0],'ct-art')[0].dataset.art,'12');assert.equal(ctx.calls.length,0);
click(all(root,'ct-album-back')[0]);assert.equal(all(root,'ct-album-grid')[0].hidden,false);assert.equal(ctx.calls.length,0);
let market=chooseMarket();
assert.equal(all(market,'ct-art')[0].dataset.art,'12');assert.equal(all(market,'ct-art')[0].dataset.artFile,'gemcity-tier3.webp?v=jewel-v2');
assert.equal(ctx.calls.length,0,'selecting never buys');assert.equal(all(root,'ct-reserve').length,0,'no repeated per-card action rows');
click(all(root,'ct-view-card')[0]);assert.equal(all(root,'ct-card-inspector')[0].hidden,false);assert.equal(ctx.calls.length,0);
click(all(root,'ct-inspect-close')[0]);assert.equal(all(root,'ct-card-inspector')[0].hidden,true);
click(all(root,'ct-confirm-reserve')[0]);assert.deepEqual(ctx.calls.pop(),{op:'reserve',tier:3,idx:0});
all(root,'ct-confirm-buy')[0].onclick();assert.equal(ctx.calls.length,0,'submission lock survives direct handler call');
gem();chooseMarket();all(root,'ct-confirm-reserve')[0].onclick();assert.equal(ctx.calls.length,0,'same snapshot redraw keeps submission lock');
reset();chooseMarket();click(all(root,'ct-confirm-buy')[0]);assert.deepEqual(ctx.calls.pop(),{op:'buy',tier:3,idx:0});
reset();click(all(all(root,'ct-reserved-grid')[0],'ct-face')[0]);assert.equal(ctx.calls.length,0);
click(all(root,'ct-confirm-buy')[0]);assert.deepEqual(ctx.calls.pop(),{op:'buy_res',idx:0});
const bank=color=>all(root,'ct-bank-chip').find(e=>e.dataset.gem===color);
reset();click(bank('o'));click(bank('o'));assert.equal(ctx.calls.length,0,'bank taps only select/deselect');
click(bank('o'));click(all(root,'ct-confirm-double')[0]);assert.deepEqual(ctx.calls.pop(),{op:'take2',color:'o'});
reset();for(const color of ['o','d','r'])click(bank(color));assert.equal(ctx.calls.length,0,'three coins still require confirmation');
click(bank('s'));assert.equal(ctx.state.ctGemMove.coins.length,3);click(all(root,'ct-confirm-take')[0]);assert.deepEqual(ctx.calls.pop(),{op:'take',colors:['o','d','r']});
reset();click(bank('s'));click(all(root,'ct-confirm-take')[0]);assert.deepEqual(ctx.calls.pop(),{op:'take',colors:['s']});
reset({bank:{...scene.bank,o:3}});click(bank('o'));assert.equal(all(root,'ct-confirm-double')[0].disabled,true);all(root,'ct-confirm-double')[0].onclick();assert.equal(ctx.calls.length,0);
reset();assert.equal(bank('g').tagName,'div');assert.ok(!bank('g').onclick,'gold is not selectable');
chooseMarket();const oldBuy=all(root,'ct-confirm-buy')[0];ctx.state.gst.state={...scene};oldBuy.onclick();assert.equal(ctx.calls.length,0);
reset();chooseMarket();const switched=all(root,'ct-confirm-buy')[0];ctx.state.token='another';switched.onclick();assert.equal(ctx.calls.length,0);delete ctx.state.token;
reset();chooseMarket();const roomChange=all(root,'ct-confirm-buy')[0];ctx.state.groom='r2';ctx.state.gst.room.room_id='r2';roomChange.onclick();assert.equal(ctx.calls.length,0);ctx.state.groom='r1';
reset({turn_uid:8});chooseMarket();assert.equal(all(root,'ct-confirm-buy')[0].disabled,true);all(root,'ct-confirm-buy')[0].onclick();assert.equal(ctx.calls.length,0);
click(all(root,'ct-view-card')[0]);assert.equal(all(root,'ct-card-inspector')[0].hidden,false,'waiting players can inspect');
reset({}, {reserved:[cards[0],cards[1],cards[2]],collection:[]});chooseMarket();assert.equal(all(root,'ct-confirm-reserve')[0].disabled,true);all(root,'ct-confirm-reserve')[0].onclick();assert.equal(ctx.calls.length,0);
reset({tokens:{7:{g:0}},discount:{7:{}}});chooseMarket();assert.equal(all(root,'ct-confirm-buy')[0].disabled,true);all(root,'ct-confirm-buy')[0].onclick();assert.equal(ctx.calls.length,0);
ctx.state.uid=99;reset();assert.equal(all(root,'ct-personal').length,0);assert.ok(!root.textContent.includes('私藏')&&!root.textContent.includes('保留私密'));ctx.state.uid=7;
reset({}, {cards:4,reserved:[]});assert.ok(root.textContent.includes('旧版牌局仅提供已购张数'));
for(const [color,row] of [['o',0],['d',1],['r',2],['e',3],['s',4]]){
 const card={tier:1,art_set:'jewel-v2',art:row*4,title:'实际'+color,disc:color,pts:0,cost:{o:1,d:2,r:3,e:4,s:5}};
 const a=api.development(card,{});assert.equal(all(a,'ct-art')[0].dataset.art,String(row*4));assert.equal(all(a,'ct-points').length,0);
 assert.deepEqual(all(a,'ct-price-coin').map(e=>e.children[1].textContent),['1','2','3','4','5']);
 const legacy=api.development({...card,art_set:undefined,title:'错名'},{});
 assert.equal(all(legacy,'ct-art')[0].dataset.artFile,undefined);assert.ok(all(legacy,'ct-neutral-'+color).length);assert.ok(!legacy.textContent.includes('错名'));
 const mismatch=api.development({...card,art:(row*4+4)%20},{});assert.equal(all(mismatch,'ct-art')[0].dataset.artFile,undefined);
}
assert.equal(all(api.development({tier:1,disc:'g',cost:{}},{}),'ct-jewel-g').length,0,'gold never becomes a permanent development bonus');
function love(s,pv){setScene('lovelove',s,pv);root=new Element('main');api.lovelove(root,s);return root;}
let loveScene={game:'lovelove',status:'playing',cur:7,alive:[7,8],dead:[],discard:[[8,2]],deck_left:8,winner_uid:null};
love(loveScene,{hand:4,drawn:1});let picks=all(root,'ct-love-hand')[0].children;assert.equal(picks.length,2);
click(picks[1]);let target=all(root,'ct-love-target')[0],guess=all(root,'ct-love-guess')[0],submit=all(root,'ct-love-submit')[0];
assert.equal(submit.disabled,true);assert.equal(submit.textContent,'先选目标');submit.onclick();assert.equal(ctx.calls.length,0);
target.value='8';target.onchange();assert.equal(submit.disabled,true);assert.equal(submit.textContent,'再选猜值');submit.onclick();assert.equal(ctx.calls.length,0);
guess.value='6';guess.onchange();assert.equal(submit.disabled,false);
target.value='';target.onchange();assert.equal(submit.disabled,true);submit.onclick();assert.equal(ctx.calls.length,0);
target.value='8';target.onchange();guess.value='';guess.oninput();assert.equal(submit.disabled,true);submit.onclick();assert.equal(ctx.calls.length,0);
guess.value='6';guess.oninput();assert.equal(submit.disabled,false);submit.onclick();submit.onclick();assert.equal(ctx.calls.length,1);
assert.deepEqual(ctx.calls.pop(),{op:'discard',play:1,target:8,val:6});
const stale=all(root,'ct-love-submit')[0];ctx.state.gpriv={hand:8};click(stale);assert.equal(ctx.calls.length,0);
love({...loveScene,cur:8},{hand:4,drawn:8});assert.equal(all(root,'ct-love-hand')[0].children.length,1);assert.equal(all(root,'ct-love-controls').length,0);
love(loveScene,{hand:8,drawn:7});picks=all(root,'ct-love-hand')[0].children;assert.equal(picks[0].disabled,true);click(picks[1]);click(all(root,'ct-love-submit')[0]);assert.equal(ctx.calls.pop().play,7);
for(const value of [2,3,5,6]){
 love(loveScene,{hand:value});click(all(root,'ct-love-hand')[0].children[0]);target=all(root,'ct-love-target')[0];submit=all(root,'ct-love-submit')[0];
 assert.equal(submit.disabled,true);submit.onclick();assert.equal(ctx.calls.length,0);
 target.value='7';target.onchange();assert.equal(submit.disabled,value!==5);
 target.value='8';target.onchange();assert.equal(submit.disabled,false);submit.onclick();assert.deepEqual(ctx.calls.pop(),{op:'discard',play:value,target:8});
}
for(const value of [4,7,8]){love(loveScene,{hand:value});click(all(root,'ct-love-hand')[0].children[0]);submit=all(root,'ct-love-submit')[0];assert.equal(submit.disabled,false);click(submit);assert.deepEqual(ctx.calls.pop(),{op:'discard',play:value});}
love({...loveScene,protected:[8]},{hand:5});click(all(root,'ct-love-hand')[0].children[0]);assert.ok(all(root,'ct-love-target')[0].children.some(o=>String(o.value)==='7'));
target=all(root,'ct-love-target')[0];target.value='7';target.onchange();click(all(root,'ct-love-submit')[0]);assert.deepEqual(ctx.calls.pop(),{op:'discard',play:5,target:7});
love({...loveScene,protected:[8]},{hand:2});click(all(root,'ct-love-hand')[0].children[0]);target=all(root,'ct-love-target')[0];target.value='8';target.onchange();click(all(root,'ct-love-submit')[0]);assert.equal(ctx.calls.pop().target,8);
love(loveScene,{hand:6});assert.equal(all(root,'ct-love-hand')[0].children.length,1);
ctx.state.uid=99;love(loveScene,{hand:8,drawn:7});assert.equal(all(root,'ct-love-private').length,0);assert.equal(all(root,'ct-role').length,1);
console.log(JSON.stringify({market_cards:12,patrons:5,collection_cards:31,art_zero:true,gem_actions:true,drawn_guard:true,target_guess_gated:true,single_submit:true,forced_countess:true,prince_self:true,protected_target_allowed:true,spectator_private_hidden:true,legacy_cards:true,stale_controls_rejected:true,selection_confirmation:true,color_rows_checked:true,gold_not_permanent:true}));
