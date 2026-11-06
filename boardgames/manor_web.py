"""Betrayal Web presentation: revealed map, ordinary actions and discovery archive."""

WEB_JS = r"""
const ManorWeb = (() => {
  const directions=[['up','北',0,-1,'↑'],['right','东',1,0,'→'],['down','南',0,1,'↓'],['left','西',-1,0,'←']];
  const colors=['#ad464d','#376ab0','#287c60','#a46e20','#8059a5','#277e85'];
  const kindNames={item:'道具',event:'事件',omen:'预兆'};
  function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function point(key){if(typeof key!=='string'||!/^[-]?\d+,[-]?\d+$/.test(key))return null;const p=key.split(',').map(Number);return p.every(Number.isSafeInteger)?p:null;}
  function sprite(kind,name){
    const image=node('div','mn-art');const atlas=(typeof MANOR_ATLASES==='object'&&MANOR_ATLASES[kind])||{};
    const index=(atlas.names||[]).indexOf(name);
    image.setAttribute('role','img');image.setAttribute('aria-label',name);
    if(index<0||!atlas.file||!atlas.cols||!atlas.rows){image.classList.add('mn-art-fallback');image.textContent=name;return image;}
    image.dataset.artKind=kind;image.dataset.artIndex=String(index);
    image.style.backgroundImage='url("/game-art/'+atlas.file+'")';
    image.style.backgroundSize=(atlas.cols*100)+'% '+(atlas.rows*100)+'%';
    image.style.backgroundPosition=(atlas.cols===1?0:index%atlas.cols*100/(atlas.cols-1))+'% '+(atlas.rows===1?0:Math.floor(index/atlas.cols)*100/(atlas.rows-1))+'%';
    return image;
  }
  function paint(box,s){
    const root=node('section','mn-shell');box.appendChild(gTitle('betrayal','山屋惊魂 · 推门探索'));box.appendChild(root);
    const me=state.uid,room=state.gst&&state.gst.room,rooms=s.rooms||{},positions=s.pos||{},seats=s.seats||{};
    const players=s.players||[],alive=s.alive||players.filter(uid=>!(s.dead||[]).includes(uid));
    const mine=players.includes(me)&&room&&(room.players||[]).includes(me);
    const active=()=>!!room&&state.gst&&state.gst.room===room&&state.gst.state===s&&state.uid===me&&room.game==='betrayal'&&room.room_id===state.groom&&room.status==='playing'&&players.includes(me)&&alive.includes(me)&&s.turn_uid===me;
    const context=state.groom+':'+(room&&room.round||0)+':'+me;
    if(!state.manorView||state.manorView.context!==context)state.manorView={context,mode:'local',follow:true,selected:null,count:0};
    const view=state.manorView,discoveries=Array.isArray(s.discoveries)?s.discoveries:[];
    const seat=uid=>seats[uid]==null?uid:seats[uid];
    const who=uid=>seat(uid)+'号 '+gnick(uid);
    const name=key=>(s.room_names||{})[key]||(discoveries.find(d=>d.pos===key)||{}).room||rooms[key]||'未知';
    const actorPos=positions[mine?me:s.turn_uid]||'0,0';
    if(discoveries.length>view.count){view.selected=discoveries[discoveries.length-1].pos;view.pendingReveal=view.selected;view.count=discoveries.length;}
    if(!view.selected||rooms[view.selected]==null)view.selected=rooms[actorPos]!=null?actorPos:Object.keys(rooms)[0];
    const focus=point(view.follow?actorPos:view.focus)||point(actorPos)||[0,0];
    const myPoint=point(positions[me]);let busy=false;
    const actionButtons=[];
    function action(label,value,allowed,cls){
      const button=node('button','gbtn mn-action '+(cls||''),label);button.type='button';button.disabled=!allowed;
      button.onclick=event=>{if(event)event.stopPropagation();if(!allowed||!active()||busy)return;
        if(value.move&&(!(s.steps_left>0)||!myPoint))return;
        if(value.move)view.follow=true;
        busy=true;actionButtons.forEach(b=>b.disabled=true);
        const request=gameAPI('action',{room_id:state.groom,action:value});
        const reset=()=>{busy=false;for(const b of actionButtons)if(b.isConnected)b.disabled=b._mnDisabled;};
        if(request&&typeof request.then==='function')request.then(reset,reset);else reset();
      };
      button._mnDisabled=!allowed;actionButtons.push(button);return button;
    }
    const tools=node('div','mn-tools');root.appendChild(tools);
    function reveal(element){
      if(!element.isConnected)return;
      if(typeof box.getBoundingClientRect==='function'){
        const host=box.getBoundingClientRect(),rect=element.getBoundingClientRect();
        box.scrollTop=Math.max(0,box.scrollTop+rect.top-host.top-tools.offsetHeight-8);
      }else element.scrollIntoView({block:'nearest'});
    }
    const turn=node('div','mn-turn',room&&room.status==='ended'?'本局结束':(({explore:'探索',haunt:'惊魂'}[s.phase]||s.phase||'探索')+' · '+who(s.turn_uid)+' · 剩 '+(s.steps_left||0)+' 步'));tools.appendChild(turn);
    const info=node('div','mn-status','预兆 '+(s.omens||0)+' · 可探索房块 '+(s.tiles_left==null?'未知':s.tiles_left));tools.appendChild(info);
    if(mine&&(s.stats||{})[me]){const own=s.stats[me];tools.appendChild(node('div','mn-status','力量 '+own.might+' · 速度 '+own.speed+' · 理智 '+own.sanity+' · 知识 '+own.knowledge));}
    if(s.haunt)tools.appendChild(node('div','mn-haunt',(s.haunt.scenario||'惊魂降临')+' · 叛徒 '+who(s.haunt.traitor)+' · 出口 '+s.haunt.exit));
    const moves=node('div','mn-moves');tools.appendChild(moves);
    for(const [dir,label,dx,dy,arrow] of directions){
      const key=myPoint?((myPoint[0]+dx)+','+(myPoint[1]+dy)):'';
      const allowed=active()&&s.steps_left>0&&(rooms[key]!=null||s.tiles_left==null||s.tiles_left>0);
      const button=action(arrow+' '+label,{move:dir},allowed);button.dataset.move=dir;moves.appendChild(button);
    }
    const end=action('结束回合',{end:true},active(),'mn-end');end.dataset.end='true';moves.appendChild(end);
    const inventory=mine&&state.gpriv&&Array.isArray(state.gpriv.items)?state.gpriv.items:((s.items||{})[me]||[]);
    if(mine&&(inventory.length||s.phase==='haunt')){
      const extra=node('details','mn-extra');extra.open=!!view.actionsOpen;
      extra.appendChild(node('summary','','道具与对抗 · '+inventory.length+' 件道具'));
      extra.ontoggle=()=>{if(extra.isConnected)view.actionsOpen=extra.open;};
      const bar=node('div','mn-extra-buttons');inventory.forEach(item=>{const b=action('使用 '+item,{use:item},active());b.dataset.use=item;bar.appendChild(b);});
      if(s.phase==='haunt'){
        const here=players.filter(uid=>uid!==me&&alive.includes(uid)&&positions[uid]===positions[me]);
        here.forEach(uid=>{const b=action('攻击 '+who(uid),{attack:uid},active());b.dataset.attack=String(uid);bar.appendChild(b);});
        const traitor=s.haunt&&s.haunt.traitor,exit=s.haunt&&s.haunt.exit;
        const allAtExit=!!exit&&alive.filter(uid=>uid!==traitor).every(uid=>positions[uid]===exit);
        const escape=action('从出口撤离',{escape:true},active()&&me!==traitor&&allAtExit);escape.dataset.escape='true';
        escape.title=me===traitor?'叛徒无法撤离':'所有幸存者到达出口后可撤离';bar.appendChild(escape);
      }
      extra.appendChild(bar);tools.appendChild(extra);
    }
    const navigation=node('div','mn-navigation');root.appendChild(navigation);
    function viewButton(label,handler,chosen){const b=node('button','gbtn mn-view-button',label);b.type='button';b.setAttribute('aria-pressed',String(!!chosen));b.onclick=handler;return b;}
    navigation.appendChild(viewButton('当前位置',()=>{view.follow=true;view.selected=actorPos;renderGamePanel();},view.follow));
    navigation.appendChild(viewButton(view.mode==='local'?'查看全图':'局部视野',()=>{view.mode=view.mode==='local'?'all':'local';view.scroll=null;renderGamePanel();},view.mode==='all'));
    if(s.haunt&&rooms[s.haunt.exit]!=null)navigation.appendChild(viewButton('定位出口',()=>{view.mode='local';view.follow=false;view.focus=s.haunt.exit;view.selected=s.haunt.exit;view.scroll=null;renderGamePanel();},false));
    root.appendChild(node('p','mn-map-hint','点门移动或探索 · 点房间查看发现 · 地图内可滚动'));
    const viewport=node('div','mn-map-viewport');viewport.tabIndex=0;viewport.setAttribute('aria-label','已揭示的山屋地图');root.appendChild(viewport);
    const stage=node('div','mn-stage');viewport.appendChild(stage);
    const known=Object.keys(rooms).map(key=>({key,p:point(key)})).filter(entry=>entry.p);
    const mobile=typeof innerWidth==='number'&&innerWidth<=560,tile=mobile?140:156;
    let x0=focus[0]-1,x1=focus[0]+1,y0=focus[1]-1,y1=focus[1]+1;
    if(view.mode==='all'&&known.length){x0=Math.min(...known.map(e=>e.p[0]))-1;x1=Math.max(...known.map(e=>e.p[0]))+1;y0=Math.min(...known.map(e=>e.p[1]))-1;y1=Math.max(...known.map(e=>e.p[1]))+1;}
    stage.style.width=(x1-x0+1)*tile+'px';stage.style.height=(y1-y0+1)*tile+'px';stage.style.setProperty('--mn-tile',tile+'px');
    viewport.style.height=(mobile?330:430)+'px';
    const occupants={};for(const uid of players){const key=positions[uid];if(key)(occupants[key]||(occupants[key]=[])).push(uid);}
    function select(key){view.selected=key;view.pendingReveal=key;view.focus=key;view.follow=false;view.scroll=null;renderGamePanel();}
    known.forEach(({key,p})=>{
      if(p[0]<x0||p[0]>x1||p[1]<y0||p[1]>y1)return;
      const roomName=name(key),tileNode=node('article','mn-tile');tileNode.dataset.pos=key;
      tileNode.style.left=(p[0]-x0)*tile+'px';tileNode.style.top=(p[1]-y0)*tile+'px';
      tileNode.classList.toggle('mn-current',key===actorPos);tileNode.classList.toggle('mn-selected',key===view.selected);
      const inspect=node('button','mn-room-inspect');inspect.type='button';inspect.setAttribute('aria-label','查看 '+roomName+' '+key);inspect.onclick=()=>select(key);
      inspect.appendChild(sprite('room',roomName));inspect.appendChild(node('strong','mn-room-name',roomName));tileNode.appendChild(inspect);
      const markers=node('div','mn-occupants');(occupants[key]||[]).forEach(uid=>{
        const marker=node('span','mn-seat',String(seat(uid))+'号'+(uid===me?'·你':''));marker.dataset.uid=String(uid);
        marker.style.setProperty('--mn-player',colors[Math.max(0,players.indexOf(uid))%colors.length]);marker.title=who(uid)+(alive.includes(uid)?'':'（阵亡）');
        marker.classList.toggle('mn-dead',!alive.includes(uid));markers.appendChild(marker);
      });tileNode.appendChild(markers);
      if(key===positions[me])for(const [dir,label,dx,dy,arrow] of directions){
        const neighbor=(p[0]+dx)+','+(p[1]+dy),revealed=rooms[neighbor]!=null;
        const allowed=active()&&s.steps_left>0&&(revealed||s.tiles_left==null||s.tiles_left>0);
        const door=action(arrow,{move:dir},allowed,'mn-door mn-door-'+dir);door.dataset.door=dir;
        const description='向'+label+(revealed?'移动至 '+name(neighbor):'开门');door.title=description;door.setAttribute('aria-label',description);tileNode.appendChild(door);
      }
      stage.appendChild(tileNode);
    });
    const restore=()=>{
      if(!viewport.isConnected)return;
      const scrollKey=view.mode+':'+focus.join(',')+':'+Object.keys(rooms).sort().join('|');
      if(view.scroll&&view.scroll.key===scrollKey){viewport.scrollLeft=view.scroll.left;viewport.scrollTop=view.scroll.top;}
      else {
        const visible=known.filter(e=>e.p[0]>=x0&&e.p[0]<=x1&&e.p[1]>=y0&&e.p[1]<=y1);
        let centerX=(focus[0]-x0+.5)*tile,centerY=(focus[1]-y0+.5)*tile;
        if(visible.length){
          const minX=Math.min(...visible.map(e=>e.p[0])),maxX=Math.max(...visible.map(e=>e.p[0]));
          const minY=Math.min(...visible.map(e=>e.p[1])),maxY=Math.max(...visible.map(e=>e.p[1]));
          if((maxX-minX+1)*tile<=viewport.clientWidth&&(maxY-minY+1)*tile<=viewport.clientHeight){centerX=((minX+maxX+1)/2-x0)*tile;centerY=((minY+maxY+1)/2-y0)*tile;}
        }
        viewport.scrollLeft=Math.max(0,centerX-viewport.clientWidth/2);viewport.scrollTop=Math.max(0,centerY-viewport.clientHeight/2);
      }
      viewport.onscroll=()=>{if(viewport.isConnected)view.scroll={key:scrollKey,left:viewport.scrollLeft,top:viewport.scrollTop};};
    };requestAnimationFrame(restore);
    const selected=view.selected,record=discoveries.find(d=>d.pos===selected);
    const findings=node('section','mn-findings');findings.dataset.reviewPos=selected||'';root.appendChild(findings);
    const findingHead=node('div','mn-finding-head');findingHead.append(node('h3','mn-section-title',name(selected)+(selected?' · '+selected:'')),viewButton('返回地图',()=>reveal(viewport),false));findings.appendChild(findingHead);
    if(record){
      findings.appendChild(node('p','mn-discovered-by',who(record.uid)+' 发现 · 第 '+(discoveries.indexOf(record)+1)+' 次开门'));
      const cards=node('div','mn-discovery-cards');
      (record.cards||[]).forEach(card=>{
        const article=node('article','mn-card');article.dataset.cardName=card.name;article.dataset.cardKind=card.kind;
        article.append(sprite(card.kind,card.name),node('small','mn-card-kind',kindNames[card.kind]||card.kind),node('strong','mn-card-name',card.name),node('p','mn-card-text',card.text||''));cards.appendChild(article);
      });
      if(!cards.children.length)cards.appendChild(node('p','mn-empty','本次没有新的牌'));findings.appendChild(cards);
    }else findings.appendChild(node('p','mn-empty','这里尚无开门抽牌记录'));
    const history=node('details','mn-history');history.open=!!view.historyOpen;history.appendChild(node('summary','','发现档案 · '+discoveries.length+' 次 · 回看房间与卡牌'));
    history.ontoggle=()=>{if(history.isConnected)view.historyOpen=history.open;};
    const entries=node('div','mn-history-list');discoveries.slice().reverse().forEach((discovery,reverseIndex)=>{
      const button=node('button','gbtn mn-history-entry','第 '+(discoveries.length-reverseIndex)+' 次 · '+discovery.room+' · '+who(discovery.uid));button.type='button';button.dataset.discoveryPos=discovery.pos;button.onclick=()=>select(discovery.pos);entries.appendChild(button);
    });
    if(!discoveries.length)entries.appendChild(node('p','mn-empty','首次开门后的房间和卡牌会保存在这里'));history.appendChild(entries);root.appendChild(history);
    const roster=node('details','mn-roster');roster.open=!!view.rosterOpen;roster.appendChild(node('summary','','玩家与属性 · '+players.length+' 人'));
    roster.ontoggle=()=>{if(roster.isConnected)view.rosterOpen=roster.open;};
    players.forEach(uid=>{const stats=(s.stats||{})[uid]||{},key=positions[uid],line=node('div','mn-player-line');
      line.append(node('strong','',who(uid)+(uid===me?'（你）':'')+(alive.includes(uid)?'':' · 阵亡')),node('div','',name(key)+' · '+(key||'未知')),node('div','mn-stat-values','力量 '+(stats.might??'—')+' · 速度 '+(stats.speed??'—')+' · 理智 '+(stats.sanity??'—')+' · 知识 '+(stats.knowledge??'—')));
      const items=(s.items||{})[uid]||[];if(items.length)line.appendChild(node('div','',items.join('、')));roster.appendChild(line);
    });root.appendChild(roster);
    if(view.pendingReveal===selected)requestAnimationFrame(()=>{if(findings.isConnected&&view.pendingReveal===selected){reveal(findings);view.pendingReveal=null;}});
  }
  return {paint};
})();
"""

