"""Gem City and Love Letter presentation; rules and private delivery stay in Hub."""

WEB_JS = r"""
const CardTableWeb = (() => {
  const inks={o:'#424550',d:'#b6c7d7',r:'#b83d49',e:'#247c5e',s:'#336ab4',g:'#b78025'};
  const labels={o:'黑',d:'白',r:'红',e:'绿',s:'蓝',g:'金'};
  const gemColors=['o','d','r','e','s'];
  const gemNames={o:'黑玛瑙',d:'白钻石',r:'红宝石',e:'祖母绿',s:'蓝宝石',g:'黄金'};
  const tierNames={1:'矿场',2:'工坊',3:'商贸城市'};
  const jewelFiles={1:'gemcity-tier1.webp?v=anime-v1',2:'gemcity-tier2.webp?v=anime-v1',3:'gemcity-tier3.webp?v=anime-v1'};
  const loveNames={1:'护卫',2:'牧师',3:'男爵',4:'侍女',5:'王子',6:'国王',7:'伯爵夫人',8:'公主'};
  const loveEffects={1:'猜中目标持牌即可淘汰',2:'查看一名目标的持牌',3:'与目标比较持牌点数',4:'获得侍女保护',5:'令目标弃牌并重新摸牌',6:'与目标交换持牌',7:'与公主同持时必须弃出',8:'弃出公主即刻出局'};
  const sources=new Map();
  function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function art(file,index,cols,rows,title){
    const e=node('div','ct-art');e.setAttribute('role','img');e.setAttribute('aria-label',title);
    if(!Number.isInteger(index)||index<0||index>=cols*rows){e.classList.add('ct-no-art');e.textContent=title;return e;}
    e.dataset.art=String(index);e.dataset.artFile=file;
    e.style.backgroundImage='url("/game-art/'+file+'")';
    e.style.backgroundSize=(cols*100)+'% '+(rows*100)+'%';
    e.style.backgroundPosition=(cols===1?0:(index%cols)*100/(cols-1))+'% '+(rows===1?0:Math.floor(index/cols)*100/(rows-1))+'%';
    let source=sources.get(file);
    if(!source){
      source={image:new Image(),targets:new Set(),ready:false,failed:false};sources.set(file,source);
      source.image.onload=()=>{source.ready=true;for(const target of source.targets)fit(target,source.image);source.targets.clear();};
      source.image.onerror=()=>{source.failed=true;for(const target of source.targets)target.classList.add('ct-art-missing');source.targets.clear();};
      source.image.src='/game-art/'+file;
    }
    function fit(target,image){target.style.aspectRatio=(image.naturalWidth/cols)+' / '+(image.naturalHeight/rows);}
    if(source.ready)fit(e,source.image);else if(source.failed)e.classList.add('ct-art-missing');else source.targets.add(e);
    return e;
  }
  function cost(tokens,colors){
    const row=node('span','ct-cost');
    for(const [color,count] of Object.entries(tokens||{})){
      if(!(count>0))continue;
      const chip=node('span','ct-cost-chip');chip.style.setProperty('--gem-ink',inks[color]||'#666');
      chip.title=(colors&&colors[color]||labels[color]||color)+' × '+count;
      chip.append(node('i','ct-gem ct-gem-'+color,labels[color]||color),node('b','',String(count)));row.appendChild(chip);
    }
    if(!row.children.length)row.appendChild(node('span','ct-free','0'));
    return row;
  }
  function jewel(color){
    const index=[...gemColors,'g'].indexOf(color);
    const e=index>=0?art('gemcity-jewels.webp?v=anime-v1',index,3,2,gemNames[color]):node('span');
    e.className='ct-jewel ct-jewel-'+color;
    e.setAttribute('role','img');e.setAttribute('aria-label',gemNames[color]||'宝石');
    e.appendChild(node('i','ct-jewel-core'));return e;
  }
  function gemCost(tokens){
    const row=node('span','ct-cost ct-jewel-cost');
    for(const c of gemColors){
      const count=Number((tokens||{})[c])||0;if(count<=0)continue;
      const chip=node('span','ct-price-coin ct-coin-'+c);chip.dataset.gem=c;
      chip.setAttribute('aria-label',gemNames[c]+' '+count);chip.title=gemNames[c]+' × '+count;
      chip.append(node('i','ct-coin-facet ct-jewel-'+c),node('b','',String(count)));row.appendChild(chip);
    }
    if(row.children.length>2)row.classList.add('ct-cost-many');
    if(!row.children.length)row.appendChild(node('span','ct-free','0'));
    return row;
  }
  function cardIdentity(card){
    return JSON.stringify([card.tier,card.art_set,card.art,card.title,card.disc,card.pts,
      gemColors.map(c=>Number((card.cost||{})[c])||0)]);
  }
  function jewelCard(card,tier){
    return card.art_set==='jewel-v2'&&[1,2,3].includes(tier)&&Number.isInteger(card.art)
      &&card.art>=0&&card.art<20&&Math.floor(card.art/4)===gemColors.indexOf(card.disc);
  }
  function cardName(card,tier){
    return jewelCard(card,tier)&&card.title?card.title:
      (gemColors.includes(card.disc)?gemNames[card.disc]:'宝石')+' · '+(tierNames[tier]||'发展卡');
  }
  function development(card,options){
    options=options||{};const tier=Number(card.tier)||options.tier||1;
    const title=cardName(card,tier),validArt=jewelCard(card,tier);
    const wrap=node('article','ct-development');wrap.dataset.title=title;wrap.dataset.discount=card.disc;
    const face=node(options.onSelect||options.onBuy||options.onView?'button':'div','ct-face');
    if(options.onSelect){face.type='button';face.onclick=options.onSelect;face.setAttribute('aria-label','选择 '+title);face.setAttribute('aria-pressed',String(!!options.selected));}
    else if(options.onView){face.type='button';face.onclick=options.onView;face.setAttribute('aria-label','欣赏 '+title);}
    else if(options.onBuy){face.type='button';face.disabled=!options.canBuy;face.onclick=options.onBuy;face.setAttribute('aria-label','购买 '+title);}
    const image=validArt?art(jewelFiles[tier],card.art,4,5,title):node('div','ct-art ct-neutral ct-neutral-'+card.disc);
    image.setAttribute('role','img');image.setAttribute('aria-label',title);
    const discountColor=gemColors.includes(card.disc)?card.disc:null;
    image.appendChild(jewel(discountColor));
    const head=node('div','ct-card-head');
    if(Number(card.pts)>0)head.appendChild(node('b','ct-points',String(card.pts)));
    const discount=node('span','ct-discount');discount.title='永久 '+(gemNames[discountColor]||'宝石')+' +1';
    discount.setAttribute('aria-label',discount.title);discount.appendChild(jewel(discountColor));
    head.appendChild(discount);image.append(head,gemCost(card.cost),node('strong','ct-card-name',title));face.appendChild(image);
    wrap.classList.toggle('ct-selected',!!options.selected);wrap.classList.toggle('ct-affordable',!!options.canBuy);
    if(options.onView)face.appendChild(node('span','ct-view-label','点击欣赏'));
    wrap.appendChild(face);
    if(options.onReserve){const reserve=node('button','ct-reserve',options.reserveFull?'保留已满':'保留');reserve.type='button';reserve.disabled=!options.canReserve;reserve.onclick=options.onReserve;reserve.setAttribute('aria-label','保留 '+title);wrap.appendChild(reserve);}
    return wrap;
  }
  function owned(game,s){
    const room=state.gst&&state.gst.room;
    const players=room&&Array.isArray(room.players)?room.players:(s.players||[]);
    return !!(room&&room.game===game&&room.room_id===state.groom&&players.includes(state.uid));
  }
  function canAct(game,s,turn){
    const room=state.gst&&state.gst.room;
    return owned(game,s)&&room.status==='playing'&&state.gst.state===s&&s.winner_uid==null&&s.status!=='ended'&&turn===state.uid;
  }
  function personal(box,s,afford,send,controls){
    if(!owned('gemcity',s))return;
    const pv=state.gpriv||{},myTurn=canAct('gemcity',s,s.turn_uid);
    const section=node('section','ct-personal');
    const album=node('details','ct-album');
    const collection=Array.isArray(pv.collection)?pv.collection:[];
    const count=Array.isArray(pv.collection)?collection.length:(Number(pv.cards)||0);
    const key=state.groom+':'+state.uid+':'+((state.gst.room||{}).round||0);
    album.open=state.ctAlbumOpen===key;
    const summary=node('summary','','我的藏册 · '+count+' 张 · '+(album.open?'收起':'展开浏览'));album.appendChild(summary);
    const grid=node('div','ct-album-grid'),view=node('div','ct-album-view');view.hidden=true;
    const identity=cardIdentity;
    function show(index,focus){
      if(!owned('gemcity',s)||state.gst.state!==s||state.gpriv!==pv||!collection[index])return;
      const card=collection[index];state.ctViewedCard={context:key,index,identity:identity(card)};
      view.innerHTML='';const back=node('button','gbtn ct-album-back','返回卡册');back.type='button';
      back.onclick=()=>{state.ctViewedCard=null;view.hidden=true;grid.hidden=false;if(focus&&focus.focus)focus.focus();};
      view.append(back,node('p','ct-view-note','已购藏品 · '+cardName(card,card.tier)),development(card,{colors:s.colors}));
      grid.hidden=true;view.hidden=false;
    }
    collection.forEach((card,index)=>grid.appendChild(development(card,{colors:s.colors,onView:event=>show(index,event&&event.currentTarget)})));
    if(!collection.length)grid.appendChild(node('p','ct-empty',count?'旧版牌局仅提供已购张数':'购得的发展卡会保存在这里'));
    album.append(grid,view);album.ontoggle=()=>{if(album.isConnected){state.ctAlbumOpen=album.open?key:null;summary.textContent='我的藏册 · '+count+' 张 · '+(album.open?'收起':'展开浏览');}};
    const previous=state.ctViewedCard;
    if(previous&&previous.context===key&&collection[previous.index]&&identity(collection[previous.index])===previous.identity)show(previous.index);
    section.appendChild(album);
    const reserved=Array.isArray(pv.reserved)?pv.reserved:[];
    if(reserved.length){
      section.appendChild(node('h3','ct-section-title','我的保留卡 · '+reserved.length+'/3'));
      const row=node('div','ct-reserved-grid');
      reserved.forEach((card,index)=>row.appendChild(development(card,{colors:s.colors,myTurn,canBuy:myTurn&&afford(card),
        selected:controls&&controls.selected(index,card),onSelect:controls?()=>controls.select(index,card):null,
        onBuy:()=>send({op:'buy_res',idx:index})})));
      section.appendChild(row);
    }
    box.appendChild(section);
  }
  function patrons(box,s,discount){
    const section=node('section','ct-patrons-section');section.appendChild(node('h3','ct-section-title','贵宾 · 发展卡折扣达到门槛即可获邀'));
    const row=node('div','ct-patrons');
    (s.nobles||[]).forEach((threshold,index)=>{
      const title=(s.noble_titles||[])[index]||('贵宾 '+(index+1));
      const card=node('article','ct-patron');const image=art('gemcity-patrons.webp?v=anime-v1',(s.noble_art||[])[index],5,1,title);
      card.append(image,node('strong','ct-card-name',title),cost(threshold,s.colors));
      const ready=Object.entries(threshold).every(([color,count])=>(discount[color]||0)>=count);
      card.appendChild(node('small','ct-patron-status',ready?'门槛已达':'门槛'));row.appendChild(card);
    });
    section.appendChild(row);box.appendChild(section);
  }
  function gemcity(box,s){
    box.appendChild(gTitle('gemcity','璀璨宝石 · 珠宝商会'));
    const table=node('div','ct-table ct-gemcity');box.appendChild(table);
    const me=state.uid,token=state.token,room=state.gst&&state.gst.room;
    const roomId=room&&room.room_id,gameRound=room&&room.round;
    const mine=owned('gemcity',s),myTurn=canAct('gemcity',s,s.turn_uid);
    const context=JSON.stringify([state.groom,me,token,room&&room.round]);
    let move=state.ctGemMove;
    if(!move||move.context!==context){move={context,pick:null,coins:[],busy:false,message:''};state.ctGemMove=move;}
    if(move.busy&&move.snapshot!==s){move.busy=false;move.message='';move.pick=null;move.coins=[];}
    if(!myTurn){move.coins=[];move.busy=false;}
    const current=()=>state.ctGemMove===move&&state.uid===me&&state.token===token
      &&state.groom===roomId&&state.gst&&state.gst.room&&state.gst.room.room_id===roomId
      &&state.gst.room.round===gameRound&&state.gst.state===s;
    const live=()=>current()&&table.isConnected;
    const enabled=()=>live()&&canAct('gemcity',s,s.turn_uid)&&!move.busy;
    const bank=s.bank||{},toks=(s.tokens||{})[me]||{},disc=(s.discount||{})[me]||{};
    const pv=mine?(state.gpriv||{}):{},reserved=Array.isArray(pv.reserved)?pv.reserved:[];
    const afford=card=>gemColors.reduce((gold,c)=>gold+Math.max(0,(Number((card.cost||{})[c])||0)
      -(Number(disc[c])||0)-(Number(toks[c])||0)),0)<=(Number(toks.g)||0);
    const getCard=pick=>pick&&(pick.kind==='reserved'?reserved[pick.idx]:((s.market||{})[pick.tier]||[])[pick.idx]);
    if(move.pick&&(!getCard(move.pick)||cardIdentity(getCard(move.pick))!==move.pick.identity))move.pick=null;
    const top=node('header','ct-table-top');
    const status=s.winner_uid!=null?'胜者 · '+gnick(s.winner_uid):s.status==='ended'?'本局结束':
      (myTurn?'你的回合':'轮到 '+gnick(s.turn_uid));
    top.append(node('strong','ct-turn',status),node('span','ct-table-goal',s.win_pts?'目标 '+s.win_pts+' 声望':'珠宝发展 · 永久折扣'));
    table.appendChild(top);
    const scene=node('div','ct-gem-scene'),market=node('section','ct-market'),aside=node('aside','ct-gem-aside');
    market.setAttribute('aria-label','三级发展卡市场');scene.append(market,aside);table.appendChild(scene);
    const cardNodes=[],bankNodes=[];
    function select(kind,tier,idx,card){
      if(!live()||move.busy)return;
      const identity=cardIdentity(card),old=move.pick;
      move.pick=old&&old.kind===kind&&old.tier===tier&&old.idx===idx&&old.identity===identity?null:{kind,tier,idx,identity};
      move.coins=[];move.message='';refresh();
    }
    for(const tier of [3,2,1]){
      const band=node('div','ct-tier'),deck=node('div','ct-tier-deck ct-tier-'+tier);
      const count=(s.deck_left||{})[tier];
      deck.append(node('span','ct-tier-level','●'.repeat(tier)),node('b','',String(tier)),
        node('small','ct-deck-count',Number.isInteger(count)?String(count):'—'));
      deck.title=tier+'级牌堆 · 剩余 '+(Number.isInteger(count)?count:'未提供');
      deck.setAttribute('aria-label',deck.title);band.appendChild(deck);
      const row=node('div','ct-market-row');row.dataset.tier=String(tier);
      const cards=(s.market||{})[tier]||[];
      for(let idx=0;idx<4;idx++){
        const card=cards[idx];
        if(!card){row.appendChild(node('div','ct-card-empty','售罄'));continue;}
        const wrap=development(card,{tier,canBuy:myTurn&&afford(card),onSelect:()=>select('market',tier,idx,card)});
        cardNodes.push({wrap,kind:'market',tier,idx,card});row.appendChild(wrap);
      }
      band.appendChild(row);market.appendChild(band);
    }
    const bankSection=node('section','ct-bank');bankSection.appendChild(node('h3','ct-section-title','珠宝银行'));
    const bankRow=node('div','ct-bank-row');bankSection.appendChild(bankRow);aside.appendChild(bankSection);
    for(const color of [...gemColors,'g']){
      const button=node(color==='g'?'div':'button','ct-bank-chip');button.dataset.gem=color;
      button.append(jewel(color),node('b','ct-bank-count',String(Number(bank[color])||0)),node('small','ct-bank-name',gemNames[color]));
      if(color==='g')button.title='黄金 · 保留卡获得的万能筹码';
      else{
        button.type='button';button.setAttribute('aria-label','选择 '+gemNames[color]);
        button.onclick=()=>{
          if(!enabled()||(bank[color]||0)<=0)return;
          move.pick=null;move.message='';
          if(move.coins.includes(color))move.coins=move.coins.filter(c=>c!==color);
          else if(move.coins.length<3)move.coins.push(color);
          refresh();
        };
      }
      bankNodes.push({button,color});bankRow.appendChild(button);
    }
    const patronsSection=node('section','ct-patrons-section');patronsSection.appendChild(node('h3','ct-section-title','贵宾'));
    const patronsRow=node('div','ct-patrons');patronsSection.appendChild(patronsRow);aside.appendChild(patronsSection);
    (s.nobles||[]).forEach((threshold,index)=>{
      const title=(s.noble_titles||[])[index]||('贵宾 '+(index+1));
      const card=node('article','ct-patron'),image=art('gemcity-patrons.webp?v=anime-v1',(s.noble_art||[])[index],5,1,title);
      const points=node('b','ct-patron-points',String(Number.isFinite(s.noble_points)?s.noble_points:3));
      image.append(points,node('strong','ct-card-name',title));
      card.append(image,gemCost(threshold));
      card.title=title+' · 永久折扣门槛';
      card.classList.toggle('ct-patron-ready',mine&&Object.entries(threshold).every(([c,n])=>(disc[c]||0)>=n));
      patronsRow.appendChild(card);
    });
    const controls=node('section','ct-gem-tools');controls.setAttribute('aria-label','本手行动');
    const notice=node('div','ct-gem-notice');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
    const actions=node('div','ct-gem-actions');controls.append(notice,actions);table.appendChild(controls);
    function actionButton(label,cls,fn){const b=node('button','gbtn '+cls,label);b.type='button';b.onclick=fn;actions.appendChild(b);return b;}
    function send(action){
      if(!enabled())return;
      move.busy=true;move.snapshot=s;move.message='';refresh();
      let request;
      try{request=gameAPI('action',{room_id:roomId,action});}
      catch(error){move.message='这手尚未确认，请刷新牌桌。';refresh();return;}
      if(request&&typeof request.then==='function')request.then(result=>{
        if(!current())return;
        if(result&&result.ok===false){move.busy=false;move.message='这手未成功，请重新选择。';refresh();}
      },()=>{if(current()){move.message='这手尚未确认，请刷新牌桌。';refresh();}});
    }
    const buy=actionButton('购买所选','go ct-confirm-buy',()=>{
      const pick=move.pick,card=getCard(pick);
      if(!pick||!card||cardIdentity(card)!==pick.identity||!afford(card))return;
      send(pick.kind==='reserved'?{op:'buy_res',idx:pick.idx}:{op:'buy',tier:pick.tier,idx:pick.idx});
    });
    const reserve=actionButton('保留所选','ct-confirm-reserve',()=>{
      const pick=move.pick,card=getCard(pick);
      if(!pick||pick.kind!=='market'||!card||cardIdentity(card)!==pick.identity||reserved.length>=3)return;
      send({op:'reserve',tier:pick.tier,idx:pick.idx});
    });
    const take=actionButton('取所选筹码','go ct-confirm-take',()=>{
      const colors=move.coins.slice();if(!colors.length||colors.some(c=>(bank[c]||0)<1))return;
      send({op:'take',colors});
    });
    const double=actionButton('取同色 2 颗','ct-confirm-double',()=>{
      if(move.coins.length!==1||(bank[move.coins[0]]||0)<4)return;
      send({op:'take2',color:move.coins[0]});
    });
    const cancel=actionButton('取消选择','ct-confirm-cancel',()=>{
      if(!live()||move.busy)return;move.pick=null;move.coins=[];move.message='';refresh();
    });
    const sync=actionButton('刷新牌桌','ct-sync',()=>{
      if(!current()||move.syncing)return;
      move.syncing=true;refresh();
      const done=()=>{if(current()){move.syncing=false;refresh();}};
      try{Promise.resolve(gameAPI('sync',{room_id:roomId},true)).then(done,done);}catch(_e){done();}
    });
    const inspector=node('div','ct-card-inspector');inspector.hidden=true;
    inspector.setAttribute('role','dialog');inspector.setAttribute('aria-modal','true');
    inspector.setAttribute('aria-label','发展卡赏卡');
    const inspectBody=node('div','ct-inspect-body'),inspectClose=node('button','gbtn ct-inspect-close','返回牌桌');
    inspectClose.type='button';inspectClose.onclick=()=>{inspector.hidden=true;view.focus&&view.focus();};
    const inspectCard=node('div','ct-inspect-card');inspectBody.append(inspectClose,inspectCard);inspector.appendChild(inspectBody);table.appendChild(inspector);
    const view=actionButton('放大赏卡','ct-view-card',()=>{
      const card=getCard(move.pick);if(!live()||!card)return;
      inspectCard.innerHTML='';inspectCard.appendChild(development(card,{}));inspector.hidden=false;
      inspectClose.focus&&inspectClose.focus();
    });
    function refresh(){
      const can=enabled(),pick=move.pick,card=getCard(pick),coins=move.coins;
      notice.textContent=move.message||(move.busy?'正在提交这一手…':card?
        (pick.kind==='reserved'?'保留卡 · ':'已选 · ')+cardName(card,card.tier||pick.tier)
          +' · '+(Number(card.pts)||0)+' 声望'+(myTurn?(afford(card)?' · 可购买':' · 筹码不足'):' · 等待本人回合'):
        coins.length?'已选 '+coins.map(c=>gemNames[c]).join('、')+' · 确认后取 '+coins.length+' 颗':
        myTurn?'点选一张牌或银行筹码，再确认本手行动。':mine?'等待本人回合 · 可浏览卡牌和藏册':'观战中 · 仅展示公开牌桌');
      buy.hidden=!card;buy.disabled=!can||!card||!afford(card);
      reserve.hidden=!card||pick.kind!=='market';reserve.disabled=!can||reserved.length>=3;
      reserve.textContent=reserved.length>=3?'保留已满':'保留所选';
      take.hidden=!coins.length;take.disabled=!can;take.textContent='取 '+coins.length+' 颗筹码';
      double.hidden=coins.length!==1;double.disabled=!can||!coins.length||(bank[coins[0]]||0)<4;
      cancel.hidden=!card&&!coins.length;cancel.disabled=move.busy;
      view.hidden=!card;view.disabled=move.busy;
      sync.hidden=!move.busy&&!move.message;sync.disabled=!!move.syncing;
      for(const {button,color} of bankNodes){
        const on=coins.includes(color);button.classList.toggle('ct-coin-selected',on);
        if(color!=='g'){button.disabled=!can||(bank[color]||0)<=0;button.setAttribute('aria-pressed',String(on));}
      }
      for(const {wrap,kind,tier,idx,card:c} of cardNodes){
        const on=!!pick&&pick.kind===kind&&pick.tier===tier&&pick.idx===idx&&pick.identity===cardIdentity(c);
        wrap.classList.toggle('ct-selected',on);wrap.children[0].setAttribute('aria-pressed',String(on));
      }
    }
    const players=node('section','ct-gem-players');players.setAttribute('aria-label','玩家账目');
    for(const uid of s.players||[]){
      const panel=node('article','ct-player'+(uid===me?' ct-player-me':''));
      panel.append(node('strong','ct-player-name',gnick(uid)+(uid===me?' · 你':'')),
        node('b','ct-player-score',String(Number((s.score||{})[uid])||0)+' 声望'));
      for(const [label,values] of [['永久',(s.discount||{})[uid]||{}],['筹码',(s.tokens||{})[uid]||{}]]){
        const wallet=node('div','ct-wallet');wallet.appendChild(node('small','',label));
        for(const color of label==='永久'?gemColors:[...gemColors,'g']){
          const value=Number(values[color])||0;
          const item=node('span','ct-wallet-item');item.title=gemNames[color]+' '+value;
          item.append(jewel(color),node('b','',String(value)));wallet.appendChild(item);
        }
        panel.appendChild(wallet);
      }
      players.appendChild(panel);
    }
    table.appendChild(players);
    personal(table,s,afford,send,{
      select:(idx,card)=>select('reserved',0,idx,card),
      selected:(idx,card)=>!!move.pick&&move.pick.kind==='reserved'&&move.pick.idx===idx&&move.pick.identity===cardIdentity(card)
    });
    const reservedGrid=table.children[table.children.length-1];
    if(mine&&reservedGrid){
      // Keep selection updates local, preserving phone scroll position and focus.
      const findReserved=e=>{
        if(e.className&&e.className.split(' ').includes('ct-reserved-grid')){
          Array.from(e.children).forEach((wrap,idx)=>cardNodes.push({wrap,kind:'reserved',tier:0,idx,card:reserved[idx]}));
        }else for(const child of e.children||[])findReserved(child);
      };findReserved(reservedGrid);
    }
    table.onkeydown=e=>{if(e.key==='Escape'){
      if(!inspector.hidden){inspector.hidden=true;view.focus&&view.focus();}
      else if(!move.busy){move.pick=null;move.coins=[];refresh();}
    }};
    refresh();
  }
  function role(value,label,interactive){
    const card=node(interactive?'button':'article','ct-role');if(interactive)card.type='button';
    card.dataset.value=String(value);const image=art('lovelove-court.webp',value-1,4,2,loveNames[value]);
    image.appendChild(node('b','ct-role-value',String(value)));
    card.append(image,node('strong','ct-card-name',loveNames[value]||('牌 '+value)));
    if(label)card.appendChild(node('span','ct-role-label',label));
    return card;
  }
  function lovelove(box,s){
    box.appendChild(gTitle('lovelove','情书 · 宫廷密语'));
    const table=node('div','ct-table ct-love');box.appendChild(table);
    const live=s.alive||[],me=state.uid,mine=owned('lovelove',s),pv=mine?(state.gpriv||{}):{};
    const myTurn=canAct('lovelove',s,s.cur)&&live.includes(me);
    const line=s.winner_uid!=null?'胜者 · '+gnick(s.winner_uid):(s.status==='ended'?'本局结束':'轮到 '+gnick(s.cur));
    table.appendChild(node('div','ct-turn',line+' · 牌堆剩 '+(s.deck_left||0)));
    table.appendChild(node('p','ct-members','存活：'+live.map(gnick).join('、')+'　出局：'+((s.dead||[]).map(gnick).join('、')||'无')));
    const valid=value=>Number.isInteger(value)&&value>=1&&value<=8;
    const hand=Number(pv.hand),drawn=myTurn?Number(pv.drawn):NaN;
    if(mine&&valid(hand)){
      const section=node('section','ct-love-private');table.appendChild(section);
      section.appendChild(node('h3','ct-section-title',myTurn?'选择要弃出的一张牌':'我的持牌 · 等待回合'));
      const cards=node('div','ct-love-hand');section.appendChild(cards);
      const choices=[{value:hand,label:'持牌'}];if(valid(drawn))choices.push({value:drawn,label:'新摸牌'});
      const forced=choices.length===2&&choices.some(c=>c.value===7)&&choices.some(c=>c.value===8);
      const controls=node('div','ct-love-controls'),note=node('p','ct-choice-note',myTurn?'先点选一张牌，再选择效果目标':'你的持牌仅自己可见');
      const targetLabel=node('label','','目标 '),targets=node('select','ct-love-target');
      const guessLabel=node('label','','护卫猜值 '),guess=node('select','ct-love-guess');
      const submit=node('button','gbtn go ct-love-submit','先选择要弃出的牌');submit.type='button';submit.disabled=true;
      let selected=null,submitted=false;
      function option(select,value,text){const o=node('option','',text);o.value=value;select.appendChild(o);}
      option(guess,'','请选择猜值');for(let value=1;value<=8;value++)option(guess,value,value+' · '+loveNames[value]);
      targetLabel.appendChild(targets);guessLabel.appendChild(guess);targetLabel.hidden=guessLabel.hidden=true;
      function readiness(){
        if(submitted)return {ready:false,label:'正在出牌…'};
        if(!selected)return {ready:false,label:'先选择要弃出的牌'};
        if(!canAct('lovelove',s,s.cur)||state.gpriv!==pv)return {ready:false,label:'等待本人回合'};
        if(forced&&selected.value!==7)return {ready:false,label:'必须弃出伯爵夫人'};
        const action={op:'discard',play:selected.value};
        if([1,2,3,5,6].includes(selected.value)){
          const target=Number(targets.value);
          if(targets.value===''||!Number.isInteger(target)||!live.includes(target)||(target===me&&selected.value!==5))
            return {ready:false,label:'先选目标'};
          action.target=target;
        }
        if(selected.value===1){
          const value=Number(guess.value);
          if(guess.value===''||!valid(value))return {ready:false,label:'再选猜值'};
          action.val=value;
        }
        return {ready:true,label:'弃出 '+loveNames[selected.value]+' · '+selected.value,action};
      }
      function updateReady(){const status=readiness();submit.disabled=!status.ready;submit.textContent=status.label;}
      targets.oninput=targets.onchange=updateReady;guess.oninput=guess.onchange=updateReady;
      const buttons=[];
      choices.forEach((choice,index)=>{
        const pick=role(choice.value,choice.label,myTurn);buttons.push(pick);cards.appendChild(pick);
        if(myTurn){pick.setAttribute('aria-pressed','false');pick.disabled=forced&&choice.value!==7;
          pick.onclick=()=>{
            if(!canAct('lovelove',s,s.cur)||state.gpriv!==pv||pick.disabled)return;
            selected=choice;buttons.forEach((button,i)=>{button.classList.toggle('ct-picked',i===index);button.setAttribute('aria-pressed',String(i===index));});
            note.textContent=loveEffects[choice.value];guess.value='';
            targets.innerHTML='';option(targets,'','请选择目标');
            live.forEach(uid=>{if(choice.value===5||uid!==me)option(targets,uid,gnick(uid)+(uid===me?'（自己）':''));});
            targetLabel.hidden=![1,2,3,5,6].includes(choice.value);guessLabel.hidden=choice.value!==1;
            updateReady();
          };
        }
      });
      if(forced)note.textContent='与公主同持时，必须弃出伯爵夫人';
      section.appendChild(note);
      if(myTurn){controls.append(targetLabel,guessLabel,submit);section.appendChild(controls);}
      submit.onclick=()=>{
        const status=readiness();if(!status.ready){updateReady();return;}
        submitted=true;updateReady();
        const request=gameAPI('action',{room_id:state.groom,action:status.action});
        const retry=()=>{if(submit.isConnected){submitted=false;updateReady();}};
        if(request&&typeof request.then==='function')request.then(result=>{if(result&&result.ok===false)retry();},retry);
      };
    }else table.appendChild(node('p','ct-empty',mine?'等待本人私有手牌':'观战中 · 仅展示公开牌'));
    const publicSection=node('section','ct-love-public');table.appendChild(publicSection);
    publicSection.appendChild(node('h3','ct-section-title','公开弃牌'));
    const discards=Array.isArray(s.discard)?s.discard:[],row=node('div','ct-love-discards');
    discards.forEach(item=>{const value=Number(item[1]);if(valid(value))row.appendChild(role(value,gnick(item[0]),false));});
    if(!discards.length&&valid(Number(s.table)))row.appendChild(role(Number(s.table),'桌面牌',false));
    if(!row.children.length)row.appendChild(node('p','ct-empty','尚无公开弃牌'));
    publicSection.appendChild(row);
  }
  return {cost,development,personal,patrons,owned,canAct,gemcity,lovelove};
})();
"""

