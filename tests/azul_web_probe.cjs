// Exercise the production package renderer with a synthetic DOM and deferred HTTP.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {js,snapshot}=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.style={};this.listeners={};this.parent=null;this._text='';this.disabled=false;
    this.classList={add:(...cs)=>this.classes(...cs),remove:(...cs)=>this.classes(...cs.map(c=>'-'+c)),
      contains:c=>this.className.split(' ').includes(c),toggle:(c,on)=>this.classes(on?c:'-'+c)};
  }
  classes(...cs){let all=new Set(this.className.split(' ').filter(Boolean));for(const c of cs){if(c[0]==='-')all.delete(c.slice(1));else all.add(c)}this.className=[...all].join(' ');}
  get className(){return this.attrs.class||''}set className(c){this.attrs.class=c}
  setAttribute(k,v){this.attrs[k]=String(v)}getAttribute(k){return this.attrs[k]??null}
  get dataset(){return Object.fromEntries(Object.entries(this.attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5),v]))}
  get isConnected(){return this===root||!!(this.parent&&this.parent.isConnected)}
  appendChild(e){e.parent=this;this.children.push(e);return e}append(...es){es.forEach(e=>this.appendChild(e))}
  after(e){e.parent=this.parent;this.parent.children.splice(this.parent.children.indexOf(this)+1,0,e)}
  contains(e){return this===e||this.children.some(c=>c.contains(e))}
  set textContent(s){this._text=String(s);this.children=[]}get textContent(){return this._text+this.children.map(c=>c.textContent).join('')}
  set innerHTML(html){this._html=html;this.children.forEach(c=>c.parent=null);this.children=[];let stack=[this];
    for(const m of html.matchAll(/<\/?[\w-]+\b[^>]*>|[^<]+/g)){
      const t=m[0];if(t.startsWith('</')){stack.pop();continue}if(!t.startsWith('<')){stack.at(-1)._text+=t;continue}
      const e=new Element(t.match(/^<([\w-]+)/)[1]);
      for(const a of t.matchAll(/([\w-]+)=(?:'([^']*)'|"([^"]*)")/g))e.setAttribute(a[1],a[2]??a[3]);
      stack.at(-1).appendChild(e);if(!['img','br','input'].includes(e.tagName))stack.push(e);
    }
  }get innerHTML(){return this._html||''}
  matches(sel){return sel[0]==='.'?this.classList.contains(sel.slice(1)):sel[0]==='['?this.getAttribute(sel.slice(1,-1))!==null:false}
  querySelectorAll(sel){return this.children.flatMap(c=>[...(sel.split(',').some(s=>c.matches(s))?[c]:[]),...c.querySelectorAll(sel)])}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null}
  closest(sel){return this.matches(sel)?this:this.parent&&this.parent.closest(sel)}
  addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)}
  fire(k,extra={}){const e={target:this,preventDefault(){},...extra};let p=this;while(p){if(k==='click'&&p.onclick)p.onclick(e);for(const fn of p.listeners[k]||[])fn(e);p=p.parent}}
  click(){if(!this.disabled)this.fire('click')}
  setPointerCapture(){}
}
let root=new Element('root'),hit=null,requests=[],respond=async()=>({ok:true});
const state={uid:1,token:'synthetic-token',groom:'az-1'};
const ctx={state,document:{createElement:tag=>new Element(tag),elementFromPoint:()=>hit},
  BG:{},bgImg:()=>'',esc:String,gnick:u=>'P'+u,gTitle:()=>new Element('h3'),GRENDER:{},setTimeout,
  gameAPI:async(op,args)=>{requests.push({op,...args});return respond(op,args)}};
