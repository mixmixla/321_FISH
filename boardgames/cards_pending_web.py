"""Shared in-memory packet latch for physical card renderers, never persisted."""

CARDS_PENDING_JS = r"""
function cardPendingFor(game, context){
  let namespace=state._physicalCardPending;
  if(!namespace||!(namespace.frames instanceof WeakMap))namespace=state._physicalCardPending={frames:new WeakMap()};
  let records=namespace.frames.get(context.publicFrame);
  if(!records){records=[];namespace.frames.set(context.publicFrame,records);}
  // Cosmetic wrappers and DOM roots are deliberately excluded from the key.
  // A rotated login token cannot unlock the same real account and frame.
  let entry=records.find(r=>r.game===game&&r.uid===context.uid&&r.roomId===context.roomId
    &&r.round===context.round&&r.privateFrame===context.privateFrame);
  if(!entry){entry={game,uid:context.uid,roomId:context.roomId,round:context.round,
    privateFrame:context.privateFrame,pending:false,attempt:0,views:[]};records.push(entry);}
  function refresh(){
    entry.views=entry.views.filter(v=>v.root.isConnected);
    for(const view of entry.views){
      const valid=view.valid();view.controls=view.controls.filter(c=>c.element.isConnected);
      for(const control of view.controls)control.element.disabled=!control.enabled||entry.pending||!valid;
    }
  }
  return {
    isPending:()=>entry.pending,
    attach(root,valid){
      entry.views=entry.views.filter(v=>v.root.isConnected);
      const view={root,valid,controls:[]};entry.views.push(view);
      return {watch(element,enabled){view.controls.push({element,enabled:!!enabled});element.disabled=!enabled||entry.pending;},refresh};
    },
    submit(request){
      if(entry.pending)return false;
      entry.pending=true;const attempt=++entry.attempt;refresh();
      const rejected=()=>{if(entry.attempt===attempt){entry.pending=false;refresh();}};
      let result;
      try{result=request();}catch(_error){rejected();return true;}
      if(result&&typeof result.then==='function'){
        Promise.resolve(result).then(reply=>{if(reply&&reply.ok===false)rejected();},()=>{
          // A lost response may follow a successful action; wait for a new frame.
        });
      }else if(result&&result.ok===false)rejected();
      return true;
    }
  };
}
"""
