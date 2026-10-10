// Behavioral checks for actual embedded PAGE functions. Does not replace browser/EXE QA.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', 'web.py'), 'utf8');
const script = source.split('\n<script>')[1].split('</script>')[0];
new vm.Script(script); // Full page syntax, not only the extracted functions.
function declaration(name) {
  const start = script.indexOf('function ' + name + '(');
  assert.ok(start >= 0, name);
  for (let end = script.indexOf('}', start); end >= 0; end = script.indexOf('}', end + 1)) {
    const value = script.slice(start, end + 1);
    try { new vm.Script('(' + value + ')'); return value; } catch {}
  }
  throw Error('Incomplete function: ' + name);
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture() {
  const calls = [], pending = [], timers = [], messages = [], readers = [];
  const text = {value: '', focus() {}};
  const elements = {'#text': text, '#silent': {checked: false}, '#disguise': {value: ''},
    '#headTitle':{textContent:''},'#apanel':{style:{}}};
  const state = {token:'synthetic', uid:1, cur:{type:'private',uid:2}, drafts:{}, unread:{}, editSeq:null};
  const ctx = {state, console, URLSearchParams, clearTimeout() {},
    setTimeout: fn => {timers.push(fn); return timers.length;},
    $: key => elements[key], channelRO: () => false, richSegs: t => [],
    showStatus: t => calls.push({status:t}), growTextArea() {}, cancelReply() {}, cancelEdit() {},
    closeSide(){},channelName:()=>'',unmarkConvo(){},renderConvos(){},updateTitle(){},syncGroups(){},
    renderHeadActions(){},clearMsgs(){},renderRoster(){},renderGroups(){},applyRO(){},closePanel(){},
    document:{querySelectorAll:()=>[],querySelector:()=>({classList:{add(){}}})},
    fetch: (url, options) => {const call={url, body:options?.body ? JSON.parse(options.body):null};calls.push(call);
      return new Promise(resolve => pending.push(data=>resolve({json:async()=>data})));},
    addMsg: msg => messages.push(msg), renderRead() {}, refreshQuoteBadges() {}, markReadDelay() {},
    FileReader: class {constructor(){readers.push(this);} readAsDataURL(){}}
  };
  vm.createContext(ctx);
  for (const name of ['uxSelectNavigation','convKey','discardGroupDraft','writeDraft','pushDraft','applyDraft','send','sendFile','uploadSend','loadHistory','sendSticker','openGroup','convoKey','selectChannel','refreshPanel','groupApi'])
    vm.runInContext(declaration(name),ctx);
  return {ctx,state,text,calls,pending,timers,messages,readers};
}
(async()=>{
  let f=fixture();
  assert.equal(f.ctx.convKey(),'private:1:2');
  f.state.cur={type:'group',gid:'g1'};assert.equal(f.ctx.convKey(),'group:g1');
  f.state.cur={type:'public'};assert.equal(f.ctx.convKey(),'public');

  f=fixture();f.text.value='private draft';f.ctx.pushDraft();
  f.state.cur={type:'public'};f.text.value='public draft';f.timers[0]();await tick();
  assert.equal(f.calls[0].body.to,2);assert.equal(f.calls[0].body.text,'private draft');
  assert.equal(f.state.drafts['private:1:2'],'private draft');
  f.state.drafts.public='separate';f.ctx.applyDraft(true);assert.equal(f.text.value,'separate');

  f=fixture();f.text.value='to private';f.ctx.pushDraft();f.ctx.send();
  f.state.cur={type:'public'};f.text.value='keep public';f.state.drafts.public='keep public';
  f.pending[0]({ok:true});await tick();
  assert.equal(f.text.value,'keep public');assert.equal(f.state.drafts.public,'keep public');
  assert.equal(f.calls[0].body.to,2);assert.equal(f.calls[1].body.to,2);assert.equal(f.calls[1].body.text,'');

  f=fixture();f.text.value='first';f.ctx.send();f.text.value='new text';f.ctx.pushDraft();
  f.pending[0]({ok:true});await tick();assert.equal(f.text.value,'new text');
  assert.equal(f.state.drafts['private:1:2'],'new text');

  f=fixture();f.ctx.uploadSend({name:'synthetic.txt'},'file');
  f.state.cur={type:'public'};f.readers[0].result='data:text/plain;base64,YQ==';f.readers[0].onload();
  f.pending[0]({ok:true,file:{fid:'synthetic'}});await tick();
  assert.equal(f.calls[1].body.channel,'private');assert.equal(f.calls[1].body.to,2);

  f=fixture();f.ctx.uploadSend({name:'synthetic.txt'},'file');f.state.token='different';
  f.readers[0].result='data:text/plain;base64,YQ==';f.readers[0].onload();assert.equal(f.calls.length,0);

  f=fixture();f.ctx.loadHistory({...f.state.cur});f.state.cur={type:'public'};f.ctx.loadHistory({...f.state.cur});
  f.pending[1]({ok:true,msgs:[{text:'public'}]});await tick();
  f.pending[0]({ok:true,msgs:[{text:'stale private'}]});await tick();
  assert.deepEqual(f.messages.map(m=>m.text),['public']);

  f=fixture();f.ctx.channelRO=()=>true;f.ctx.sendSticker('smile');f.ctx.uploadSend({name:'x'},'file');f.ctx.send();
  assert.equal(f.calls.filter(c=>c.url).length,0);

  f=fixture();f.ctx.writeDraft(f.state.cur,'old',f.state.token);
  f.ctx.writeDraft(f.state.cur,'',f.state.token);await tick();
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].body.text,'old');
  f.pending[0]({ok:true});await tick();
  assert.equal(f.calls.length,2);assert.equal(f.calls[1].body.text,'');

  f=fixture();f.text.value='repeat';f.ctx.pushDraft();f.ctx.send();
  f.text.value='different';f.ctx.pushDraft();f.text.value='repeat';f.ctx.pushDraft();
  f.pending[0]({ok:true});await tick();assert.equal(f.text.value,'repeat');
  assert.equal(f.state.drafts['private:1:2'],'repeat');

  f=fixture();f.ctx.openGroup({gid:'synthetic'});f.state.navigationRequest++;
  f.pending[0]({ok:true,member:true});await tick();assert.equal(f.state.cur.type,'private');

  f=fixture();f.state.cur={type:'public'};f.state.unread['private:1:2']=7;
  let enteredUnread;f.ctx.loadHistory=(c,n)=>{enteredUnread=n;};
  f.ctx.selectChannel({type:'private',uid:2});assert.equal(enteredUnread,7);
  assert.equal(f.state.unread['private:1:2'],0);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};
  let fallback;f.ctx.selectChannel=(c,save)=>{fallback={c,save};};f.ctx.refreshPanel();
  assert.equal(f.state.groupAccessPending,'g');
  f.pending[0]({ok:true,member:false});await tick();
  assert.equal(fallback.c.type,'public');assert.equal(fallback.save,false);assert.equal(f.state.meIn.g,false);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};f.ctx.refreshPanel();
  f.state.cur={type:'public'};f.state.navigationRequest=1;f.pending[0]({ok:true,member:false});await tick();
  assert.equal(f.state.cur.type,'public');assert.equal(f.state.meIn.g,true);

  f=fixture();vm.runInContext(declaration('channelRO'),f.ctx);f.ctx.curChannelGroup=()=>({kind:'group'});
  f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};assert.equal(f.ctx.channelRO(),false);
  f.state.groupAccessPending='g';assert.equal(f.ctx.channelRO(),true);
  f.state.groupAccessPending=null;f.state.meIn.g=false;assert.equal(f.ctx.channelRO(),true);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};f.state.groupAccessPending='g';
  f.ctx.writeDraft(f.state.cur,'not allowed while pending',f.state.token);await tick();assert.equal(f.calls.length,0);
  f.state.groupAccessPending=null;f.text.value='old member draft';f.ctx.pushDraft();
  f.ctx.discardGroupDraft('g');f.state.meIn.g=true;f.timers[0]();await tick();
  assert.equal(f.calls.length,0);assert.equal(f.state.drafts['group:g'],undefined);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};
  f.ctx.writeDraft(f.state.cur,'already dispatched',f.state.token);
  f.ctx.writeDraft(f.state.cur,'queued stale',f.state.token);await tick();assert.equal(f.calls.length,1);
  f.ctx.discardGroupDraft('g');f.state.meIn.g=false;f.pending[0]({ok:true});await tick();
  assert.equal(f.calls.length,1);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};f.text.value='old draft';
  f.ctx.pushDraft();f.ctx.groupApi('leave',{gid:'g'});f.state.cur={type:'public'};f.state.navigationRequest=1;
  f.pending[0]({ok:true,groups:[]});await tick();f.timers[0]();await tick();
  assert.equal(f.state.cur.type,'public');assert.equal(f.state.drafts['group:g'],undefined);
  assert.equal(f.calls.filter(c=>c.url==='/api/draft').length,0);

  f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};f.ctx.groupApi('leave',{gid:'g'});
  f.state.navigationRequest=1;f.state.drafts['group:g']='new visit';f.text.value='new visit';
  f.pending[0]({ok:true,groups:[]});await tick();
  assert.equal(f.state.cur.type,'group');assert.equal(f.state.drafts['group:g'],'new visit');
  assert.equal(f.text.value,'new visit');assert.equal(f.state.groupDraftEpoch.g,1);

  for (const detail of [{ok:false},{ok:true,member:false}]) {
    f=fixture();f.state.cur={type:'group',gid:'g'};f.state.meIn={g:true};f.state.drafts['group:g']='old';
    f.ctx.selectChannel=(c,save)=>{assert.equal(save,false);f.state.cur=c;};
    f.ctx.openGroup({gid:'g'});f.pending[0](detail);await tick();
    assert.equal(f.state.cur.type,'public');assert.equal(f.state.meIn.g,false);
    assert.equal(f.state.drafts['group:g'],undefined);assert.equal(f.state.groupDraftEpoch.g,1);
  }
  console.log('PASS: full PAGE syntax + 21 navigation/draft/history/send/upload/group ownership scenarios');
})().catch(e=>{console.error(e);process.exitCode=1;});
