"""Gem City and Love Letter presentation; rules and private delivery stay in Hub."""

WEB_JS = r"""
const CardTableWeb = (() => {
  const inks={o:'#424550',d:'#b6c7d7',r:'#b83d49',e:'#247c5e',s:'#336ab4',g:'#b78025'};
  const labels={o:'黑',d:'白',r:'红',e:'绿',s:'蓝',g:'金'};
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
  function development(card,options){
    options=options||{};const tier=Number(card.tier)||options.tier||1;
    const title=card.title||((tier===1?'矿场':tier===2?'工坊':'商贸城市')+' · '+(labels[card.disc]||card.disc||'发展卡'));
    const wrap=node('article','ct-development');wrap.dataset.title=title;
    const face=node(options.onBuy||options.onView?'button':'div','ct-face');
    if(options.onBuy){face.type='button';face.disabled=!options.canBuy;face.onclick=options.onBuy;face.setAttribute('aria-label','购买 '+title);}
    else if(options.onView){face.type='button';face.onclick=options.onView;face.setAttribute('aria-label','欣赏 '+title);}
    const image=art('gemcity-tier'+tier+'.webp',card.art,4,5,title);
    const head=node('div','ct-card-head');head.append(node('b','ct-points',(card.pts||0)+' 分'));
    const discount=node('span','ct-discount');discount.style.setProperty('--gem-ink',inks[card.disc]||'#666');
    discount.title='永久折扣 '+(labels[card.disc]||card.disc)+' +1';discount.append(node('i','ct-gem ct-gem-'+card.disc,labels[card.disc]||card.disc),node('b','','+1'));
    head.appendChild(discount);image.appendChild(head);face.append(image,node('strong','ct-card-name',title));
    const price=node('div','ct-price');price.append(node('small','','费用'),cost(card.cost,options.colors));face.appendChild(price);
    if(options.onBuy){const label=node('span','ct-buy-label',options.canBuy?'点击购买':(options.myTurn?'筹码不足':'等待回合'));face.appendChild(label);wrap.classList.toggle('ct-affordable',!!options.canBuy);}
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
  function personal(box,s,afford,send){
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
    const identity=card=>[card.tier,card.art,card.title].join(':');
    function show(index,focus){
      if(!owned('gemcity',s)||!collection[index])return;
      const card=collection[index];state.ctViewedCard={context:key,index,identity:identity(card)};
      view.innerHTML='';const back=node('button','gbtn ct-album-back','返回卡册');back.type='button';
      back.onclick=()=>{state.ctViewedCard=null;view.hidden=true;grid.hidden=false;if(focus&&focus.focus)focus.focus();};
      view.append(back,node('p','ct-view-note','已购藏品 · '+(card.title||'发展卡')),development(card,{colors:s.colors}));
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
      reserved.forEach((card,index)=>row.appendChild(development(card,{colors:s.colors,myTurn,canBuy:myTurn&&afford(card),onBuy:()=>send({op:'buy_res',idx:index})})));
      section.appendChild(row);
    }
    box.appendChild(section);
  }
  function patrons(box,s,discount){
    const section=node('section','ct-patrons-section');section.appendChild(node('h3','ct-section-title','贵宾 · 发展卡折扣达到门槛即可获邀'));
    const row=node('div','ct-patrons');
    (s.nobles||[]).forEach((threshold,index)=>{
      const title=(s.noble_titles||[])[index]||('贵宾 '+(index+1));
      const card=node('article','ct-patron');const image=art('gemcity-patrons.webp',(s.noble_art||[])[index],5,1,title);
      card.append(image,node('strong','ct-card-name',title),cost(threshold,s.colors));
      const ready=Object.entries(threshold).every(([color,count])=>(discount[color]||0)>=count);
      card.appendChild(node('small','ct-patron-status',ready?'门槛已达':'门槛'));row.appendChild(card);
    });
    section.appendChild(row);box.appendChild(section);
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
      let selected=null;
      function option(select,value,text){const o=node('option','',text);o.value=value;select.appendChild(o);}
      option(guess,'','不猜值');for(let value=1;value<=8;value++)option(guess,value,value+' · '+loveNames[value]);
      targetLabel.appendChild(targets);guessLabel.appendChild(guess);targetLabel.hidden=guessLabel.hidden=true;
      const buttons=[];
      choices.forEach((choice,index)=>{
        const pick=role(choice.value,choice.label,myTurn);buttons.push(pick);cards.appendChild(pick);
        if(myTurn){pick.setAttribute('aria-pressed','false');pick.disabled=forced&&choice.value!==7;
          pick.onclick=()=>{
            if(!canAct('lovelove',s,s.cur)||state.gpriv!==pv||pick.disabled)return;
            selected=choice;buttons.forEach((button,i)=>{button.classList.toggle('ct-picked',i===index);button.setAttribute('aria-pressed',String(i===index));});
            note.textContent=loveEffects[choice.value];submit.disabled=false;submit.textContent='弃出 '+loveNames[choice.value]+' · '+choice.value;
            targets.innerHTML='';option(targets,'','不指定目标');
            live.forEach(uid=>{if(choice.value===5||uid!==me)option(targets,uid,gnick(uid)+(uid===me?'（自己）':''));});
            targetLabel.hidden=![1,2,3,5,6].includes(choice.value);guessLabel.hidden=choice.value!==1;
          };
        }
      });
      if(forced)note.textContent='与公主同持时，必须弃出伯爵夫人';
      section.appendChild(note);
      if(myTurn){controls.append(targetLabel,guessLabel,submit);section.appendChild(controls);}
      submit.onclick=()=>{
        if(!selected||!canAct('lovelove',s,s.cur)||state.gpriv!==pv)return;
        const action={op:'discard',play:selected.value};
        if(!targetLabel.hidden&&targets.value!=='')action.target=Number(targets.value);
        if(!guessLabel.hidden&&guess.value!=='')action.val=Number(guess.value);
        gameAPI('action',{room_id:state.groom,action});
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
  return {cost,development,personal,patrons,owned,canAct,lovelove};
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
"""
