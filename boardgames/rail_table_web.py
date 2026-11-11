"""Railway web table. Route ownership, fares and private tickets come from the room."""

WEB_CSS = r"""
.rail-desk{--rail-navy:#203b49;--rail-cream:#fff8e8;--rail-ink:#1b3945;--rail-edge:#c4ae81;box-sizing:border-box;container-type:inline-size;background:#f1e6ca;color:var(--rail-ink);border:1px solid #af9570;border-radius:12px;overflow:hidden;font-family:"Microsoft YaHei UI",sans-serif;text-align:left}
.rail-desk *{box-sizing:border-box}.rail-desk h3,.rail-desk h4,.rail-desk p{margin:0}.rail-desk button{font:inherit;cursor:pointer;color:inherit}.rail-desk button:disabled{cursor:default;opacity:.65}
.rail-head{display:flex;align-items:center;gap:10px;min-height:53px;padding:7px 12px;background:var(--rail-navy);color:#fff7df;border-bottom:3px solid #dfae62}
.rail-head .rail-stamp{width:40px;height:40px;border:2px solid #f4d7a1;border-radius:50%;flex:none}
.rail-head h3{font-size:18px;line-height:1.22;color:#fff7df;letter-spacing:.09em}.rail-head small{display:block;font-size:11px;color:#ebdabb;margin-top:2px}
.rail-scores{margin-left:auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:3px}.rail-seat{padding:2px 5px 2px 7px;border-left:4px solid var(--owner);background:#38505a;border-radius:3px;color:#fff7df;font-size:11px}.rail-seat.is-turn{background:#fff2d2;color:#213e49;font-weight:700}
.rail-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(142px,25%);gap:9px;padding:9px}.rail-field,.rail-side{min-width:0}.rail-side{display:flex;flex-direction:column;gap:8px}
.rail-chart{position:relative;background:#e9dbb4;border:1px solid #9c8565;border-radius:7px;overflow:hidden;line-height:0}.rail-chart svg{display:block;width:100%;height:auto}
.rail-route{cursor:pointer;outline:none}.rail-route:focus .rail-rail,.rail-route:hover .rail-rail{stroke:#ffc464;stroke-width:10}.rail-route[data-chosen="true"] .rail-rail{stroke:#ffcf6b;stroke-width:13}.rail-route[data-muted="true"]{opacity:.24}
.rail-station-name{font:700 15px "Microsoft YaHei UI",sans-serif;fill:#213b43;paint-order:stroke fill;stroke:#fffae8;stroke-width:4.5px;stroke-linejoin:round}
.rail-quote{min-height:42px;display:flex;align-items:center;justify-content:space-between;gap:5px;padding:6px 8px;margin:0 2px;background:#fff8e6;color:#213a47;border:1px solid var(--rail-edge);border-top:0;border-radius:0 0 6px 6px;font-size:12px}
.rail-quote strong,.rail-side h4,.rail-field h4{font-weight:750;font-size:12px}.rail-fares{display:inline-flex;align-items:center;vertical-align:middle;margin-left:4px}
.rail-fare{display:inline-block;width:10px;height:15px;margin-right:-2px;background:var(--fare);border:1px solid #fff8e8;outline:1px solid #5b5c55;transform:rotate(6deg);border-radius:2px}.rail-fare.short{background:transparent;border:1px dashed var(--fare);outline:none}
.rail-claim{border:0;border-radius:4px;padding:5px 9px!important;background:#224b50!important;color:#fff9e9!important;font-weight:700!important;white-space:nowrap}.rail-claim:disabled{background:#7c8176!important}.rail-hand{padding:7px 2px 0}.rail-hand h4,.rail-side h4{margin-bottom:5px;color:#29414b}
.rail-cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}.rail-coach{position:relative;padding:3px!important;border:1px solid #9e845e!important;background:#fff8e8!important;color:#243942!important;border-radius:5px;overflow:hidden;box-shadow:0 2px 0 #c6ac82}
.rail-coach[aria-pressed="true"]{outline:2px solid #204752;outline-offset:0}.rail-coach.is-empty .rail-print{opacity:.5}
.rail-picture{background-image:url("/game-art/tielu-coach-cards.webp");background-size:300% 200%;background-repeat:no-repeat}
.rail-print{overflow:hidden;aspect-ratio:1.75;display:block;border-radius:2px;background:#ded8c6;position:relative}.rail-print .rail-picture{position:absolute;display:block;width:100%;aspect-ratio:1;top:50%;transform:translateY(-50%)}
.rail-caption{display:flex;align-items:center;justify-content:space-between;gap:1px;padding:2px 2px 0;font-weight:700;font-size:11px;line-height:1.2}.rail-caption b{font:800 15px/1.2 "Segoe UI",sans-serif;color:var(--rail-navy)}
.rail-piles{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:2px 3px 5px}.rail-deck{border-radius:6px;position:relative;min-height:69px;padding:5px 4px 4px!important;display:flex;align-items:center;justify-content:center;flex-direction:column;isolation:isolate;box-shadow:2px 2px #efe1be,3px 3px #786e59,4px 4px #e0cba3;line-height:1.12;text-align:center}
.rail-deck.ticket-deck{border:2px solid #a75d46;background:repeating-linear-gradient(135deg,#a44038 0 4px,#af4e42 4px 7px)!important;color:#fff1d0!important}.rail-deck.goal-deck{border:2px solid #32716f;background:repeating-linear-gradient(135deg,#1e6766 0 4px,#286f6c 4px 7px)!important;color:#fff1d0!important}.rail-deck::after{content:"";position:absolute;inset:3px;border:1px solid #f8dfac;border-radius:3px;opacity:.78;pointer-events:none}.rail-deck b{font-size:12px}.rail-deck small{font-size:10px;color:inherit}.rail-deck svg{width:25px;height:20px;margin-bottom:3px}
.rail-contracts{display:grid;gap:6px}.rail-contract{position:relative;display:grid;grid-template-columns:1fr auto;align-items:center;width:100%;padding:5px 6px!important;background:#fff6df!important;color:#253d48!important;border:1px solid #b79e71!important;border-left:4px solid #877b5b!important;border-radius:4px;text-align:left}
.rail-contract[aria-pressed="true"]{border-color:#207979!important;outline:1px solid #207979}.rail-contract.is-connected{border-left-color:#2f8272!important}.rail-contract .rail-stops{display:flex;gap:3px;align-items:center;font-size:12px;font-weight:700}.rail-contract .rail-ticket-score{padding:1px 4px;border-left:1px dashed #a68e62;font-size:12px;font-weight:700;color:#7f5131}.rail-contract small{grid-column:1/-1;font-size:10px;color:#56695d}
.rail-pass{align-self:flex-end;background:transparent!important;border:0!important;font-size:11px!important;color:#415455!important;text-decoration:underline;padding:3px!important}.rail-desk button:focus-visible{outline:3px solid #2b7787;outline-offset:1px}
.rail-seat{display:inline-flex;gap:3px;align-items:center}.rail-seat .name{max-width:56px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rail-seat b{flex:none}
.rail-contract{display:grid;grid-template-columns:minmax(0,1fr) 25px;padding:5px!important;background:linear-gradient(105deg,#fff9e5 60%,#ead8ac)!important;box-shadow:0 2px 0 #d3c396}
.rail-contract::after{content:"";position:absolute;right:26px;top:0;bottom:0;border-left:1px dashed #9f875d}
.rail-stops{justify-content:space-around;align-items:center}.rail-place{display:flex;align-items:center;flex-direction:column;gap:2px;min-width:0;color:#2b424a;font-size:11px}
.rail-postmark{width:clamp(29px,5cqw,44px);aspect-ratio:1;background-image:url("/game-art/tielu-stations.webp");background-repeat:no-repeat;background-size:400% 200%;border:2px dotted #fbf5d9;box-shadow:0 0 0 1px #a18a6d;transform:rotate(-3deg)}
.rail-place:last-child .rail-postmark{transform:rotate(3deg)}.rail-contract .rail-ticket-score{display:flex;flex-direction:column;gap:1px;font-weight:750;border:0;text-align:center;padding:0}.rail-ticket-score small{font-size:10px}
.rail-contract .rail-seal{padding:2px 4px;border:1px solid #aa9571;border-radius:30%;color:#806e57;font-size:9px;justify-self:center;margin-top:3px;letter-spacing:1px}.rail-contract.is-connected .rail-seal{color:#17755c;border-color:#368b6b}
.rail-end{grid-column:1/-1;width:100%;border-collapse:collapse;margin:6px 0;font-size:12px;text-align:center}.rail-end th,.rail-end td{padding:4px;border-bottom:1px solid #cdb894}.rail-end caption{font-weight:700;text-align:left;margin-bottom:5px}
#gpanel .card:has(.rail-desk){width:min(900px,96vw)}#gmain:has(.rail-desk){max-height:calc(90vh - 122px)}#gpanel .card:has(.rail-desk) #glog{max-height:53px}
@container(max-width:510px){.rail-body{grid-template-columns:minmax(0,1fr);padding:6px;gap:7px}.rail-side{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.2fr);gap:7px}.rail-pass{grid-column:1/-1;justify-self:end}.rail-piles{gap:4px}.rail-head{padding:5px 7px;gap:6px}.rail-head h3{font-size:16px}.rail-head .rail-stamp{width:34px;height:34px}.rail-seat{font-size:10px;max-width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rail-chart{border-radius:5px}.rail-quote{font-size:11px}.rail-cards{gap:3px}.rail-caption{font-size:10px}.rail-caption b{font-size:13px}.rail-deck b{font-size:10px}.rail-deck{min-height:66px}.rail-print{aspect-ratio:1.5}}
"""

