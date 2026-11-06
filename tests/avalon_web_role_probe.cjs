const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{constructor(){this.children=[];this.style={};this.dataset={};this.textContent='';this.innerHTML='';}appendChild(e){this.children.push(e);return e;}append(...nodes){nodes.forEach(n=>this.appendChild(n));}}
const nodes=root=>[root,...root.children.flatMap(nodes)],calls=[];
const ctx={state:{uid:0,groom:'r1',gpriv:null},document:{createElement:()=>new Element(),createTextNode:text=>{const e=new Element();e.textContent=text;return e;}},esc:String,gnick:u=>'P'+u,roleIcon:()=>'',scoreHTML:()=>'',gTitle:()=>new Element(),gameAPI:(op,payload)=>calls.push(payload.action),gBtn:(text,action)=>{const b=new Element();b.textContent=text;return b;}};
vm.createContext(ctx);vm.runInContext('const renderer={'+data.renderer+'};',ctx);const render=vm.runInContext('renderer.avalon',ctx);
let assassinButton;
for(const [uid,pv] of Object.entries(data.private)){
 ctx.state.uid=+uid;ctx.state.gpriv=pv;ctx.state.gst={room:{game:'avalon',status:'playing'},state:data.snapshot};const root=new Element();render(root,data.snapshot);
 const all=nodes(root),html=all.map(e=>e.innerHTML+e.textContent).join(''),guess=all.filter(e=>e.textContent.startsWith('指认 '));
 if(pv.role===1){assert.ok(html.includes('梅林所见叛军'));for(const evil of pv.evil)assert.ok(html.includes('P'+evil));assert.equal(guess.length,0);}
 else assert.ok(!html.includes('梅林所见叛军'));
 if(pv.role===2){assert.ok(html.includes('你是刺客'));assert.equal(guess.length,data.snapshot.players.length-1);guess[0].onclick();assert.equal(calls.pop().op,'guess');assassinButton=guess[0];}
 else {assert.ok(!html.includes('你是刺客'));assert.equal(guess.length,0);}
 if(pv.role===3)assert.ok(html.includes('莫德雷德'));
}
ctx.state.uid=99;ctx.state.gpriv=data.private[Object.keys(data.private).find(uid=>data.private[uid].role===1)];
const observer=new Element();render(observer,data.snapshot);assert.ok(!nodes(observer).map(e=>e.innerHTML).join('').includes('你的身份'));assert.equal(nodes(observer).filter(e=>e.textContent.startsWith('指认 ')).length,0);
assassinButton.onclick();assert.equal(calls.length,0);
const actions=[];
function paint(uid,s,pv){ctx.state.uid=uid;ctx.state.gpriv=pv;ctx.state.gst={room:{game:'avalon',status:'playing'},state:s};const root=new Element();render(root,s);return nodes(root);}
for(const trace of data.traces){const emitted=[];for(const step of trace.steps){
 const list=paint(step.uid,step.snapshot,step.private),wanted=step.action;
 if(wanted.team){for(const uid of wanted.team){const pick=list.find(e=>+e.dataset.u===uid);assert.ok(pick);pick.onclick();}list.find(e=>e.textContent==='确定组队').onclick();}
 else if('approve' in wanted)list.find(e=>e.textContent===(wanted.approve?'✅ 通过':'❌ 否决')).onclick();
 else if('success' in wanted){if(![2,3].includes(step.private.role))assert.ok(!list.some(e=>e.textContent==='💥 失败'));list.find(e=>e.textContent===(wanted.success?'✅ 成功':'💥 失败')).onclick();}
 else list.find(e=>e.textContent==='指认 P'+wanted.target).onclick();
 const action=JSON.parse(JSON.stringify(calls.pop()));assert.deepEqual(action,wanted);emitted.push(action);
 if(step.snapshot.phase==='nominate'){const other=step.snapshot.players.find(uid=>uid!==step.uid);assert.ok(!paint(other,step.snapshot,{role:0,name:'亚瑟忠臣'}).some(e=>e.textContent==='确定组队'));}
 if(step.snapshot.voted.length){const uid=step.snapshot.voted[0];assert.ok(!paint(uid,step.snapshot,{role:0,name:'亚瑟忠臣'}).some(e=>e.textContent==='✅ 通过'));}
 if(step.snapshot.quest_done.length){const uid=step.snapshot.quest_done[0];assert.ok(!paint(uid,step.snapshot,{role:0,name:'亚瑟忠臣'}).some(e=>e.textContent==='✅ 成功'));}
}actions.push(emitted);}
vm.runInContext('const workshopRenderer={'+data.gongfang+'};',ctx);const workshop=vm.runInContext('workshopRenderer.gongfang',ctx);
ctx.state.uid=12;let root=new Element();workshop(root,data.workshop);const html=nodes(root).map(e=>e.innerHTML+e.textContent).join('');
assert.ok(!html.includes('✨')&&!html.includes('#e8b93c')&&html.includes('P11'));
root=new Element();workshop(root,{...data.workshop,spots:data.workshop.spots.map(s=>({...s,exclusive:!s.exclusive}))});assert.equal(nodes(root).map(e=>e.innerHTML+e.textContent).join(''),html);
console.log(JSON.stringify({assassin_role2:true,mordred_role3:true,merlin_private_evil_visible:true,loyal_and_spectator_no_private:true,only_assassin_guess:true,stale_guess_blocked:true,workshop_no_false_exclusive:true,actions}));
