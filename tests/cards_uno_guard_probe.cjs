// Production UNO callbacks with an instrumented DOM, including a positive send.
const fs=require('node:fs'),assert=require('node:assert/strict');
class E{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.isConnected=true;this.className='';this.style={setProperty(){}};
  this.classList={add:(...v)=>this.className=[...new Set([...this.className.split(' '),...v])].join(' '),remove:(...v)=>this.className=this.className.split(' ').filter(x=>!v.includes(x)).join(' ')};}
 setAttribute(){}append(...nodes){for(const n of nodes){this.children.push(n);if(n instanceof E)n.parent=this;}}appendChild(n){this.append(n)}
 querySelectorAll(selector){return walk(this).slice(1).filter(e=>selector==='button'?e.tag==='button':selector.startsWith('.')?e.className.split(' ').includes(selector.slice(1)):false);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}remove(){for(const e of walk(this))e.isConnected=false;}focus(){}
}
function walk(e){return [e,...e.children.flatMap(c=>c instanceof E?walk(c):[])];}
const versions=JSON.parse(fs.readFileSync(process.argv[2],'utf8')).versions,results=[];
const changes={
 room_id:state=>{state.groom='room-B';state.gst.room={...state.gst.room,room_id:'room-B'};},
 room_round:state=>{state.gst.room.round+=1;},room_object:state=>{state.gst.room={...state.gst.room};},
 token:state=>{state.token='SYNTHETIC_OTHER_LOGIN';},uid:state=>{state.uid=8;},
 room_game:state=>{state.gst.room.game='blackjack';},room_members:state=>{state.gst.room.players=[8];},
 spectator:state=>{state.gst.room.spectators=[7];},room_ended:state=>{state.gst.room.status='ended';},
 public_frame:state=>{state.gst.state={...state.gst.state};},private_frame:state=>{state.gpriv={...state.gpriv};},
 turn_in_place:state=>{state.gst.state.current_uid=8;},phase_in_place:state=>{state.gst.state.status='round_end';},
 detached:(_state,box)=>{walk(box).find(e=>e.className.split(' ').includes('cu-table')).remove();},
 transient_render:()=>{}
};
for(const version of versions){const rows=[];
 for(const kind of ['play','draw','wild-color'])for(const scenario of ['normal',...Object.keys(changes)]){
  const s={game:'uno',status:'playing',players:[7,8],current_uid:7,top:'红2',top_color:'red',hand_counts:{7:2,8:2},scores:{7:0,8:0},deck_remaining:90};
  const pv={hand:['红7','万能'],hand_ids:[7,100],playable_ids:[7,100]},state={uid:7,token:'SYNTHETIC_LOGIN',groom:'room-A',gst:{room:{game:'uno',room_id:'room-A',round:1,players:[7,8],spectators:[],status:'playing'},state:s},gpriv:pv};
  if(scenario==='transient_render')state.groom='room-B';
  const box=new E('main'),sent=[],document={createElement:tag=>new E(tag)};
  new Function('box','s','state','gnick','gameAPI','document',version.js)(box,s,state,u=>'合成'+u,(_op,body)=>sent.push(body),document);
  let control=walk(box).find(e=>kind==='draw'?e.dataset.action==='draw':e.dataset.cardId===(kind==='play'?'7':'100'));
  assert.ok(control,kind+' control missing');
  if(kind==='wild-color'){control.onclick();control=walk(box).find(e=>e.dataset.color==='blue');
   // A transient render is disabled before any picker can open.
   if(!control&&scenario==='transient_render'){rows.push({kind,scenario,sent:[]});continue;}assert.ok(control,'color picker missing');}
  if(scenario!=='normal'&&scenario!=='transient_render')changes[scenario](state,box);
  control.onclick();rows.push({kind,scenario,sent});
  if(scenario==='normal')assert.equal(sent.length,1,'positive callback must send');
  else if(version.require_blocked)assert.equal(sent.length,0,kind+' stale callback fired: '+scenario);
 }
 results.push({sha:version.sha,normal_sends:rows.filter(r=>r.scenario==='normal').length,
  stale_cases:rows.filter(r=>r.scenario!=='normal').length,stale_sends:rows.filter(r=>r.scenario!=='normal'&&r.sent.length).length,rows});
}
const report={results};if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(report,null,2));console.log(JSON.stringify(report));