WEB_CSS = r"""
#gmain:has(.ct-table){max-height:calc(90vh - 150px)}
.ct-table{color:var(--txt);font-size:12px;min-width:0}
.ct-section-title{font-size:12px;margin:9px 0 5px;line-height:1.45}
.ct-turn{font-weight:700;line-height:1.5}.ct-empty,.ct-members,.ct-choice-note{font-size:12px;line-height:1.5;margin:5px 0}
.ct-market-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-bottom:7px}
.ct-development{border:1px solid #b9afa1;background:#fffaf0;border-radius:8px;overflow:hidden;min-width:0;color:#253b39}
.ct-face{display:block;width:100%;padding:0;border:0;border-radius:0;text-align:left;font:inherit;cursor:default}
.ct-table .ct-face,.ct-table button.ct-face,.ct-table button.ct-face:disabled{background:#fffaf0;color:#253b39;opacity:1}
button.ct-face:enabled{cursor:pointer}.ct-affordable{border:2px solid #207965}
.ct-art{position:relative;aspect-ratio:1.15;background-color:#e7dfce;background-repeat:no-repeat;overflow:hidden}
.ct-no-art{display:flex;align-items:center;justify-content:center;padding:10px;box-sizing:border-box;font-weight:700;font-size:12px;color:#5b574d}
.ct-art-missing{background-image:none!important}.ct-card-head{position:absolute;inset:3px 3px auto;display:flex;align-items:flex-start;justify-content:space-between;gap:3px}
.ct-points,.ct-discount{display:inline-flex;align-items:center;gap:2px;background:#fff8e9;color:#263937;padding:2px 4px;border-radius:4px;font-size:11px;box-shadow:0 1px 3px #0003}
.ct-points{font-weight:800}.ct-card-name{display:block;padding:4px 5px 2px;line-height:1.25;font-size:11px;overflow-wrap:anywhere}
.ct-price{display:flex;gap:3px;align-items:flex-start;padding:2px 4px 4px;min-height:30px}.ct-price small{font-size:9px;color:#536359;white-space:nowrap}
.ct-cost{display:inline-flex;gap:2px 4px;flex-wrap:wrap;align-items:center;line-height:1.4}.ct-cost-chip{display:inline-flex;gap:1px;align-items:center;font-size:10px;color:#263937}
.ct-gem{font:normal 8px/13px sans-serif;display:inline-block;text-align:center;width:13px;height:13px;border-radius:50%;background:var(--gem-ink,#666);color:#fff;border:1px solid #0002;box-sizing:border-box}
.ct-gem-d{color:#233b4f}.ct-free{font-size:11px}.ct-buy-label{display:block;text-align:center;font-size:10px;font-weight:700;padding:3px;background:#ede7d9;color:#554836}
.ct-affordable .ct-buy-label{background:#207965;color:#fff}.ct-table button.ct-reserve{display:block;width:100%;min-height:28px;border:0;border-top:1px solid #c9c0ae;background:#f4ead6;color:#31443f;font-size:11px;font-weight:700;cursor:pointer}
.ct-table button.ct-reserve:disabled{background:#f4ead6;color:#817769;cursor:default}.ct-face:focus-visible,.ct-reserve:focus-visible,.ct-role:focus-visible{outline:3px solid #d88e20;outline-offset:-3px}
.ct-personal{margin:6px 0}.ct-album{border:1px solid var(--line,#c9c0ae);border-radius:8px;padding:7px 9px;background:var(--card)}
.ct-album summary{cursor:pointer;font-weight:700;font-size:12px}.ct-album-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:8px;max-height:min(55vh,500px);overflow:auto;overscroll-behavior:contain}
.ct-album-grid .ct-card-name{font-size:13px}.ct-reserved-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
.ct-album-grid[hidden],.ct-album-view[hidden]{display:none}.ct-album-view{max-width:420px;margin:9px auto}.ct-album-view .ct-card-name{font-size:16px;padding:7px 9px}.ct-album-view .ct-price{padding:7px 9px}.ct-album-view .ct-cost-chip{font-size:13px}.ct-album-view .ct-gem{width:17px;height:17px;font-size:10px;line-height:17px}.ct-album-view .ct-points,.ct-album-view .ct-discount{font-size:14px}.ct-view-label{display:block;font-size:11px;text-align:center;padding:4px;color:#155b50;background:#e1efe8}.ct-view-note{font-size:12px;line-height:1.4}
.ct-patrons{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}.ct-patron{background:#fff8e9;color:#263937;border:1px solid #b7a27b;border-radius:7px;overflow:hidden}
.ct-patron .ct-card-name{font-size:10px;padding:3px}.ct-patron .ct-cost{padding:3px;gap:2px}.ct-patron-status{display:block;padding:2px 3px;font-size:9px;color:#5b574d}
.ct-gem-tools{position:sticky;top:0;z-index:3;background:var(--card,#fffaf0);padding:4px 0 5px;border-bottom:1px solid var(--line,#c9c0ae)}
.ct-table button.ct-bank-chip{color:var(--txt);font:inherit}.ct-table button.ct-bank-chip:disabled{color:var(--dim)}
.ct-wallet{font-size:11px;line-height:1.7}.ct-legacy{margin-top:8px}.ct-legacy summary{font-size:12px;cursor:pointer}
.ct-love-hand{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-width:400px;margin:7px auto}
.ct-table .ct-role,.ct-table button.ct-role,.ct-table button.ct-role:disabled{padding:0;background:#fff9ed;color:#2e3943;border:1px solid #b7a27b;border-radius:9px;overflow:hidden;text-align:center;font:inherit;min-width:0}
button.ct-role{cursor:pointer}button.ct-role:disabled{opacity:1;cursor:default}.ct-role .ct-art{aspect-ratio:4/5}.ct-role-value{position:absolute;top:5px;left:5px;background:#fff7df;color:#473523;border-radius:50%;width:24px;height:24px;font:bold 17px/24px serif;box-shadow:0 1px 4px #0005}
.ct-role .ct-card-name{font-size:14px;padding-top:6px}.ct-role-label{display:block;font-size:11px;padding:2px 5px 6px}.ct-table .ct-role.ct-picked{border:3px solid #167565;box-shadow:0 0 0 2px #16756533}
.ct-picked .ct-role-label{background:#167565;color:#fff}.ct-love-controls{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:8px 0}
.ct-love-controls label{display:flex;gap:4px;align-items:center;font-size:12px}.ct-love-controls label[hidden]{display:none}
.ct-love-controls select{max-width:100%;min-height:34px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--txt)}
.ct-love-submit{min-height:38px}.ct-love-discards{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px}.ct-love-discards .ct-card-name{font-size:10px}.ct-love-discards .ct-role-label{font-size:9px;overflow-wrap:anywhere}
.ct-love-discards .ct-role-value{width:18px;height:18px;font-size:13px;line-height:18px;top:3px;left:3px}
@media(max-width:560px){.ct-album-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ct-market-row{gap:4px}.ct-card-name{font-size:10px;padding-inline:3px}.ct-price{padding-inline:3px;gap:2px;min-height:32px}.ct-price small{font-size:8px}.ct-cost-chip{font-size:9px}.ct-card-head{inset:3px 2px auto}.ct-points,.ct-discount{font-size:9px;padding:2px}.ct-love-discards{grid-template-columns:repeat(4,minmax(0,1fr))}.ct-love-controls{align-items:stretch}.ct-love-submit{width:100%}}

/* Jewel table. All overrides are scoped so the Love Letter court keeps its layout. */
#gpanel .card:has(.ct-gemcity){width:min(1120px,calc(100vw - 16px));box-sizing:border-box;padding:12px}
#gmain:has(.ct-gemcity){max-height:calc(92vh - 130px)}
.ct-gemcity{--ct-brass:#ddbd72;--ct-paper:#f9f0da;color:var(--ct-paper);padding:12px;box-sizing:border-box;border:1px solid #a48958;border-radius:12px;
  background:radial-gradient(ellipse at 35% 20%,#624a57 0,#42313e 52%,#2b252f 100%);box-shadow:inset 0 0 35px #17121b88;isolation:isolate}
.ct-table-top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:9px}
.ct-gemcity .ct-turn{color:#fff3d0;font-size:14px}.ct-table-goal{font-size:11px;color:#d5c6b2}
.ct-gem-scene{display:grid;grid-template-columns:minmax(0,min(720px,calc(81.78dvh - 142px))) 174px;gap:15px;align-items:start;justify-content:center}
.ct-market{min-width:0;display:flex;flex-direction:column;gap:10px}
.ct-tier{display:flex;gap:9px;align-items:center;min-width:0}
.ct-gemcity .ct-market-row{flex:1;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0;min-width:0}
.ct-tier-deck{width:42px;flex:0 0 42px;align-self:stretch;max-height:170px;border:1px solid #ceae68;border-radius:6px;box-sizing:border-box;
  background:linear-gradient(135deg,#417663,#1b4239);box-shadow:3px 3px 0 #d4bd83,5px 4px 0 #281d22;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:#f5df9f}
.ct-tier-2{background:linear-gradient(135deg,#bc9f5a,#69532f)}.ct-tier-3{background:linear-gradient(135deg,#59729d,#2b3656)}
.ct-tier-deck>b{font:bold 28px/1 Georgia,serif}.ct-tier-level{font-size:7px;letter-spacing:2px}.ct-deck-count{font-size:12px;font-weight:700}
.ct-gemcity .ct-development{position:relative;border:1px solid #e2c68b;border-radius:7px;background:#3a2930;overflow:hidden;box-shadow:0 3px 5px #140c18aa;min-width:0}
.ct-gemcity .ct-development.ct-affordable{border:1px solid #ead59e}
.ct-gemcity .ct-development.ct-selected{outline:3px solid #ffe184;outline-offset:1px;box-shadow:0 0 12px #ffde7a66}
.ct-gemcity .ct-face,.ct-gemcity button.ct-face,.ct-gemcity button.ct-face:disabled{display:block;width:100%;padding:0;border:0;border-radius:0;background:#4e5558;color:#fff;opacity:1}
.ct-gemcity button.ct-face{cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.ct-gemcity .ct-face:focus-visible{outline:3px solid #fff2c1;outline-offset:-3px}
.ct-gemcity .ct-art{position:relative;aspect-ratio:2/3;padding:0;min-width:0;background-color:#4b5860;isolation:isolate}
.ct-gemcity .ct-art:after{content:'';position:absolute;inset:0;z-index:0;pointer-events:none;background:linear-gradient(180deg,#0007 0,transparent 27%,transparent 48%,#000a 100%)}
.ct-gemcity .ct-card-head{inset:5px 5px auto;z-index:2;pointer-events:none}
.ct-gemcity .ct-points{background:none;padding:0;border:0;border-radius:0;box-shadow:none;color:#fff8dd;font:bold clamp(20px,2.7vw,34px)/1 Georgia,serif;text-shadow:0 2px 2px #100b0a,1px 0 #100b0a,-1px 0 #100b0a}
.ct-gemcity .ct-discount{margin-left:auto;background:none;padding:0;box-shadow:none;border:0}
.ct-jewel{display:inline-block;width:28px;height:28px;flex:0 0 auto;background-color:transparent;background-repeat:no-repeat;vertical-align:middle;filter:drop-shadow(0 1px 1px #0009)}
.ct-jewel-core{display:none}.ct-jewel.ct-art-missing .ct-jewel-core{display:block;width:76%;height:76%;margin:12%;background:#333;box-shadow:0 0 0 1px #fff}
.ct-jewel-o .ct-jewel-core{background:#151515;border-radius:3px}.ct-jewel-d .ct-jewel-core{background:#f4fbff;clip-path:polygon(50% 0,100% 45%,50% 100%,0 45%)}
.ct-jewel-r .ct-jewel-core{background:#c91832;clip-path:polygon(28% 0,72% 0,100% 28%,100% 72%,72% 100%,28% 100%,0 72%,0 28%)}
.ct-jewel-e .ct-jewel-core{background:#0d9668;clip-path:polygon(20% 0,80% 0,100% 20%,100% 80%,80% 100%,20% 100%,0 80%,0 20%)}
.ct-jewel-s .ct-jewel-core{background:#225ac5;border-radius:50%}.ct-jewel-g .ct-jewel-core{background:#e8ba43;border-radius:50%}
.ct-gemcity .ct-art>.ct-jewel{display:none}
.ct-gemcity .ct-neutral>.ct-jewel,.ct-gemcity .ct-art-missing>.ct-jewel{display:block;position:absolute;width:65%;height:auto;aspect-ratio:1;left:18%;top:20%;opacity:.72;filter:drop-shadow(0 6px 9px #0008)}
.ct-neutral-o{background:radial-gradient(ellipse at 30% 20%,#656565,#222)}.ct-neutral-d{background:radial-gradient(ellipse at 30% 20%,#a2bfce,#485b69)}
.ct-neutral-r{background:radial-gradient(ellipse at 30% 20%,#a64a52,#3b2029)}.ct-neutral-e{background:radial-gradient(ellipse at 30% 20%,#5b8c76,#163a34)}
.ct-neutral-s{background:radial-gradient(ellipse at 30% 20%,#5b7da7,#233448)}
.ct-gemcity .ct-development .ct-card-name{position:absolute;inset:auto 3px 4px;z-index:2;color:#fff8e4;text-shadow:0 1px 2px #000;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  font-size:clamp(10px,1.1vw,13px);line-height:1.2;text-align:center;padding:0;pointer-events:none}
.ct-gemcity .ct-development .ct-jewel-cost{position:absolute;left:5px;bottom:24px;z-index:2;display:flex;flex-direction:column;gap:4px;pointer-events:none}
.ct-gemcity .ct-development .ct-cost-many{display:grid;grid-template-columns:repeat(2,min-content);gap:4px}
.ct-price-coin{position:relative;display:inline-grid;place-items:center;width:25px;height:25px;border-radius:50%;box-sizing:border-box;border:1px solid #fff8;
  color:#fff;background:#222;box-shadow:0 1px 2px #0009;isolation:isolate;vertical-align:middle}
.ct-price-coin b{position:relative;z-index:1;font:bold 16px/1 Georgia,serif;text-shadow:0 1px 1px #0006}
.ct-coin-o{background:#202020}.ct-coin-d{background:#f2f6f4;border-color:#74838c;color:#17272d}
.ct-coin-r{background:#ba273c}.ct-coin-e{background:#16724e}.ct-coin-s{background:#215b9f}
.ct-coin-facet{position:absolute;width:67%;height:67%;top:13%;left:15%;background:#fff2;transform:rotate(45deg);border:1px solid #fff2;z-index:0}
.ct-gemcity .ct-free{display:inline-grid;place-items:center;width:21px;height:21px;background:#fff2;border:1px solid #fff8;border-radius:50%;color:#fff;font-size:12px}
.ct-card-empty{aspect-ratio:2/3;border:1px dashed #c1a77b66;border-radius:7px;display:grid;place-items:center;color:#cfbfa3;font-size:11px}
.ct-gem-aside{min-width:0;display:flex;flex-direction:column;gap:12px}
.ct-gemcity .ct-section-title{color:#eed5a4;font-size:12px;margin:0 0 6px;letter-spacing:1px}
.ct-bank-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.ct-gemcity .ct-bank-chip,.ct-gemcity button.ct-bank-chip{min-width:0;min-height:58px;border:1px solid #d4b37766;border-radius:50% 50% 10px 10px;background:#201a2288;color:#f9e9c7;
  display:grid;grid-template-columns:1fr auto;align-items:center;justify-items:center;gap:2px;padding:5px 7px;font:inherit;box-sizing:border-box;position:relative}
.ct-gemcity button.ct-bank-chip:disabled{color:#d0bfaa;opacity:.6;cursor:default}.ct-gemcity button.ct-bank-chip:enabled{cursor:pointer;touch-action:manipulation}
.ct-gemcity button.ct-bank-chip{-webkit-tap-highlight-color:transparent}
.ct-bank-chip .ct-jewel{width:32px;height:32px}.ct-bank-count{font:bold 18px/1 Georgia,serif;color:#f9e9c7}.ct-bank-name{grid-column:1/-1;font-size:10px;white-space:nowrap}
.ct-gemcity .ct-bank-chip.ct-coin-selected,.ct-gemcity button.ct-bank-chip.ct-coin-selected{background:#897145;border:2px solid #ffe296;box-shadow:0 0 8px #edc86e88}
.ct-gemcity .ct-patrons{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.ct-gemcity .ct-patron{position:relative;border:1px solid #ba975b;background:#271f27;border-radius:6px;box-shadow:0 2px 4px #0006}
.ct-gemcity .ct-patron .ct-art{aspect-ratio:1.05}.ct-gemcity .ct-patron .ct-card-name{position:absolute;inset:auto 2px 2px;color:#fff1cf;text-shadow:0 1px #000;padding:0;font-size:9px;z-index:1;text-align:center}
.ct-patron-points{position:absolute;left:3px;top:2px;z-index:1;color:#fff4ce;font:bold 22px/1 Georgia,serif;text-shadow:0 1px #000}
.ct-gemcity .ct-patron>.ct-jewel-cost{display:flex;flex-direction:row;justify-content:center;gap:3px;padding:4px 2px;min-height:20px}
.ct-gemcity .ct-patron .ct-price-coin{width:18px;height:18px}.ct-gemcity .ct-patron .ct-price-coin b{font-size:12px}
.ct-patron-ready{outline:2px solid #ffe296;outline-offset:1px}
.ct-gemcity .ct-gem-tools{position:sticky;top:auto;bottom:0;z-index:4;min-height:38px;margin-top:10px;padding:7px 9px;border:1px solid #a48a5e;border-radius:8px;
  color:#fff2d2;background:#2e2731f5;box-shadow:0 -3px 10px #15101966}
.ct-gem-notice{font-size:12px;line-height:1.6}.ct-gem-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:5px}
.ct-gemcity .ct-gem-actions button{min-height:40px;padding:6px 12px;font-size:12px;border:1px solid #ad9364;background:#f0e2c0;color:#382d32;border-radius:6px}
.ct-gemcity .ct-gem-actions button.go{background:#b69a55;color:#171b20;border-color:#f8dc98;font-weight:700}
.ct-gemcity .ct-gem-actions button:disabled{opacity:.5;cursor:default}.ct-gem-actions button[hidden]{display:none}
.ct-gem-players{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.ct-player{flex:1 1 205px;min-width:0;position:relative;background:#1a20267a;border:1px solid #b9a17d66;border-radius:7px;padding:7px}
.ct-player-me{border-color:#e7c57c;background:#2b333b99}.ct-player-name{font-size:12px;color:#f6e6c6}.ct-player-score{float:right;font-size:11px;color:#ffe2a2}
.ct-gemcity .ct-wallet{display:flex;gap:5px;align-items:center;margin-top:4px;line-height:1.25;font-size:11px}
.ct-wallet>small{font-size:10px;color:#bfae97}.ct-wallet-item{display:inline-flex;align-items:center;gap:1px}.ct-wallet-item .ct-jewel{width:17px;height:17px}.ct-wallet-item b{font-size:11px;font-weight:500}
.ct-gemcity .ct-personal{margin:10px 0 0}.ct-gemcity .ct-album{padding:8px;background:#251f28;border-color:#ac9367;color:#f3e3c2}
.ct-gemcity .ct-album summary{font-size:12px;line-height:1.6}.ct-gemcity .ct-album-grid{grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;max-height:450px}
.ct-gemcity .ct-album-grid .ct-view-label{display:none}.ct-gemcity .ct-album-view{max-width:260px}
.ct-gemcity .ct-reserved-grid{grid-template-columns:repeat(3,minmax(0,150px));gap:10px;margin-top:7px}
.ct-gemcity .ct-personal>.ct-section-title{margin-top:10px}.ct-gemcity .ct-view-note,.ct-gemcity .ct-empty{color:#dfd0b9}
.ct-card-inspector{position:fixed;inset:0;background:#140f19cf;z-index:101;display:flex;align-items:center;justify-content:center;padding:18px;box-sizing:border-box}
.ct-card-inspector[hidden]{display:none}.ct-inspect-body{display:flex;flex-direction:column;gap:10px;max-width:290px;width:70vw;max-height:90vh;overflow:auto}
.ct-inspect-close{align-self:center}.ct-inspect-card .ct-development .ct-card-name{font-size:16px}.ct-inspect-card .ct-development .ct-jewel-cost{bottom:32px;gap:7px}
.ct-inspect-card .ct-price-coin{width:34px;height:34px}.ct-inspect-card .ct-price-coin b{font-size:21px}.ct-inspect-card .ct-discount .ct-jewel{width:48px;height:48px}
.ct-inspect-card .ct-points{font-size:44px}
@media(min-width:761px) and (max-height:850px){
  .ct-gemcity .ct-gem-tools{position:static}
  .ct-bank-row,.ct-gemcity .ct-patrons{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}
  .ct-gemcity .ct-bank-chip,.ct-gemcity button.ct-bank-chip{min-height:46px;padding:3px;gap:1px;border-radius:10px}
  .ct-bank-chip .ct-jewel{width:25px;height:25px}.ct-bank-count{font-size:15px}.ct-bank-name{font-size:8px}
  .ct-gemcity .ct-patron .ct-card-name{display:none}.ct-gemcity .ct-patron>.ct-jewel-cost{gap:1px;padding:3px 1px}
  .ct-gemcity .ct-patron .ct-price-coin{width:15px;height:15px}.ct-gemcity .ct-patron .ct-price-coin b{font-size:11px}
}
@media(max-width:760px){
  #gpanel .card:has(.ct-gemcity){padding:8px}#gmain:has(.ct-gemcity){max-height:calc(94vh - 110px)}
  .ct-gemcity{padding:7px;border-radius:9px}.ct-table-top{margin-bottom:7px}.ct-table-goal{font-size:9px}.ct-gemcity .ct-turn{font-size:12px}
  .ct-gem-scene{display:block}.ct-market{gap:8px}.ct-tier{gap:6px}.ct-tier-deck{flex-basis:24px;width:24px;gap:6px;border-radius:4px;box-shadow:2px 2px 0 #b7a078}
  .ct-tier-deck>b{font-size:18px}.ct-tier-level{letter-spacing:0;font-size:5px}.ct-deck-count{font-size:10px}
  .ct-gemcity .ct-market-row{gap:5px}.ct-gemcity .ct-development{border-radius:5px}
  .ct-gemcity .ct-card-head{inset:3px 3px auto}.ct-discount .ct-jewel{width:23px;height:23px}
  .ct-gemcity .ct-development .ct-jewel-cost{left:3px;bottom:18px;gap:3px}.ct-gemcity .ct-development .ct-cost-many{gap:3px}
  .ct-price-coin{width:20px;height:20px}.ct-price-coin b{font-size:14px}.ct-gemcity .ct-development .ct-card-name{font-size:9px;bottom:3px}
  .ct-gem-aside{margin-top:12px;gap:10px}.ct-bank-row{grid-template-columns:repeat(6,minmax(0,1fr));gap:5px}
  .ct-gemcity .ct-bank-chip,.ct-gemcity button.ct-bank-chip{min-height:61px;padding:4px 2px;grid-template-columns:1fr;border-radius:10px;gap:1px}
  .ct-bank-chip .ct-jewel{width:31px;height:31px}.ct-bank-count{position:absolute;right:1px;top:22px;background:#27212e;border-radius:8px;min-width:17px;font-size:14px;line-height:17px}
  .ct-bank-name{font-size:9px}.ct-gemcity .ct-patrons{grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}
  .ct-gemcity .ct-patron .ct-art{aspect-ratio:1.03}.ct-gemcity .ct-patron .ct-card-name{display:none}
  .ct-gemcity .ct-patron>.ct-jewel-cost{gap:2px;padding:4px 1px}.ct-gemcity .ct-patron .ct-price-coin{width:17px;height:17px}
  .ct-gemcity .ct-gem-tools{padding:6px;margin-top:8px}.ct-gem-notice{font-size:11px}.ct-gemcity .ct-gem-actions button{min-height:44px;padding:5px 10px;font-size:12px}
  .ct-player{flex-basis:145px;padding:5px}.ct-gemcity .ct-wallet{gap:3px}.ct-wallet-item .ct-jewel{width:14px;height:14px}
  .ct-wallet-item b{font-size:10px}.ct-wallet>small{font-size:9px}.ct-gemcity .ct-album-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
  .ct-gemcity .ct-reserved-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
}
"""
