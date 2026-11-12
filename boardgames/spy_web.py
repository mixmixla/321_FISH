"""Illustrated Who Is the Spy tabletop on the production game panel."""

from boardgames.cards_pending_web import CARDS_PENDING_JS

WEB_JS = CARDS_PENDING_JS + r"""
const SpyWeb = (() => {
  const tables = new Map();
  const colors = ['#63ad9e', '#a88bd4', '#d6a55e', '#7fae82', '#79a6cb', '#cc8a9d'];
  const art = '/game-art/spy-';
  const seatsPerPage = colors.length;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function button(className, text, label, click) {
    const node = element('button', className, text);
    node.type = 'button';
    if (label) node.setAttribute('aria-label', label);
    node.onclick = click;
    return node;
  }

  function validPrivate(frame, privateFrame) {
    const room = frame?.room;
    const publicFrame = frame?.state;
    const previous = state.gpriv;
    return Boolean(state.token && room?.game === 'spy' && room.room_id === state.groom
      && room.status === 'playing' && publicFrame?.status !== 'reveal'
      && room.players.includes(state.uid) && !room.spectators.includes(state.uid)
      && publicFrame?.alive.includes(state.uid) && privateFrame?.game === 'spy'
      && privateFrame.owner_uid === state.uid && privateFrame.round_key === publicFrame.round_key
      && Number.isInteger(privateFrame.revision) && privateFrame.revision <= publicFrame.revision
      && !(previous?.game === 'spy' && previous.round_key === privateFrame.round_key
        && previous.owner_uid === state.uid && previous.revision > privateFrame.revision)
      && ['civilian', 'spy'].includes(privateFrame.role) && typeof privateFrame.word === 'string');
  }

  function stalePublic(previous, next) {
    if (previous?.room?.game !== 'spy' || previous.room_id !== next.room_id) return false;
    if (previous.room.round !== next.room.round) return previous.room.round > next.room.round;
    if (previous.room.status === 'created' && next.room.status !== 'created') return true;
    if (previous.room.status === 'ended' && next.room.status === 'playing') return true;
    return previous.state?.round_key === next.state?.round_key
      && previous.state?.revision > next.state?.revision;
  }

  function picture(file, width, height) {
    const image = element('img', 'spy-image');
    image.src = art + file + '.webp';
    image.alt = '';
    image.width = width;
    image.height = height;
    return image;
  }

  function mount(main) {
    const root = element('section', 'spy-board');
    const stage = element('div', 'spy-stage');
    const seats = element('div', 'spy-seats');
    const paper = element('div', 'spy-paper');
    const copy = element('div', 'spy-paper-copy');
    const form = element('form', 'spy-compose');
    const input = element('input', 'spy-input');
    input.placeholder = '写下一句描述';
    input.setAttribute('aria-label', '描述你的词');
    input.maxLength = 200;
    input.autocomplete = 'off';
    const stamp = element('button', 'spy-seal', '发言');
    stamp.type = 'submit';
    stamp.setAttribute('aria-label', '发送描述');
    form.append(input, stamp);
    const feedback = element('div', 'spy-action-note');
    feedback.setAttribute('role', 'status');
    paper.append(copy, form, feedback);
    const rail = element('aside', 'spy-rail');
    const navigation = element('div', 'spy-seat-nav');
    stage.append(picture('roundtable', 768, 768), paper, seats);
    root.append(stage, navigation, rail);
    main.replaceChildren(root);
    const view = {root, stage, seats, copy, form, input, stamp, feedback, rail, navigation, composing:false};
    input.addEventListener('compositionstart', () => { view.composing = true; });
    input.addEventListener('compositionend', () => { view.composing = false; });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && (event.isComposing || view.composing || event.keyCode === 229)) event.preventDefault();
    });
    return view;
  }

  function positions(length) {
    if (length === 1) return [[50, 16]];
    if (length === 2) return [[13, 48], [87, 48]];
    if (length === 3) return [[50, 14], [87, 68], [13, 68]];
    if (length === 4) return [[14, 25], [86, 25], [86, 74], [14, 74]];
    if (length === 5) return [[50, 13], [86, 32], [84, 74], [16, 74], [14, 32]];
    return [[16, 21], [84, 21], [88, 47], [84, 74], [16, 74], [12, 47]];
  }

  function tableFor(room, publicFrame, uid, token) {
    const id = JSON.stringify([uid, room.room_id, room.round, publicFrame.round_key]);
    let table = tables.get(id);
    if (!table) {
      table = {page: 0, hidden: false, tab: 'clues', clue: null, view: null, token, revision: -1};
      if (tables.size >= 6) tables.delete(tables.keys().next().value);
      tables.set(id, table);
    }
    if (table.token !== token) {
      table.hidden = true;
      table.view = null;
      table.token = token;
    }
    return table;
  }

  function waiting(main, room) {
    const stage = element('section', 'spy-board spy-waiting');
    stage.append(picture('roundtable', 768, 768));
    const paper = element('div', 'spy-paper');
    paper.append(element('h3', '', '等待入席'),
      element('p', '', room.players.length + ' 人入席 · 4 人即可开始'));
    stage.append(paper);
    main.replaceChildren(stage);
  }

  function headerButton(envelope, op, label) {
    const room = envelope.room;
    const {token, uid, groom: roomId} = state;
    const round = room.round;
    const control = button('gbtn', label, null, () => {
      if (!control.isConnected || !token || state.token !== token || state.uid !== uid
          || state.groom !== roomId || state.gst !== envelope || envelope.room !== room
          || room.room_id !== roomId || room.round !== round || room.game !== 'spy') return;
      if (op === 'start' && (room.status !== 'created' || room.owner_uid !== uid)) return;
      if (!room.players.includes(uid) && !room.spectators.includes(uid)) return;
      gameAPI(op, {room_id:roomId}, op === 'leave').catch(() => showStatus('连接中断，请重试'));
    });
    return control;
  }

  function render(main, envelope) {
    const room = envelope.room;
    const uid = state.uid;
    const token = state.token;
    if (!token || room.room_id !== state.groom || envelope.room_id !== room.room_id
        || (!room.players.includes(uid) && !room.spectators.includes(uid))) {
      main.replaceChildren(element('p', 'spy-syncing', '正在同步牌桌…'));
      return;
    }
    let publicFrame = envelope.state;
    const live = room.status === 'playing';
    if (room.status === 'created') {
      const retained = [...tables.entries()].find(([id, table]) =>
        table.token === token && table.result
        && id === JSON.stringify([uid, room.room_id, room.round, table.result.round_key]));
      if (retained) publicFrame = retained[1].result;
      else {
        waiting(main, room);
        return;
      }
    }
    if (!publicFrame?.round_key) {
      main.replaceChildren(element('p', 'spy-syncing', '正在同步牌桌…'));
      return;
    }
    const table = tableFor(room, publicFrame, uid, token);
    const {status, revision, clue_round: clueRound, round_key: roundKey} = publicFrame;
    const roomId = room.room_id;
    const round = room.round;
    const privateFrame = state.gpriv;
    const hasWord = live && validPrivate(envelope, privateFrame);
    const present = publicFrame.players.includes(uid) && room.players.includes(uid)
      && !room.spectators.includes(uid);
    const alive = publicFrame.alive.includes(uid);
    const voted = publicFrame.voted.includes(uid);
    const ending = status === 'reveal' || !live;
    const speaking = !ending && status === 'describing' && publicFrame.speaker_uid === uid && present && alive;
    const choosing = !ending && status === 'voting' && present && alive && !voted;
    const phase = status + ':' + clueRound;
    if (revision > table.revision) {
      const invalidated = table.voted && !voted
        || table.slot?.target != null && !publicFrame.alive.includes(table.slot.target);
      if (!table.slot || table.phase !== phase || invalidated) {
        table.slot = {};
        table.clue = null;
      }
      table.phase = phase;
      table.revision = revision;
      table.voted = voted;
      if (status === 'reveal') table.result = publicFrame;
      if (publicFrame.last_ballot && table.ballotRound !== publicFrame.last_ballot.clue_round) {
        table.ballotRound = publicFrame.last_ballot.clue_round;
        table.tab = 'ballot';
      }
    }
    const slot = table.slot;
    if (!table.view?.root.isConnected || table.view.root.parentElement !== main) table.view = mount(main);
    const view = table.view;
    const paint = () => render(main, envelope);
    const focusKey = view.seats.contains(document.activeElement) ? document.activeElement.dataset.uid : null;
    const marker = element('div', 'spy-seat-layer');
    const validView = () => view.root.isConnected && marker.isConnected && state.token === token
      && state.uid === uid && state.groom === roomId && state.gst === envelope
      && envelope.room === room && room.room_id === roomId && room.round === round
      && room.game === 'spy' && envelope.state === publicFrame
      && publicFrame.round_key === roundKey && publicFrame.revision === revision
      && publicFrame.status === status && publicFrame.clue_round === clueRound && state.gpriv === privateFrame;
    const valid = () => validView() && room.status === 'playing' && hasWord
      && privateFrame.revision === revision && validPrivate(envelope, privateFrame);
    const pending = cardPendingFor('spy', {uid, roomId, round, publicFrame: slot, privateFrame: slot});
    const controls = pending.attach(marker, valid);
    const feedback = () => {
      if (slot.error && (speaking || choosing)) return slot.error;
      if (pending.isPending() && (speaking || choosing)) return slot.confirmed ? '已提交，等待牌桌同步' : '正在提交…';
      return '';
    };
    function send(action) {
      if (!valid() || pending.isPending()) return;
      if ('describe' in action && (publicFrame.speaker_uid !== uid || !speaking)) return;
      if ('vote' in action && (!choosing || publicFrame.voted.includes(uid)
          || action.vote === uid || !publicFrame.alive.includes(action.vote))) return;
      slot.error = '';
      slot.target = action.vote ?? null;
      slot.confirmed = false;
      view.feedback.textContent = '正在提交…';
      if (slot.target != null) {
        const seat = [...marker.children].find(node => Number(node.dataset.uid) === slot.target);
        seat?.querySelector('.spy-portrait')?.append(element('b', 'spy-mark spy-mark-pending', '待'));
      }
      pending.submit(() => {
        const sameRoom = () => state.token === token && state.uid === uid && state.groom === roomId
          && state.gst?.room?.room_id === roomId && state.gst.room.round === round
          && state.gst.state?.round_key === roundKey;
        function failed(message, refresh) {
          slot.target = null;
          slot.error = message;
          if (sameRoom() && table.slot === slot) {
            table.view.refreshFeedback();
            table.view.seats.querySelectorAll('.spy-mark-pending').forEach(mark => mark.remove());
            if (refresh) gameAPI('sync', {room_id:roomId}, true).catch(() => {});
          }
          return {ok:false};
        }
        return gameAPI('action', {room_id:roomId,
          action:{...action, spy_context:{round_key:roundKey, clue_round:clueRound}}}, true)
          .then(reply => {
            if (reply?.ok !== true) return failed(reply?.error || '提交失败，请重试', reply?.refresh);
            slot.confirmed = true;
            if (sameRoom() && table.slot === slot) table.view.refreshFeedback();
            return reply;
          }, () => failed('连接中断，请重试', true));
      });
    }

    const allSeats = publicFrame.seat_order;
    const pageCount = Math.ceil(allSeats.length / seatsPerPage);
    if (table.speaker !== publicFrame.speaker_uid) {
      const seat = allSeats.indexOf(publicFrame.speaker_uid);
      if (seat >= 0) table.page = Math.floor(seat / seatsPerPage);
      table.speaker = publicFrame.speaker_uid;
    }
    const start = table.page * seatsPerPage;
    const displayed = allSeats.slice(start, start + seatsPerPage);
    const points = positions(displayed.length);
    const votes = publicFrame.last_ballot?.counts || {};
    const tally = Boolean(publicFrame.last_ballot && (table.tab === 'ballot' || ending));
    displayed.forEach((player, index) => {
      const seatNumber = start + index;
      const currentSpeaker = !ending && publicFrame.speaker_uid === player;
      const out = !publicFrame.alive.includes(player);
      const left = !publicFrame.players.includes(player);
      const canVote = choosing && player !== uid && !out;
      const label = gnick(player);
      const detail = left ? '离席' : out ? '出局' : currentSpeaker ? '发言中'
        : publicFrame.voted.includes(player) && !ending ? '已投' : '';
      const ballotCount = tally && votes[player]
        ? (publicFrame.last_ballot.clue_round < clueRound ? '上轮' : '') + votes[player] + '票' : '';
      const seat = button('spy-seat', null, [label, player === uid ? '你' : '', detail, ballotCount,
        canVote ? '投票' : ''].filter(Boolean).join(' · '), () => {
        if (seat.isConnected && canVote) send({vote:player});
      });
      seat.classList.toggle('spy-speaking', currentSpeaker);
      seat.classList.toggle('spy-out', out);
      seat.dataset.uid = player;
      seat.title = seat.getAttribute('aria-label');
      seat.style.setProperty('--spy-seat-color', colors[seatNumber % seatsPerPage]);
      const x = points[index][0];
      const mobileX = displayed.length === 6 && x === 16 ? 13.5
        : displayed.length === 6 && x === 84 ? 86.5 : x;
      seat.style.setProperty('--spy-seat-x', x + '%');
      seat.style.setProperty('--spy-seat-mobile-x', mobileX + '%');
      seat.style.top = points[index][1] + '%';
      const portrait = element('span', 'spy-portrait');
      portrait.append(picture('seat-' + (seatNumber % seatsPerPage + 1), 256, 256));
      if (status === 'reveal' && publicFrame.spy_uid === player) portrait.append(element('b', 'spy-mark', '卧底'));
      else if (hasWord && privateFrame.revision === revision && voted && privateFrame.own_vote === player) {
        portrait.append(element('b', 'spy-mark', '票'));
      } else if (pending.isPending() && slot.target === player && choosing) {
        portrait.append(element('b', 'spy-mark spy-mark-pending', '待'));
      }
      const name = element('span', 'spy-seat-name', label);
      if (player === uid) name.append(element('small', '', '你'));
      seat.append(portrait, name);
      if (detail || ballotCount) {
        const caption = element('span', 'spy-seat-status');
        if (detail) caption.append(element('span', '', detail));
        if (ballotCount) caption.append(element('span', 'spy-seat-count', ballotCount));
        seat.append(caption);
      }
      marker.append(seat);
      controls.watch(seat, canVote && hasWord && privateFrame.revision === revision);
    });
    view.seats.replaceChildren(marker);
    if (focusKey) {
      const same = [...marker.children].find(seat => seat.dataset.uid === focusKey && !seat.disabled);
      same?.focus({preventScroll:true});
    }
    view.navigation.replaceChildren();
    if (pageCount > 1) {
      function turnPage(delta) {
        if (!marker.isConnected || state.token !== token || state.gst !== envelope || state.groom !== roomId) return;
        table.page = (table.page + delta + pageCount) % pageCount;
        paint();
      }
      view.navigation.append(button('spy-page-button', '‹', '上一页席位', () => turnPage(-1)),
        element('span', '', '席位 ' + (start + 1) + '–' + (start + displayed.length) + ' / ' + allSeats.length),
        button('spy-page-button', '›', '下一页席位', () => turnPage(1)));
    }

    view.copy.replaceChildren();
    const title = ending ? (status !== 'reveal' ? '对局中止' : publicFrame.winner_uid == null ? '平民胜' : '卧底胜')
      : status === 'voting' ? '票投给谁？' : speaking ? '轮到你发言' : gnick(publicFrame.speaker_uid) + ' 发言中';
    view.copy.append(element('div', 'spy-paper-label', ending ? '揭晓' : '第 ' + clueRound + ' 轮 · ' + (status === 'voting' ? '投票' : '发言')),
      element('h3', 'spy-paper-title', title));
    if (status === 'reveal') {
      view.copy.append(element('p', 'spy-public-reveal', '卧底是 ' + gnick(publicFrame.spy_uid)));
      if (publicFrame.reveal_words) {
        const words = element('div', 'spy-reveal-words');
        for (const [role, label] of [['civilian','平民'], ['spy','卧底']]) {
          const word = element('div', 'spy-reveal-word');
          word.append(element('small','',label), element('strong','',publicFrame.reveal_words[role]));
          words.append(word);
        }
        view.copy.append(words);
      }
    } else if (status === 'voting') {
      const note = element('p', 'spy-paper-detail', voted ? '已投票，等待其他玩家'
        : choosing ? '点一位存活玩家投票' : '等待玩家投票');
      note.append(element('span', 'spy-vote-progress',
        publicFrame.voted.length + ' / ' + publicFrame.alive.length));
      view.copy.append(note);
    }
    const ballot = publicFrame.last_ballot;
    const statements = publicFrame.describes;
    if (ballot && (tally || ending)) {
      const result = ballot.tie ? '最高票平票 · 无人出局'
        : ballot.eliminated_uid == null ? '无人出局'
        : gnick(ballot.eliminated_uid) + ' · ' + ballot.counts[ballot.eliminated_uid] + ' 票出局';
      view.copy.append(element('p', 'spy-ballot-result', '第 ' + ballot.clue_round + ' 轮唱票 · ' + result));
    }
    if (!ending && !tally && statements.length) {
      const index = Math.min(table.clue ?? statements.length - 1, statements.length - 1);
      const clue = statements[index];
      const quote = element('div', 'spy-quote');
      quote.append(element('span', 'spy-quote-name', gnick(clue.uid)), element('span', 'spy-quote-text', clue.text));
      const pager = element('div', 'spy-clue-nav');
      const prev = button('spy-clue-button', '‹', '上一条发言', () => {if (marker.isConnected) {table.clue = index - 1; paint();}});
      const next = button('spy-clue-button', '›', '下一条发言', () => {if (marker.isConnected) {table.clue = index + 1; paint();}});
      prev.disabled = index === 0;
      next.disabled = index === statements.length - 1;
      pager.append(prev, element('span', '', (index + 1) + ' / ' + statements.length), next);
      view.copy.append(quote, pager);
    }
    if (!ending && ballot) {
      view.copy.append(button('spy-switch', tally ? '查看本轮发言' : '上轮唱票', null, () => {
        if (!marker.isConnected || state.gst !== envelope || state.token !== token || state.groom !== roomId) return;
        table.tab = tally ? 'clues' : 'ballot';
        paint();
      }));
    }
    if (view.formPhase !== phase || !speaking) {
      view.input.value = '';
      view.formPhase = phase;
      view.composing = false;
    }
    view.form.hidden = !speaking;
    view.form.onsubmit = event => {
      event.preventDefault();
      const value = view.input.value.trim();
      if (view.composing || !value || !speaking) return;
      if (Array.from(value).length > 100) {
        view.feedback.textContent = '描述最多 100 个字符';
        return;
      }
      send({describe:value});
    };
    controls.watch(view.stamp, speaking && hasWord && privateFrame.revision === revision);
    view.refreshFeedback = () => { view.feedback.textContent = feedback(); };
    view.refreshFeedback();
    view.rail.replaceChildren();
    if (hasWord) {
      const hand = button('spy-word-card', null, table.hidden ? '翻开私密词卡' : '遮住私密词卡', () => {
        if (!hand.isConnected || !validView() || !validPrivate(envelope, privateFrame)) return;
        table.hidden = !table.hidden;
        paint();
        view.rail.querySelector('button')?.focus({preventScroll:true});
      });
      const illustration = element('span', 'spy-word-art');
      illustration.style.backgroundPositionX = table.hidden ? '100%' : privateFrame.role === 'spy' ? '0%' : '50%';
      illustration.setAttribute('aria-hidden', 'true');
      hand.append(illustration);
      const label = element('span', 'spy-hand-copy');
      label.append(element('small', '', table.hidden ? '词卡已遮住' : privateFrame.role === 'spy' ? '卧底 · 私密词' : '平民 · 私密词'),
        element('strong', '', table.hidden ? '翻开词卡' : privateFrame.word));
      if (!table.hidden) label.append(element('span', 'spy-hand-hide', '点卡遮住'));
      hand.append(label);
      view.rail.append(hand);
    } else {
      const text = ending ? '本局已结束' : present && !alive ? '你已出局'
        : !present ? '观战席' : '词卡同步中';
      view.rail.append(element('div', 'spy-no-word', text));
    }
    controls.refresh();
  }

  return {render, validPrivate, stalePublic, headerButton, reset: () => tables.clear()};
})();
"""

