const assert=require("node:assert/strict"), fs=require("node:fs"), vm=require("node:vm");
const fixture=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.style={setProperty(k,v){this[k]=v;}};}
  append(...items){this.children.push(...items);}
  setAttribute(k,v){this.attrs[k]=String(v);}
  click(){if(!this.disabled&&this.onclick)this.onclick();}
}
const element=tag=>new Element(tag);
const document={createElement:element,createElementNS:(_ns,tag)=>element(tag)};
const s=fixture.state,uid=s.players[0],room={room_id:"rail-1",game:"tielu",status:"playing",players:s.players,round:1};
const state={groom:room.room_id,uid,token:"synthetic",gst:{room,state:s},gpriv:fixture.private};
let box,api=[];
const ctx=vm.createContext({document,state,RAIL_TICKET_COUNT:fixture.ticketCount,BG:{tielu_travel:"map"},gnick:u=>"P"+u,
  gameAPI:(method,args)=>{api.push([method,args]);return Promise.resolve({ok:true});},renderGamePanel:render});
const table=vm.runInContext(fixture.js+";RailTable",ctx);
function render(){box=element("main");table.paint(box,state.gst.state);}
function all(node){return [node,...node.children.flatMap(all)];}
function find(f){const v=all(box).find(f);assert.ok(v);return v;}
function routeEl(route){return find(e=>e.attrs["data-tla"]===String(route.a)&&e.attrs["data-tlb"]===String(route.b));}
function controls(cls){return all(box).filter(e=>(e.className||"").split(" ").includes(cls));}
render();
assert.equal(controls("rail-coach").length,5);
assert.equal(controls("rail-contract").length,2);
assert.equal(controls("rail-postmark").length,4);
for(const rt of s.routes)assert.equal(all(routeEl(rt)).filter(e=>e.attrs.class==="rail-car").length,rt.length);
controls("rail-contract")[0].click();assert.equal(all(box).filter(e=>e.attrs["data-highlight"]==="true").length,2);
assert.equal(api.length,0);
const affordable=s.routes.find(r=>fixture.private.hand[r.color]>=r.length);assert.ok(affordable);
const expensive=s.routes.find(r=>fixture.private.hand[r.color]<r.length);assert.ok(expensive);
routeEl(expensive).click();assert.equal(controls("rail-claim")[0].disabled,true);
routeEl(affordable).click();assert.equal(api.length,0);const pay=controls("rail-claim")[0];assert.equal(pay.disabled,false);
const oldState=state.gst.state;state.gst.state={...s};pay.click();assert.equal(api.length,0);
state.gst.state=oldState;
state.token="new-token";pay.click();assert.equal(api.length,0);state.token="synthetic";
room.round=2;pay.click();assert.equal(api.length,0);room.round=1;
state.gst.room={...room};pay.click();assert.equal(api.length,0);state.gst.room=room;
pay.click();pay.click();assert.equal(api.length,1);
assert.deepEqual(JSON.parse(JSON.stringify(api[0])),["action",{room_id:"rail-1",action:{op:"claim",a:affordable.a,b:affordable.b}}]);
// Real SSE clears the private frame on 'ended'. Keep only this player's prior
// ticket identities and use final publicly owned rails to compute the marks.
const goal=fixture.private.tickets[0];
const via=Object.keys(s.cities).map(Number).find(city=>city!==goal.a&&city!==goal.b);
state.gpriv=null;
state.gst.room={...room,status:"ended"};
state.gst.state={...s,winner_uid:uid,routes:[{a:goal.a,b:via,length:2,claimed:uid},{a:via,b:goal.b,length:3,claimed:uid}],
 final_scores:{[uid]:{route:5,ticket_bonus:goal.v,ticket_penalty:0,total:5+goal.v}}};
render();assert.ok(controls("rail-end").length);assert.equal(controls("rail-deck").length,0);assert.equal(controls("rail-contract").length,2);
assert.ok(controls("rail-contract")[0].className.includes("is-connected"));
state.uid=999;state.gpriv=fixture.private;state.gst.room=room;state.gst.state=s;render();
assert.equal(controls("rail-coach").length,0);assert.equal(controls("rail-contract").length,0);
assert.ok(controls("rail-deck").every(e=>e.disabled));
table.reset();state.uid=uid;state.gpriv=null;state.gst.state={...s,winner_uid:uid};render();
assert.equal(controls("rail-contract").length,0);
console.log("rail map, real car counts, fare, two private stations, spectator and guarded confirmation OK");