vm.createContext(ctx);vm.runInContext(js,ctx);
const clone=x=>JSON.parse(JSON.stringify(x));
let currentSnapshot;
function paint(s=currentSnapshot,reset=false,privateOnly=false){
  if(reset){delete state.azulMove;state.uid=1;state.token='synthetic-token';state.groom='az-1';requests=[];respond=async()=>({ok:true})}
  currentSnapshot=privateOnly?state.gst.state:clone(s);
  if(!privateOnly)state.gst={room:{room_id:state.groom,game:'azul',status:'playing',round:1},state:currentSnapshot};
  root.children.forEach(c=>c.parent=null);root.children=[];const box=root.appendChild(new Element('div'));ctx.GRENDER.azul(box,currentSnapshot);
  return root.querySelector('.azgrid');
}
function source(src,col){return root.querySelectorAll('[data-azsrc]').find(t=>t.dataset.azsrc===String(src)&&t.dataset.azcol===col)}
function row(r){return root.querySelectorAll('[data-azdrop]').find(t=>+t.dataset.azdrop===r)}
const tick=()=>new Promise(r=>setImmediate(r));
const actions=()=>clone(requests.filter(r=>r.op==='action').map(r=>r.action));
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
(async()=>{
  paint(snapshot,true);source(0,'r').click();assert.equal(actions().length,0);
  assert.match(root.querySelector('.aztip').textContent,/红色 3 块/);
  for(const [r,reason] of [[0,'已满'],[1,'颜色不符'],[2,'墙上已有此色']]){
    assert.equal(row(r).getAttribute('aria-disabled'),'true');assert.match(row(r).textContent,new RegExp(reason));row(r).click();
  }
  assert.equal(actions().length,0);assert.match(row(3).textContent,/入行 2 · 溢出 1/);assert.match(row(4).textContent,/入行 3 · 溢出 0/);
  source(1,'b').click();assert.match(root.querySelector('.aztip').textContent,/蓝色 1 块/);
  root.querySelector('.azactions').children[0].click();assert.equal(state.azulMove.pick,null);assert.equal(actions().length,0);
  source('center','r').click();assert.match(root.querySelector('.aztip').textContent,/先手标记/);
  assert.equal(root.querySelector('.azfloor').querySelectorAll('[data-azsrc]').length,0);
  row(-1).click();await tick();assert.deepEqual(actions(),[{op:'take',src:'center',col:'r'},{op:'floor'}]);
  const centralActions=clone(actions());

  // take SSE and a private-state repaint arrive before its HTTP response; one place follows.
  paint(snapshot,true);const take=defer(),place=defer();respond=(op,a)=>a.action.op==='take'?take.promise:place.promise;
  source(0,'r').click();row(3).click();row(3).click();assert.equal(actions().length,1);
  const held=clone(snapshot);held.pending=['r','r','r'];held.offers[0]=[];paint(held);paint(held);row(4).click();
  assert.equal(actions().length,1);take.resolve({ok:true});await tick();assert.deepEqual(actions(),[{op:'take',src:'0',col:'r'},{op:'place',row:3}]);
  row(-1).click();assert.equal(actions().length,2);const done=clone(held);done.pending=null;done.turn_uid=2;paint(done);place.resolve({ok:true});await tick();
  const tapActions=clone(actions());

  // Delayed SSE: HTTP success is enough to continue, but does not unlock repeated input.
  paint(snapshot,true);source(0,'r').click();row(4).click();await tick();row(4).click();assert.equal(actions().length,2);

  // A refreshed client with server pending skips take entirely and can use floor.
  paint(held,true);assert.equal(source(1,'b').disabled,true);row(-1).click();await tick();assert.deepEqual(actions(),[{op:'floor'}]);
  const floorActions=clone(actions());

  // A rejected take must never be followed by place, and a rejected place can be resumed.
  for(const failedOp of ['take','place']){
    paint(snapshot,true);respond=async(op,a)=>({ok:op==='sync'||a.action.op!==failedOp});
    source(0,'r').click();row(3).click();await tick();
    assert.equal(actions().length,failedOp==='take'?1:2);assert.equal(state.azulMove.recover,true);
    assert.ok(requests.some(r=>r.op==='sync'));
  }

  // Every async continuation is bound to the captured room/session and game instance.
  for(const mutate of [()=>state.groom='other-room',()=>state.uid=2,()=>state.token='new-token',
    ()=>state.gst.room.room_id='other-room',()=>state.gst.room.round++,()=>state.gst.state.round++,()=>state.gst.room.status='ended',
    ()=>state.gst.state.turn_uid=2,()=>state.gst.state.winner_uid=2]){
    paint(snapshot,true);const waiting=defer();respond=()=>waiting.promise;
    source(0,'r').click();row(3).click();mutate();waiting.resolve({ok:true});await tick();assert.equal(actions().length,1);
    assert.equal(requests[0].room_id,'az-1');
  }

  // Lost take reply: sync, then place the authoritative pending without taking again.
  paint(snapshot,true);respond=(op)=>op==='sync'?Promise.resolve({ok:true}):Promise.reject(new Error('lost reply'));
  source(0,'r').click();row(3).click();await tick();assert.equal(actions().length,1);assert.ok(requests.some(r=>r.op==='sync'));
  row(3).click();assert.equal(actions().length,1); // locked until a new public snapshot
  paint(snapshot,false,true);row(3).click();assert.equal(actions().length,1); // private-only redraw is not a sync
  paint(held);respond=async()=>({ok:true});row(3).click();await tick();assert.equal(actions().length,2);assert.equal(actions()[1].op,'place');

  // Mouse threshold and drop hit testing still execute the same take/place pair.
  let grid=paint(snapshot,true),t=source(0,'r');hit=row(3);
  t.fire('pointerdown',{pointerType:'mouse',button:0,clientX:10,clientY:10,pointerId:1});
  grid.fire('pointermove',{clientX:30,clientY:40,pointerId:1});grid.fire('pointerup',{clientX:30,clientY:40,pointerId:1});await tick();
  assert.deepEqual(actions(),tapActions);const dragActions=clone(actions());
  paint(snapshot,true);state.uid=3;paint(snapshot);source(0,'r').click();
  assert.equal(root.querySelectorAll('[data-azdrop]').length,0);assert.equal(actions().length,0);
  const fullFloor=clone(snapshot);fullFloor.marker_uid=1;fullFloor.floor['1']=7;fullFloor.floor_tiles={'1':Array(7).fill('r')};
  paint(fullFloor,true);assert.equal(root.querySelectorAll('.azfirst-marker').length,1);
  assert.equal(root.querySelector('.azfloor').querySelectorAll('.azfirst-marker').length,0);
  const markerFloor=clone(fullFloor);markerFloor.floor['1']=5;markerFloor.floor_tiles={'1':Array(4).fill('r')};
  paint(markerFloor,true);assert.equal(root.querySelector('.azfloor').querySelectorAll('.azfirst-marker').length,1);
  console.log(JSON.stringify({tapActions,dragActions,centralActions,floorActions,previews:true,pending:true,contextGuards:true,recovery:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