WEB_JS = r"""
const RailTable=(()=>{
  const colors=[
    ["red","红","#bf493d"],["yellow","黄","#d6a129"],["green","绿","#36815e"],
    ["blue","蓝","#3379ba"],["purple","紫","#81549d"]
  ];
  const stations=[[96,80],[252,64],[432,67],[528,149],[462,266],[276,266],[108,262],[60,172]];
  const bends={"0-7":36,"0-3":-72,"0-4":5,"1-4":-12,"2-6":-12,"3-6":-22,"1-5":10};
  const seats=["#ef8366","#64aed9","#82be8c","#d8aa65"];
  const svgNS="http://www.w3.org/2000/svg";
  let board=null;

  function el(tag,cls,content){
    const e=document.createElement(tag);if(cls)e.className=cls;
    if(content!=null)e.textContent=String(content);return e;
  }
  function svg(tag,attrs){
    const e=document.createElementNS(svgNS,tag);
    for(const [key,value] of Object.entries(attrs||{}))e.setAttribute(key,String(value));
    return e;
  }
  function btn(cls,label,handler){
    const b=el("button",cls);b.type="button";b.setAttribute("aria-label",label);b.onclick=handler;return b;
  }
  function picture(index,cls){
    const p=el("span","rail-picture "+(cls||""));
    p.style.backgroundPosition=(index%3)*50+"% "+Math.floor(index/3)*100+"%";p.setAttribute("aria-hidden","true");return p;
  }
  function routeId(a,b){return [Math.min(a,b),Math.max(a,b)].join("-");}
  function ink(key){return colors.find(c=>c[0]===key)||["","", "#655f54"];}
  function finalTickets(known,routes,uid){
    const owned=routes.filter(r=>r.claimed===uid);
    return known.map(t=>{
      const reachable=new Set([t.a]);
      for(const station of reachable){
        for(const r of owned){
          if(r.a===station)reachable.add(r.b);
          if(r.b===station)reachable.add(r.a);
        }
      }
      return {...t,connected:reachable.has(t.b)};
    });
  }
  function paintMap(s,selected,choose){
    const chart=el("div","rail-chart");
    const map=svg("svg",{viewBox:"0 0 600 350",role:"group","aria-label":"铁路地图，选择线路查看票价",class:"tl-map"});
    if(BG.tielu_travel)map.append(svg("image",{href:BG.tielu_travel,width:600,height:350,preserveAspectRatio:"none","pointer-events":"none"}));
    map.append(svg("rect",{width:600,height:350,fill:"#fff7dc",opacity:".19","pointer-events":"none"}));
    const ticket=selected.goal;
    for(const rt of s.routes||[]){
      const a=Math.min(rt.a,rt.b),b=Math.max(rt.a,rt.b),A=stations[a],B=stations[b];
      if(!A||!B)continue;
      const key=routeId(a,b),dx=B[0]-A[0],dy=B[1]-A[1],dist=Math.hypot(dx,dy);
      const bend=bends[key]||0,C=[(A[0]+B[0])/2-dy*bend/dist,(A[1]+B[1])/2+dx*bend/dist];
      const d="M"+A+" Q"+C+" "+B;
      const owner=rt.claimed, color=owner?seats[s.players.indexOf(owner)%seats.length]:ink(rt.color)[2];
      const title=s.cities[a]+" — "+s.cities[b]+"，"+(owner?gnick(owner)+"已认领":ink(rt.color)[1]+"票 "+rt.length+" 张");
      const g=svg("g",{class:"rail-route",tabindex:0,role:"button","aria-label":title,"data-tla":a,"data-tlb":b,
        "data-chosen":selected.route===key,"data-muted":!!selected.color&&selected.color!==rt.color&&selected.route!==key});
      const tip=svg("title");tip.textContent=title;g.append(tip);
      g.append(svg("path",{class:"rail-rail",d,fill:"none",stroke:"#fff0c7","stroke-width":8}));
      g.append(svg("path",{d,fill:"none",stroke:"#6b6350","stroke-width":5,"stroke-dasharray":"1.5 5"}));
      g.append(svg("path",{d,fill:"none",stroke:"#73674e","stroke-width":2.2}));
      const count=rt.length,carW=Math.min(31,(dist-22)/count*.79);
      for(let n=0;n<count;n++){
        const t=.07+.86*(n+.5)/count,u=1-t;
        const x=u*u*A[0]+2*t*u*C[0]+t*t*B[0],y=u*u*A[1]+2*t*u*C[1]+t*t*B[1];
        const angle=Math.atan2(u*(C[1]-A[1])+t*(B[1]-C[1]),u*(C[0]-A[0])+t*(B[0]-C[0]))*180/Math.PI;
        const car=svg("g",{class:"rail-car",transform:"translate("+x+" "+y+") rotate("+angle+")","pointer-events":"none"});
        for(const wheel of [-.29,.29])car.append(svg("circle",{cx:wheel*carW,cy:4.4,r:2.2,fill:"#3a3e3e"}));
        car.append(svg("rect",{x:-carW/2,y:-5,width:carW,height:9,rx:2.1,fill:color,stroke:"#4c4436","stroke-width":1.1}));
        car.append(svg("path",{d:"M"+(-carW*.32)+" -2 h"+carW*.64,stroke:owner?"#243036":"#fff4d3","stroke-width":2.4,"stroke-dasharray":"3.2 1.65"}));
        g.append(car);
      }
      g.append(svg("path",{d,fill:"none",stroke:"transparent","stroke-width":19}));
      g.onclick=()=>choose(key);g.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(key);}};
      map.append(g);
    }
    const route=(s.routes||[]).find(r=>routeId(r.a,r.b)===selected.route);
    for(const [id,name] of Object.entries(s.cities||{})){
      const i=Number(id),P=stations[i];if(!P)continue;
      const marked=!!(ticket&&(ticket.a===i||ticket.b===i))||!!(route&&(route.a===i||route.b===i));
      const station=svg("g",{"pointer-events":"none","data-station":i,"data-highlight":marked});
      if(marked)station.append(svg("circle",{cx:P[0],cy:P[1],r:14,fill:"#ffdb75",stroke:"#784c1d","stroke-width":2}));
      station.append(svg("circle",{cx:P[0],cy:P[1],r:7,fill:"#24444d",stroke:"#fff5d9","stroke-width":3}));
      const above=[0,1,2].includes(i);
      const label=svg("text",{x:P[0],y:P[1]+(above?-12:23),"text-anchor":"middle",class:"rail-station-name"});
      label.textContent=name;station.append(label);map.append(station);
    }
    chart.append(map);return chart;
  }

  function paint(box,s){
    const room=state.gst?.room;if(!room)return;
    const uid=state.uid,rid=room.room_id;
    if(!board||board.rid!==rid||board.uid!==uid||board.token!==state.token||board.round!==room.round){
      board={rid,uid,token:state.token,round:room.round,route:null,goal:null,color:null,pending:null,tickets:[]};
    }
    const view=board,pv=state.gpriv;
    const member=(s.players||[]).includes(uid)&&(room.players||[]).includes(uid)&&!(room.spectators||[]).includes(uid);
    const hand=member&&pv?.hand||{};
    if(!member)view.tickets=[];
    else if(Array.isArray(pv?.tickets))view.tickets=pv.tickets.map(({a,b,v})=>({a,b,v}));
    const tickets=member?(s.winner_uid!=null?finalTickets(view.tickets,s.routes||[],uid):(pv?.tickets||[])):[];
    function fresh(){
      return board===view&&view.token===state.token&&view.round===state.gst?.room?.round
        &&state.groom===rid&&state.uid===uid&&state.gst?.room===room&&state.gst?.state===s&&state.gpriv===pv;
    }
    const onTurn=()=>fresh()&&member&&room.status==="playing"&&s.winner_uid==null&&s.turn_uid===uid&&view.pending!==s;
    const refresh=()=>{if(fresh())renderGamePanel();};
    function send(action){
      if(!onTurn())return;view.pending=s;refresh();
      const retry=()=>{if(view.pending===s){view.pending=null;refresh();}};
      gameAPI("action",{room_id:rid,action}).then(reply=>{if(!reply?.ok)retry();},retry);
    }
    function choose(key){if(fresh()){view.route=key;view.goal=null;refresh();}}
    const root=el("section","rail-desk");box.append(root);
    const header=el("div","rail-head");header.append(picture(5,"rail-stamp"));
    const title=el("div");title.append(el("h3",null,"铁路"));
    const turn=s.winner_uid!=null?"已结算":s.turn_uid===uid?"轮到你":s.turn_uid!=null?"轮到"+gnick(s.turn_uid):"等待结算";
    title.append(el("small",null,turn+(s.final_round?" · 最后一轮":"")+" · 余 "+s.route_left+" 条线路"));
    header.append(title);
    const scores=el("div","rail-scores");
    (s.players||[]).forEach((u,i)=>{
      const p=el("span","rail-seat"+(s.turn_uid===u?" is-turn":""));p.title=gnick(u);
      const points=s.winner_uid!=null?s.final_scores?.[u]?.total:s.score?.[u];
      p.append(el("span","name",gnick(u)),el("b",null,(points??0)+"分"));
      p.style.setProperty("--owner",seats[i%seats.length]);scores.append(p);
    });header.append(scores);root.append(header);
    const body=el("div","rail-body"),field=el("div","rail-field"),side=el("div","rail-side");
    root.append(body);body.append(field,side);
    if(!tickets.some(t=>view.goal&&t.a===view.goal.a&&t.b===view.goal.b))view.goal=null;
    field.append(paintMap(s,view,choose));
    const rt=(s.routes||[]).find(r=>routeId(r.a,r.b)===view.route);
    const quote=el("div","rail-quote");field.append(quote);
    if(rt){
      const detail=el("div");detail.append(el("strong",null,s.cities[rt.a]+" — "+s.cities[rt.b]));
      if(!rt.claimed){
        const fare=el("span","rail-fares");fare.setAttribute("aria-label",ink(rt.color)[1]+"票 "+rt.length+" 张");
        for(let i=0;i<rt.length;i++){const t=el("i","rail-fare"+(i<(hand[rt.color]||0)?"":" short"));t.style.setProperty("--fare",ink(rt.color)[2]);fare.append(t);}
        detail.append(fare);
      }
      quote.append(detail);
      if(rt.claimed)quote.append(el("span",null,gnick(rt.claimed)+" 已认领"));
      else{
        const cost=ink(rt.color)[1]+"票 "+rt.length;
        const missing=rt.length-(hand[rt.color]||0);
        const claim=btn("rail-claim","支付 "+cost+" 张认领",()=>send({op:"claim",a:rt.a,b:rt.b}));
        claim.textContent=missing>0&&member?"还差 "+missing+" 张"+ink(rt.color)[1]+"票":"认领 · "+cost;claim.dataset.railClaim="";claim.disabled=!onTurn()||missing>0;
        quote.append(claim);
      }
    }else if(view.goal){
      quote.append(el("strong",null,s.cities[view.goal.a]+" → "+s.cities[view.goal.b]),el("span",null,"目的票 · "+view.goal.v+"分"));
    }else{
      quote.append(el("span",null,"点地图上的车厢查看线路和票价"));
    }

    if(member&&pv?.hand){
      const rack=el("section","rail-hand"),row=el("div","rail-cards");
      rack.append(el("h4",null,"我的车票"),row);field.append(rack);
      colors.forEach(([key,label,color],i)=>{
        const count=hand[key]||0;
        const card=btn("rail-coach"+(count?"":" is-empty"),label+"票 "+count+" 张，查看同色线路",()=>{
          if(!fresh())return;view.color=view.color===key?null:key;view.route=null;view.goal=null;refresh();});
        card.dataset.color=key;card.setAttribute("aria-pressed",view.color===key);
        const print=el("span","rail-print");print.append(picture(i));card.append(print);
        const cap=el("span","rail-caption");cap.append(el("span",null,label+"票"),el("b",null,count));card.append(cap);row.append(card);
      });
    }
    if(s.winner_uid!=null){
      const table=el("table","rail-end"),heading=el("tr");
      table.append(el("caption",null,gnick(s.winner_uid)+" 获胜"),heading);
      for(const text of ["玩家","线路","连通","未连通","总分"])heading.append(el("th",null,text));
      (s.players||[]).forEach(u=>{const v=s.final_scores?.[u]||{},row=el("tr");
        for(const val of [gnick(u),v.route||0,"+"+(v.ticket_bonus||0),"−"+(v.ticket_penalty||0),v.total||0])row.append(el("td",null,val));table.append(row);
      });side.append(table);
    }
    if(s.winner_uid==null){
    const drawArea=el("section"),piles=el("div","rail-piles");drawArea.append(el("h4",null,"牌堆"),piles);side.append(drawArea);
    function pile(cls,label,sub,op,disabled,path){
      const p=btn("rail-deck "+cls,label,()=>send({op}));p.disabled=!onTurn()||disabled;p.dataset.railDraw=op;
      const icon=svg("svg",{viewBox:"0 0 32 24","aria-hidden":"true"});icon.append(svg("path",{d:path,fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"}));
      p.append(icon,el("b",null,label),el("small",null,sub));piles.append(p);
    }
    const left=s.ticket_left||0;
    pile("ticket-deck","摸车票 ×"+Math.min(2,left),"余 "+left+" 张","draw",left<1,"M5 4h21v13H5z M9 8h5v4H9z M18 8h5v4h-5z M9 20h1 M21 20h1");
    pile("goal-deck","抽目的票","两站 · 1 张","ticket",tickets.length>=RAIL_TICKET_COUNT,"M4 5l7-2 9 3 8-2v15l-8 2-9-3-7 2z M11 4v13 M20 6v14");
    }
    if(tickets.length){
      const satchel=el("section"),list=el("div","rail-contracts");
      satchel.append(el("h4",null,"我的目的票"),list);side.append(satchel);
      for(const t of tickets){
        const picked=view.goal&&view.goal.a===t.a&&view.goal.b===t.b;
        const name=s.cities[t.a]+" → "+s.cities[t.b];
        const pass=btn("rail-contract"+(t.connected?" is-connected":""),name+" "+t.v+"分",()=>{
          if(!fresh())return;view.route=null;view.color=null;view.goal=picked?null:t;refresh();});
        pass.setAttribute("aria-pressed",!!picked);
        const stops=el("span","rail-stops");
        for(const city of [t.a,t.b]){
          if(stops.children.length)stops.append(el("span",null,"→"));
          const place=el("span","rail-place"),stamp=el("span","rail-postmark");stamp.dataset.city=city;
          stamp.style.backgroundPosition=(city%4*100/3)+"% "+(Math.floor(city/4)*100)+"%";
          place.append(stamp,el("b",null,s.cities[city]));stops.append(place);
        }
        const score=el("span","rail-ticket-score");
        score.append(el("b",null,"+"+t.v),el("small",null,"−"+t.v));
        pass.append(stops,score,el("small","rail-seal",t.connected?"已连通":s.winner_uid!=null?"未连通":"待连通"));
        list.append(pass);
      }
    }
    if(member&&s.winner_uid==null){const skip=btn("rail-pass","跳过回合",()=>send({op:"skip"}));skip.textContent="跳过回合";skip.disabled=!onTurn();side.append(skip);}
  }
  return {paint,reset(){board=null;}};
})();
"""
