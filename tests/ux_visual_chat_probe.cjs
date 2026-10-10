// Behavior of the actual embedded functions; DOM fixtures contain no real data.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','web.py'),'utf8');
const script=source.split('\n<script>')[1].split('</script>')[0];
new vm.Script(script);
function declaration(name){
 const start=script.indexOf('function '+name+'(');assert.ok(start>=0,name);
 for(let end=script.indexOf('}',start);end>=0;end=script.indexOf('}',end+1)){
  const value=script.slice(start,end+1);try{new vm.Script('('+value+')');return value}catch{}
 }throw Error(name);
}
const buttons=['chat','game','moments'].map(key=>({dataset:{uxNav:key},attrs:{},on:false,
 classList:{toggle(name,value){buttons.find(b=>b.dataset.uxNav===key).on=value}},
 setAttribute(name,value){this.attrs[name]=value},removeAttribute(name){delete this.attrs[name]}}));
const nodes={};
const element=()=>({appendChild(){},remove(){delete nodes['#'+this.id]}});
const storage=new Map(), attributes={};
const ctx={state:{groom:null,glog:[]},document:{querySelectorAll:()=>buttons,
 documentElement:{setAttribute:(k,v)=>attributes[k]=v,removeAttribute:k=>delete attributes[k]},
 createElement:element,body:{appendChild(node){nodes['#'+node.id]=node}}},
 $:key=>nodes[key],localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 gameAPI(){},renderGamePanel(){}};
vm.createContext(ctx);
for(const name of ['uxSelectNavigation','openGamePanel','hideGamePanel','closeLobby','webThemeMode','applyWebTheme','setTheme','toggleTheme','setThemeFamily'])vm.runInContext(declaration(name),ctx);
ctx.uxSelectNavigation('chat');assert.equal(buttons[0].on,true);
ctx.closeLobby();ctx.openGamePanel('synthetic-room');
assert.equal(buttons[1].on,true);assert.equal(buttons[1].attrs['aria-current'],'page');assert.equal(buttons[0].on,false);
ctx.hideGamePanel();assert.equal(buttons[0].on,true);assert.equal(buttons[1].attrs['aria-current'],undefined);
assert.equal(ctx.webThemeMode(),'mist');ctx.applyWebTheme();assert.equal(attributes['data-theme'],'mist');
ctx.toggleTheme();assert.equal(ctx.webThemeMode(),'mist-dark');ctx.toggleTheme();assert.equal(ctx.webThemeMode(),'mist');
storage.set('web_theme','light');assert.equal(ctx.webThemeMode(),'light');
ctx.setThemeFamily('mist');assert.equal(ctx.webThemeMode(),'mist');
console.log(JSON.stringify({navigation_room_open_close:true,aria_current:true,mist_pair:true,legacy_preference:true,full_script_syntax:true}));