WEB_CSS = r"""
#gpanel.spy-room { background: #20151bbd; backdrop-filter: blur(2px); }
body.hasBgArt #gpanel.spy-room > .card,
#gpanel.spy-room > .card {
  width: min(1040px, 97vw); max-height: 96dvh; padding: 12px; gap: 8px;
  background: #231b22; background-image: none; color: #f4e6cf;
  border: 1px solid #8e6a4d; box-shadow: 0 18px 65px #150c13bd;
}
#gpanel.spy-room > .card.full { width: min(1180px, 98vw); height: auto; }
#gpanel.spy-room #ghead { color: #ead8ba; font-size: 13px; gap: 6px; }
#gpanel.spy-room #ghead > span:first-child { min-width: 0; }
#gpanel.spy-room #ghead .gbtn {
  color: #f2e1c3; background: #45313a; border-color: #795b50; flex: none; padding: 6px 9px;
}
#gpanel.spy-room #ghead .gbtn:hover { background: #604238; }
#gpanel.spy-room #glog { display: none; }
#gpanel.spy-room #gmain { min-height: 0; max-height: calc(96dvh - 64px); overflow-x: hidden; }
.spy-board {
  display: grid; grid-template-columns: minmax(0, 1fr) 180px;
  grid-template-areas: "stage rail" "navigation rail"; align-items: center; gap: 0 10px;
  padding: 6px; background: radial-gradient(ellipse at 45% 38%, #3d2a28, #241b21 78%);
  border: 1px solid #795b48; border-radius: 13px; color: #f4e7d0; min-width: 0;
  font: 14px/1.35 "Microsoft YaHei UI", sans-serif;
}
.spy-stage {
  grid-area: stage; position: relative; height: clamp(480px, 66dvh, 650px);
  isolation: isolate; min-width: 0; overflow: hidden; border-radius: 9px;
  background: #271e24;
}
.spy-stage > .spy-image {
  display: block; position: absolute; width: min(100%, 650px); height: 100%;
  left: 50%; transform: translateX(-50%); object-fit: contain; z-index: -1;
  mask-image: radial-gradient(ellipse, #000 64%, transparent 77%);
}
.spy-seats, .spy-seat-layer { position: absolute; inset: 0; pointer-events: none; }
#gpanel .spy-seat {
  --spy-portrait-size: clamp(68px, 8vw, 100px);
  position: absolute; left: var(--spy-seat-x); transform: translate(-50%, calc(-.5 * var(--spy-portrait-size) - 12px));
  width: clamp(84px, 12vw, 122px);
  display: flex; flex-direction: column; align-items: center; gap: 3px; pointer-events: auto;
  padding: 0; background: none; border: 0; box-shadow: none; color: #fff0d7; text-align: center;
  font: inherit;
}
#gpanel .spy-seat:disabled { opacity: 1; }
#gpanel .spy-seat:enabled { cursor: pointer; }
.spy-portrait {
  position: relative; width: var(--spy-portrait-size); aspect-ratio: 1; border-radius: 50%;
  background: #4d3837; border: 3px solid var(--spy-seat-color);
  box-shadow: 0 0 0 3px #362731, 0 5px 11px #170f15c9;
}
.spy-portrait > img { display: block; width: 100%; height: 100%; border-radius: inherit; object-fit: contain; }
.spy-speaking .spy-portrait, .spy-seat:enabled .spy-portrait { box-shadow: 0 0 0 3px #f3d899, 0 5px 19px #d1a1588a; }
.spy-seat:enabled:hover .spy-portrait, .spy-seat:focus-visible .spy-portrait { border-color: #fff0be; }
.spy-out .spy-portrait > img { filter: grayscale(.85) brightness(.65); }
.spy-seat-name {
  display: block; max-width: 100%; padding: 3px 9px; border-radius: 5px;
  background: #2d2023ed; border: 1px solid var(--spy-seat-color); color: #fff0d7;
  font-weight: 700; line-height: 1.25; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;
}
.spy-seat-name small { margin-left: 5px; color: #e4c792; }
.spy-seat-status {
  display: flex; align-items: center; gap: 4px; white-space: nowrap; padding: 2px 6px; border-radius: 6px;
  background: #322526; color: #f2d39b; font-size: 11px; font-weight: 700;
}
.spy-speaking .spy-seat-status { color: #301b20; background: #eed096; }
.spy-vote-progress { display: inline-block; margin-left: 7px; white-space: nowrap; font-size: .86em; }
.spy-mark {
  position: absolute; right: -7px; bottom: 0; min-width: 29px; min-height: 29px;
  display: grid; place-items: center; padding: 1px 3px; background: #823f4d; color: #ffe1a4;
  border: 3px double #e5aa86; border-radius: 50%; font-size: 11px; transform: rotate(-12deg);
}
.spy-mark-pending { background: #665444; }
.spy-paper {
  position: absolute; top: 49%; left: 50%; transform: translate(-50%, -50%);
  width: clamp(228px, 51%, 385px); box-sizing: border-box; padding: 15px;
  background: #edddbb; background-image: repeating-linear-gradient(10deg, #7e634008 0 1px, transparent 1px 5px);
  color: #32232c; border: 1px solid #bc9561; border-radius: 8px;
  box-shadow: inset 0 0 0 3px #e2cba2, 0 6px 13px #180f19aa;
}
.spy-paper-label { color: #6f4d4c; font-weight: 700; font-size: 12px; }
.spy-paper-title { color: #3b2634; font-size: clamp(17px, 2.1vw, 25px); margin: 3px 0 7px; line-height: 1.25; overflow-wrap: anywhere; }
.spy-paper-detail,.spy-public-reveal,.spy-ballot-result { margin: 5px 0; overflow-wrap: anywhere; }
.spy-ballot-result { font-size: 12px; font-weight: 700; color: #6e3341; }
.spy-quote {
  display: grid; grid-template-columns: 65px minmax(0, 1fr); gap: 6px; align-items: start;
  border-top: 1px solid #b89a6e; padding-top: 6px; margin-top: 8px;
}
.spy-quote-name { color: #634143; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spy-quote-text { max-height: 58px; overflow: auto; overflow-wrap: anywhere; }
.spy-clue-nav { display: flex; align-items: center; justify-content: flex-end; gap: 7px; font-size: 11px; }
#gpanel .spy-clue-button, #gpanel .spy-switch {
  border: 0; background: none; color: #633645; box-shadow: none; min-height: 30px;
  padding: 3px 8px; font: inherit; cursor: pointer; text-decoration: underline;
}
#gpanel .spy-clue-button:disabled { color: #8e766b; cursor: default; }
.spy-compose { display: flex; align-items: center; gap: 8px; margin-top: 7px; }
.spy-compose[hidden] { display: none; }
#gpanel .spy-input {
  width: 100%; min-width: 0; min-height: 41px; padding: 7px 9px; font: inherit;
  color: #32232c; background: #fff4d9; border: 1px solid #a4825b; border-radius: 5px;
}
#gpanel .spy-seal {
  flex: 0 0 44px; width: 44px; height: 44px; padding: 0; border: 3px double #e6b788;
  color: #fff1c9; background: #824553; border-radius: 50%; box-shadow: 0 2px 3px #512c3f77;
  font-weight: 800; cursor: pointer;
}
#gpanel .spy-seal:disabled { background: #725d55; color: #eddfc1; cursor: default; }
.spy-action-note { min-height: 0; color: #703745; font-size: 12px; }
.spy-action-note:not(:empty) { margin-top: 6px; }
.spy-rail { grid-area: rail; min-width: 0; }
#gpanel .spy-word-card {
  display: flex; flex-direction: column; width: 100%; padding: 8px; gap: 8px; text-align: left;
  color: #f7e6c8; background: #3c2a37; border: 1px solid #bd9365; border-radius: 9px;
  box-shadow: inset 0 0 0 3px #59413f, 0 7px 18px #160e16a6; cursor: pointer;
}
.spy-word-art {
  display: block; width: 100%; aspect-ratio: 4 / 5; border-radius: 5px;
  background: url("/game-art/spy-word-cards.webp") no-repeat; background-size: 300% 100%;
}
.spy-hand-copy { display: flex; flex-direction: column; gap: 3px; padding: 2px 4px; min-width: 0; }
.spy-hand-copy small, .spy-hand-hide { font-size: 12px; color: #e5c89f; }
.spy-hand-copy strong { font-size: 25px; line-height: 1.15; overflow-wrap: anywhere; }
.spy-no-word { color: #e5c89f; text-align: center; padding: 9px; }
.spy-seat-nav { grid-area: navigation; display: flex; justify-content: center; align-items: center; gap: 10px; color: #e4c699; }
.spy-seat-nav:empty { display: none; }
#gpanel .spy-page-button { min-width: 44px; min-height: 36px; border: 1px solid #9d7758; color: #ffe6ad; background: #4d343d; border-radius: 5px; cursor: pointer; }
.spy-reveal-words { display: flex; gap: 8px; margin: 8px 0; }
.spy-reveal-word { flex: 1; min-width: 0; padding: 4px 6px; border: 1px solid #b59772; border-radius: 4px; }
.spy-reveal-word > small, .spy-reveal-word > strong { display: block; overflow-wrap: anywhere; }
.spy-reveal-word > small { color: #6f4d4c; }
.spy-waiting { position: relative; display: block; height: 350px; overflow: hidden; }
.spy-waiting > img { display: block; width: 100%; height: 100%; object-fit: contain; }
.spy-syncing { color: #f0d6b1; padding: 16px; }
#gpanel .spy-board button:focus-visible, #gpanel .spy-input:focus-visible { outline: 3px solid #edb75d; outline-offset: 2px; }
@media (max-width: 680px) {
  body.hasBgArt #gpanel.spy-room > .card,
  #gpanel.spy-room > .card { width: 98vw; padding: 6px; gap: 5px; }
  #gpanel.spy-room #ghead { font-size: 12px; gap: 4px; }
  #gpanel.spy-room #ghead .gbtn { padding: 5px 6px; }
  .spy-board { grid-template-columns: minmax(0, 1fr); grid-template-areas: "stage" "navigation" "rail"; padding: 4px; gap: 5px; }
  .spy-stage { height: clamp(350px, 101vw, 480px); }
  #gpanel .spy-seat { --spy-portrait-size: 56px; left: var(--spy-seat-mobile-x); width: 71px; gap: 2px; font-size: 12px; }
  .spy-portrait { border-width: 2px; }
  .spy-seat-name { padding: 3px 5px; }
  .spy-seat-status { font-size: 10px; padding: 2px 3px; gap: 2px; }
  .spy-seat-count { font-size: 9px; }
  .spy-paper { width: 52%; min-width: 160px; padding: 9px; }
  .spy-paper-title { font-size: 16px; margin-bottom: 4px; }
  .spy-paper-label, .spy-ballot-result, .spy-quote { font-size: 11px; }
  .spy-quote { display: block; }
  .spy-quote-name { display: block; }
  .spy-quote-text { display: block; max-height: 46px; }
  .spy-compose { gap: 5px; }
  #gpanel .spy-input { padding: 6px 4px; font-size: 16px; }
  #gpanel .spy-seal { flex-basis: 43px; width: 43px; }
  #gpanel .spy-word-card { flex-direction: row; align-items: center; padding: 5px; gap: 9px; }
  .spy-word-art { flex: 0 0 58px; width: 58px; }
  .spy-hand-copy strong { font-size: 22px; }
  .spy-waiting { height: 320px; }
}
@media (max-width: 370px) {
  #gpanel .spy-seat { --spy-portrait-size: 50px; width: 63px; }
  .spy-paper { width: 50%; min-width: 140px; }
}
"""
