const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const payload=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.isConnected=true;this.clientWidth=332;this.clientHeight=330;
  this.style={setProperty(k,v){this[k]=v}};this.classList={add:n=>{this.className+=' '+n},toggle:(n,on)=>{const names=new Set(this.className.split(' '));if(on)names.add(n);else names.delete(n);this.className=[...names].join(' ')}};}
 append(...nodes){nodes.forEach(n=>this.appendChild(n));}appendChild(node){this.children.push(node);return node;}setAttribute(k,v){this.attrs[k]=v;}
 scrollIntoView(){this.scrolledIntoView=true;}
 set textContent(value){this.text=String(value);this.children=[];}get textContent(){return (this.text||'')+this.children.map(n=>n.textContent).join('');}
}
const all=(root,cls)=>[...(root.className.split(' ').includes(cls)?[root]:[]),...root.children.flatMap(n=>all(n,cls))];
const click=button=>{if(!button.disabled&&button.onclick)button.onclick({stopPropagation(){}})};
const calls=[],ctx={state:{uid:1,groom:'r1'},innerWidth:390,MANOR_ATLASES:payload.catalog,
 document:{createElement:tag=>new Element(tag)},gnick:uid=>'玩家'+uid,gTitle:()=>new Element('h2'),
 requestAnimationFrame:callback=>callback(),gameAPI:(op,data)=>calls.push(JSON.parse(JSON.stringify(data.action)))};
vm.createContext(ctx);vm.runInContext(payload.js,ctx);const api=vm.runInContext('ManorWeb',ctx);
const scene={game:'betrayal',phase:'explore',players:[1,2,3],alive:[1,2,3],dead:[],seats:{1:1,2:2,3:3},turn_uid:1,steps_left:3,
 pos:{1:'0,0',2:'0,0',3:'0,0'},rooms:{'0,0':'门','0,-1':'礼'},room_names:{'0,0':'门厅','0,-1':'礼拜堂'},tiles_left:18,
 discoveries:[{pos:'0,-1',room:'礼拜堂',uid:1,cards:[{kind:'event',name:'意外的馈赠',text:'本次获得光之水晶'},{kind:'item',name:'光之水晶',text:'使用后速度 +1'}]}],
 stats:{1:{might:3,speed:3,sanity:3,knowledge:3}},items:{1:['光之水晶'],2:[],3:[]},haunt:null};
let root;
function paint(s=scene){ctx.state.gst={room:{room_id:'r1',round:1,game:'betrayal',status:'playing',players:[1,2,3]},state:s};ctx.state.gpriv={items:s.items[ctx.state.uid]||[]};root=new Element('main');api.paint(root,s);return root;}
ctx.renderGamePanel=()=>paint(ctx.state.gst.state);
paint();assert.equal(all(root,'mn-tile').length,2);assert.equal(all(root,'mn-seat').length,3);
assert.equal(all(root,'mn-door').length,4);assert.equal(all(root,'mn-discovery-cards')[0].children.length,2);
assert.ok(root.textContent.includes('礼拜堂')&&root.textContent.includes('本次获得光之水晶'));
const entrance=all(root,'mn-tile').find(t=>t.dataset.pos==='0,0');assert.equal(all(entrance,'mn-art')[0].dataset.artIndex,'0');
click(all(root,'mn-door').find(d=>d.dataset.door==='up'));assert.deepEqual(calls.pop(),{move:'up'});
click(all(root,'mn-action').find(b=>b.dataset.end));assert.deepEqual(calls.pop(),{end:true});
click(all(root,'mn-action').find(b=>b.dataset.use));assert.deepEqual(calls.pop(),{use:'光之水晶'});
const oldDoor=all(root,'mn-door')[0];ctx.state.gst.state={...scene};oldDoor.onclick({stopPropagation(){}});assert.equal(calls.length,0);
const far={...scene,phase:'haunt',haunt:{traitor:3,exit:'9,9',scenario:'血月惊魂'},rooms:{...scene.rooms,'9,9':'出'},room_names:{...scene.room_names,'9,9':'出口之门'},pos:{1:'9,9',2:'9,9',3:'9,9'}};
paint(far);assert.equal(all(root,'mn-tile').length,1);assert.equal(all(root,'mn-seat').length,3);
click(all(root,'mn-action').find(b=>b.dataset.attack==='3'));assert.deepEqual(calls.pop(),{attack:3});
click(all(root,'mn-action').find(b=>b.dataset.escape));assert.deepEqual(calls.pop(),{escape:true});
click(all(root,'mn-view-button').find(b=>b.textContent==='查看全图'));assert.equal(all(root,'mn-tile').length,3);
assert.ok(all(root,'mn-stage')[0].style.width.endsWith('px'));assert.ok(all(root,'mn-tile').length<10);
click(all(root,'mn-history-entry')[0]);assert.equal(all(root,'mn-card').length,2);assert.ok(root.textContent.includes('使用后速度 +1'));
ctx.state.uid=99;paint(scene);assert.ok(all(root,'mn-action').every(b=>b.disabled));
ctx.state.uid=1;ctx.state.manorView=null;paint({...scene,room_names:undefined,discoveries:undefined});assert.ok(root.textContent.includes('门'));assert.equal(all(root,'mn-card').length,0);
console.log(JSON.stringify({revealed_only:true,three_seats:true,room_zero_art:true,doors:true,old_state_blocked:true,multiple_cards:true,history:true,escape:true,attack:true,item:true,far_map_bounded_nodes:true,spectator_read_only:true,old_fields:true}));