WEB_CSS = r"""
#gmain:has(.mn-shell){max-height:calc(90vh - 140px)}
.mn-shell{width:100%;min-width:0;box-sizing:border-box;font-size:12px;color:var(--txt)}
.mn-tools{position:sticky;top:0;z-index:6;padding:5px 0;background:var(--card,#fffaf0);border-bottom:1px solid var(--line)}
.mn-turn{font-size:13px;font-weight:700;line-height:1.5}.mn-status,.mn-haunt{font-size:11px;line-height:1.5}.mn-haunt{color:#a84545}
.mn-moves{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}.mn-shell button.mn-action{font-size:12px;min-height:32px;padding:4px 9px}.mn-moves .mn-end{margin-left:auto}
.mn-extra{margin-top:4px}.mn-extra summary,.mn-history summary,.mn-roster summary{cursor:pointer;font-size:12px;font-weight:700;line-height:1.6}.mn-extra-buttons{display:flex;flex-wrap:wrap;gap:5px;padding:5px 0}
.mn-navigation{display:flex;gap:6px;flex-wrap:wrap;margin:7px 0 3px}.mn-shell button.mn-view-button{font-size:11px;padding:4px 9px;min-height:30px}.mn-map-hint{font-size:10px;line-height:1.4;margin:4px 0;color:var(--dim)}
.mn-map-viewport{width:100%;max-width:100%;min-width:0;box-sizing:border-box;overflow:auto;border:1px solid #55525d;border-radius:8px;background:#23232d;overscroll-behavior:contain;scrollbar-color:#827c7f #292832}
.mn-stage{position:relative;margin:0 auto;background-color:#242630;background-image:linear-gradient(#c9c2a410 1px,transparent 1px),linear-gradient(90deg,#c9c2a410 1px,transparent 1px);background-size:var(--mn-tile) var(--mn-tile)}
.mn-tile{position:absolute;width:var(--mn-tile);height:var(--mn-tile);box-sizing:border-box}.mn-shell button.mn-room-inspect{display:block;position:relative;width:100%;height:100%;padding:0;border:1px solid #938571;border-radius:0;background:#cfc3a3;color:#312f2b;box-shadow:none;overflow:hidden;cursor:pointer}
.mn-current .mn-room-inspect{outline:2px solid #3baf98;outline-offset:-3px}.mn-selected .mn-room-name{background:#fff3c9;color:#44351e}
.mn-art{background-repeat:no-repeat;background-color:#b9ab91;background-position:center;width:100%;aspect-ratio:1}.mn-art-fallback{display:flex;justify-content:center;align-items:center;color:#322f29;font-size:15px;font-weight:700}
.mn-room-name{position:absolute;top:15px;left:4px;right:4px;background:#fff7e6ed;color:#342f28;border-radius:3px;padding:2px 3px;font-size:12px;line-height:1.25;white-space:normal;overflow-wrap:anywhere;text-align:center}
.mn-occupants{position:absolute;left:5px;right:5px;bottom:11px;display:flex;flex-wrap:wrap;gap:3px;pointer-events:none;z-index:2}.mn-seat{background:var(--mn-player,#536879);color:#fff;border:1px solid #fff7e6;border-radius:4px;padding:2px 4px;line-height:1.1;font-size:10px;box-shadow:0 1px 3px #0007}.mn-dead{background:#5b5761;text-decoration:line-through}
.mn-shell button.mn-door,.mn-shell button.mn-door:disabled{position:absolute;z-index:4;border:1px solid #e5c47e;background:#b27e37;color:#fff6dd;box-shadow:0 1px 4px #0008;border-radius:4px;padding:0;text-align:center;font-size:14px;line-height:1;min-height:0}
.mn-shell button.mn-door:disabled{background:#55505b;color:#d1c9c0;border-color:#89818b;cursor:default}
.mn-door-up,.mn-door-down{width:28px;height:20px;left:calc(50% - 14px)}.mn-door-up{top:-10px}.mn-door-down{bottom:-10px}.mn-door-left,.mn-door-right{width:20px;height:28px;top:calc(50% - 14px)}.mn-door-left{left:-10px}.mn-door-right{right:-10px}
.mn-shell button.mn-room-inspect:focus-visible,.mn-shell button.mn-door:focus-visible{outline:3px solid #ffc761;outline-offset:-3px}
.mn-section-title{font-size:14px;margin:9px 0 3px}.mn-discovered-by,.mn-empty{font-size:11px;line-height:1.5;margin:4px 0;color:var(--dim)}
.mn-finding-head{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-top:5px}.mn-finding-head .mn-section-title{margin:0}
.mn-discovery-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:6px 0}.mn-card{min-width:0;background:#fff8e8;color:#302e2b;border:1px solid #bbaa86;border-radius:7px;overflow:hidden}.mn-card .mn-art{aspect-ratio:4/3}
.mn-card-kind{display:inline-block;margin:5px 6px 2px;padding:1px 5px;border-radius:3px;background:#e7dec9;color:#4b3c29;font-size:10px}.mn-card-name{display:block;margin:2px 6px;font-size:13px;line-height:1.3}.mn-card-text{margin:5px 6px 8px;font-size:12px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere}
.mn-history,.mn-roster{border:1px solid var(--line);border-radius:7px;padding:6px 8px;margin:8px 0}.mn-history-list{display:flex;flex-direction:column;gap:5px;max-height:260px;overflow:auto;margin-top:6px}.mn-shell button.mn-history-entry{text-align:left;font-size:12px;line-height:1.5;padding:5px 8px;flex-shrink:0}
.mn-player-line{padding:7px 0;border-top:1px solid var(--line);font-size:12px;line-height:1.5}.mn-stat-values{font-size:11px;color:var(--dim)}
@media(max-width:560px){.mn-discovery-cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.mn-room-name{font-size:11px}.mn-tools{padding-top:3px}.mn-shell button.mn-action{font-size:11px;padding:4px 7px}.mn-moves{gap:4px}.mn-haunt{font-size:10px}}
"""
