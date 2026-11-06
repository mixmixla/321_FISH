// Run the real lobby functions with synthetic metadata; no browser or user profile.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','web.py'),'utf8');
const script=source.split('\n<script>')[1].split('</script>')[0];
new vm.Script(script);
function declaration(name){
 const start=script.indexOf('function '+name+'(');assert.ok(start>=0,name);
 for(let end=script.indexOf('}',start);end>=0;end=script.indexOf('}',end+1)){
  const code=script.slice(start,end+1);try{new vm.Script('('+code+')');return code}catch{}
 }throw Error(name);
}
const nodes={},calls=[];
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this.value='';this.textContent='';}
 set innerHTML(html){this.html=html;this.children=[];
  for(const match of html.matchAll(/id=['"]([^'"]+)['"]/g))nodes['#'+match[1]]=new Element('fixture');}
 get innerHTML(){return this.html||'';}
 appendChild(child){this.children.push(child);if(child.id)nodes['#'+child.id]=child;
  if(this.tag==='select'&&(child.selected||!this.value))this.value=String(child.value);return child;}
 remove(){delete nodes['#'+this.id];}
 focus(){this.focused=true;}
}
const meta=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
let snapshot={ok:true,games:Object.entries(meta).map(([name,g])=>({name,...g})),rooms:[]};
const ctx={state:{uid:7,gmeta:meta,grooms:[]},GART:{},$:s=>nodes[s],esc:String,
 document:{createElement:tag=>new Element(tag),body:new Element('body')},
 gIcon:()=>'',gArt:()=>'',renderGames(){},uxSelectNavigation(){},openGamePanel(){},
 gameAPI:(op,payload)=>calls.push({op,...payload}),fetch:async()=>({json:async()=>snapshot})};
vm.createContext(ctx);
for(const name of ['gameLobby','closeLobby','renderLobby'])vm.runInContext(declaration(name),ctx);
const cards=()=>nodes['#glGames'].children.flatMap(n=>n.children).filter(n=>n.className==='gcard');
const names=()=>cards().map(n=>n.dataset.game);
function filter(query,players){nodes['#glQuery'].value=query;nodes['#glQuery'].oninput();
 nodes['#glPlayers'].value=players;nodes['#glPlayers'].oninput();}
function create(name){const card=cards().find(n=>n.dataset.game===name);assert.ok(card,name);
 card.children.find(n=>n.className==='gbtn go').onclick();}
(async()=>{
 ctx.gameLobby();await new Promise(setImmediate);
 assert.equal(cards().length,Object.keys(meta).length);
 filter('铁路','4');assert.deepEqual(names(),['tielu']);create('tielu');assert.equal(calls.at(-1).game,'tielu');
 ctx.gameLobby();await new Promise(setImmediate);assert.equal(nodes['#glQuery'].value,'铁路');
 assert.equal(nodes['#glPlayers'].value,'4');assert.deepEqual(names(),['tielu']);
 filter(' TIELU ','2');assert.deepEqual(names(),['tielu']);
 filter('tielu','1');assert.equal(cards().length,0);assert.match(nodes['#glGames'].children[0].textContent,/没有符合/);
 filter('','1');assert.deepEqual(names().sort(),['balatro_solo','go_solo']);create('go_solo');
 ctx.gameLobby();filter('','2');assert.ok(names().includes('gomoku'));assert.ok(!names().includes('rps'));
 create('gomoku');ctx.gameLobby();filter('','4');assert.ok(names().includes('rps'));assert.ok(!names().includes('gomoku'));
 create('rps');ctx.gameLobby();filter('','17');assert.ok(names().includes('spy'));assert.ok(!names().includes('tielu'));
 for(const invalid of ['0','-1','2.5','abc']){filter('',invalid);assert.equal(cards().length,0);}
 filter('铁路','4');ctx.state.grooms=[{room_id:'live-room',game:'gomoku',players:[8],spectators:[],status:'created'}];
 ctx.renderLobby();assert.equal(nodes['#glRooms'].children.length,1);assert.deepEqual(names(),['tielu']);
 nodes['#glRooms'].children[0].children[0].onclick();assert.equal(calls.at(-1).room_id,'live-room');
 ctx.gameLobby();await new Promise(setImmediate);assert.deepEqual(names(),['tielu']);
 nodes['#glClear'].onclick();assert.equal(cards().length,Object.keys(meta).length);
 assert.equal(nodes['#glQuery'].value,'');assert.equal(nodes['#glPlayers'].value,'');
 filter('go','2');const go=cards().find(n=>n.dataset.game==='go');
 go.children.find(n=>n.tag==='select').value='13';create('go');
 assert.equal(calls.at(-1).options.size,13);
 console.log(JSON.stringify({passed:true,created:calls.filter(c=>c.op==='create').map(c=>c.game)}));
})().catch(error=>{console.error(error);process.exitCode=1;});
