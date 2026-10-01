"""Execute production Web functions with controlled browser/network callbacks."""
import json
import re
import shutil
import subprocess

from web import PAGE


def _function(name):
    match = re.search(r"^function " + re.escape(name) + r"\(", PAGE, re.M)
    if match is None:
        return ""
    start = match.start()
    i = PAGE.index("{", start)
    depth, quote = 0, None
    while i < len(PAGE):
        ch = PAGE[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif PAGE.startswith("//", i):
            i = PAGE.index("\n", i)
            continue
        elif PAGE.startswith("/*", i):
            i = PAGE.index("*/", i) + 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return PAGE[start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced production function: {name}")


SCRIPT = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const checks={};
function setup(){
  const dom=new Map(),sockets=[],timers=new Map(),statuses=[];
  function element(id){
    if(!dom.has(id))dom.set(id,{style:{display:id==='main'?'flex':'none'},value:'',innerHTML:'',
      classList:{add(){},remove(){},toggle(){}},addEventListener(){},appendChild(){},remove(){dom.delete(id)}});
    return dom.get(id);
  }
  for(const id of ['login','main','pwd','npwd','msgs','gpanel','globby','games'])element(id);
  const state={token:'old',uid:1,nick:'synthetic',es:null,esRetry:null,groom:'old-room',gst:{},gpriv:{},
    glog:['old'],grooms:[],gmeta:{},gleft:{},roster:[],groups:[],convos:[],unread:{},drafts:{}};
  let reply=()=>Promise.reject(new Error('synthetic temporary network loss'));
  const context={state,URL,location:{href:'http://127.0.0.2:12345/',origin:'http://127.0.0.2:12345'},
    document:{getElementById:element},$:s=>element(s.slice(1)),esc:String,
    EventSource:class{constructor(url){this.url=url;this.closed=false;sockets.push(this)}close(){this.closed=true}},
    setTimeout:fn=>{const id=timers.size+1;timers.set(id,fn);return id},clearTimeout:id=>timers.delete(id),
    showStatus:s=>statuses.push(s),fetch:(...args)=>reply(...args),renderLobby(){}};
  context.window=context;
  vm.createContext(context);vm.runInContext(input.code,context);
  if(typeof context.installSessionFetch==='function')context.installSessionFetch();
  return{context,state,dom,sockets,timers,statuses,setReply:fn=>reply=fn};
}
async function flush(){await new Promise(resolve=>setImmediate(resolve))}
async function main(){
  let e=setup();e.context.openStream();let old=e.state.es;
  old.onmessage({data:JSON.stringify({t:'error',code:'kicked',text:'synthetic kick'})});
  checks.kicked_returns_to_manual_login=e.state.token===null&&e.state.uid===0&&old.closed
    &&e.dom.get('main').style.display==='none'&&e.dom.get('login').style.display==='';
  old.onmessage({data:JSON.stringify({t:'welcome',uid:1})});old.onerror();await flush();
  checks.old_sse_cannot_revive_auth=e.state.token===null&&e.timers.size===0;
  e=setup();e.setReply(()=>Promise.resolve({status:401,json:async()=>({ok:false})}));
  await e.context.fetch('/api/send');
  checks.protected401_ends_current_auth=e.state.token===null;
  e=setup();e.setReply(()=>Promise.resolve({status:500}));await e.context.fetch('/api/send');
  checks.http500_preserves_auth=e.state.token==='old';
  e=setup();e.setReply(()=>Promise.resolve({status:401}));
  await e.context.fetch('/api/login');await e.context.fetch('/api/meta');
  await e.context.fetch('https://example.invalid/api/send');
  checks.public_and_external401_preserve_auth=e.state.token==='old';
  e=setup();e.setReply(()=>Promise.resolve({status:401}));await e.context.fetch('/api/packcover');
  checks.packcover401_is_protected=e.state.token===null;
  e=setup();e.setReply(()=>Promise.resolve({status:401}));await e.context.fetch('/api/sticker/foo');
  checks.public_sticker401_preserves_auth=e.state.token==='old';
  e=setup();let resolve;e.setReply(()=>new Promise(r=>resolve=r));
  const pending=e.context.fetch('/api/send');e.state.token='fresh';e.state.uid=2;
  resolve({status:401});await pending;
  checks.old401_does_not_clear_fresh_auth=e.state.token==='fresh'&&e.state.uid===2;
  e=setup();let logoutDone;e.setReply(()=>new Promise(r=>logoutDone=r));
  e.context.logout();e.state.token='fresh';e.state.uid=2;
  logoutDone({status:401,json:async()=>({ok:false})});await flush();
  checks.old_logout401_does_not_clear_fresh_auth=e.state.token==='fresh'&&e.state.uid===2;
  e=setup();e.context.openStream();old=e.state.es;
  e.setReply(()=>Promise.resolve({status:401,json:async()=>({ok:false})}));old.onerror();await flush();
  checks.sse401_stops_retry_and_returns_login=e.state.token===null&&old.closed&&e.timers.size===0;
  e=setup();e.context.openStream();old=e.state.es;
  e.setReply(()=>Promise.resolve({status:200,json:async()=>({ok:true})}));old.onerror();await flush();
  const reconnect=e.timers.get(e.state.esRetry);if(reconnect)reconnect();
  checks.valid_session_keeps_normal_reconnect=e.sockets.length===2&&e.state.token==='old';
  e=setup();e.context.openStream();old=e.state.es;old.onerror();await flush();
  checks.network_failure_keeps_auth_and_retry=e.state.token==='old'&&e.timers.size===1;
  e=setup();e.context.openStream();old=e.state.es;let finish;
  e.setReply(()=>new Promise(r=>finish=r));old.onerror();
  e.state.token='fresh';e.context.openStream();const fresh=e.state.es;
  if(finish)finish({status:401,json:async()=>({ok:false})});await flush();
  checks.old_probe_does_not_close_new_stream=e.state.token==='fresh'&&e.state.es===fresh&&!fresh.closed;
  console.log(JSON.stringify({checks,failures:Object.entries(checks).filter(([,v])=>!v).map(([k])=>k)}));
  if(Object.values(checks).some(v=>!v))process.exitCode=1;
}
main().catch(error=>{console.error(error);process.exitCode=1});
"""


def test_production_web_kick_and_auth_failure_callbacks(tmp_path):
    node = shutil.which("node")
    assert node is not None, "production JavaScript validation requires Node"
    source = "\n".join(_function(name) for name in
                       ("leaveLogin", "logout", "openStream", "renderGames", "closeLobby", "installSessionFetch"))
    data = tmp_path / "production-functions.json"
    script = tmp_path / "probe.cjs"
    data.write_text(json.dumps({"code": source}), encoding="utf-8")
    script.write_text(SCRIPT, encoding="utf-8")
    result = subprocess.run([node, str(script), str(data)], capture_output=True,
                            text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["failures"] == []
    assert len(report["checks"]) == 13
