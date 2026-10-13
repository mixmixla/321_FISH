const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','web.py'),'utf8');
const script=source.split('\n<script>')[1].split('</script>')[0];new vm.Script(script);
const start=script.indexOf('const GRENDER=');assert.ok(start>=0);
let renderer;
for(let end=script.indexOf('};',start);end>=0;end=script.indexOf('};',end+2)){
  const code=script.slice(start,end+2);try{new vm.Script(code);renderer=code;break}catch{}
}
assert.ok(renderer);
class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.disabled=false;this.textContent='';this.innerHTML='';}
  appendChild(child){this.children.push(child);return child;}
}
const sent=[];const state={uid:11,groom:'r1',gst:null};
const ctx={state,document:{createElement:tag=>new Element(tag)},gTitle:()=>new Element('h3'),
  gnick:u=>'P'+u,esc:x=>String(x),gameAPI:(op,args)=>sent.push(args.action)};
vm.createContext(ctx);vm.runInContext(renderer+';globalThis.kalah=GRENDER.kalah;',ctx);
function descendants(node){return [node,...node.children.flatMap(descendants)];}
function paint(uid,turn,status='playing',cells=Array(14).fill(4)){
  sent.length=0;state.uid=uid;state.groom='r1';
  const s={p0:11,p1:22,turn,status,cells,stores:{11:0,22:0}};
  state.gst={room:{room_id:'r1',status},state:s};
  const box=new Element('div');ctx.kalah(box,s);
  const all=descendants(box),buttons=all.filter(n=>n.tagName==='BUTTON');
  return {s,box,all,buttons};
}
for(const [uid,turn,expected] of [[11,11,[1,2,3,4,5,6]],[22,22,[9,10,11,12,13,14]]]){
  const v=paint(uid,turn);assert.equal(v.buttons.length,12); // six pits per row
  const active=v.buttons.filter(b=>!b.disabled);assert.equal(active.length,6);
  active.forEach(b=>b.onclick());assert.deepEqual(sent.map(a=>a.hole).sort((a,b)=>a-b),expected);
  assert.deepEqual(sent.map(a=>a.hole),uid===22?expected.slice().reverse():expected);
  const top=v.buttons.slice(0,6); // B: local6..1, global13..8, not empty slice
  assert.ok(top[0].textContent.includes('6'));assert.ok(top[5].textContent.includes('1'));
  assert.ok(v.all.some(n=>n.textContent.includes('轮到你')));
}
for(const [uid,turn,status] of [[33,11,'playing'],[11,22,'playing'],[22,11,'playing'],[22,22,'ended']]){
  const v=paint(uid,turn,status);
  if(uid===33||status==='ended')assert.equal(v.buttons.filter(b=>!b.disabled).length,0);
  v.buttons.filter(b=>!b.disabled).forEach(b=>b.onclick());
  if(uid!==turn||status!=='playing')assert.equal(sent.length,0);
  if(uid!==turn)assert.ok(!v.all.some(n=>n.textContent.includes('轮到你')));
}
const counts=[11,12,13,14,15,16,0,0,21,22,23,24,25,26];
const v=paint(22,22,'playing',counts);
assert.ok(v.buttons[0].textContent.includes('26'));assert.ok(v.buttons[5].textContent.includes('21'));
const stale=v.buttons.find(b=>!b.disabled);state.groom='new-room';stale.onclick();assert.equal(sent.length,0);
for(const mutate of [
  s=>{state.gst={room:{room_id:'r1',status:'playing'},state:{...s,turn:11}}},
  s=>{s.status='ended'},s=>{state.uid=11},s=>{s.cells[13]=0},
  s=>{state.gst.room.room_id='other-room'},s=>{state.gst.room.status='ended'}]){
  const old=paint(22,22);const button=old.buttons[0];mutate(old.s);button.onclick();assert.equal(sent.length,0);
}
const z=counts.slice();z[8]=0;const empty=paint(22,22,'playing',z);
assert.equal(empty.buttons.filter(b=>!b.disabled).length,5);
console.log(JSON.stringify({b_turn:true,both_six:true,guards:true,row_direction:true,full_script_syntax:true}));
