// Open the served app and use the ordinary lobby, HTTP API and EventSource.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.env.PLAYWRIGHT_BROWSERS_PATH = cfg.cache;
const {chromium} = require(cfg.runtime);

const board = '#gmain .spy-board';
const names = ['阿棠', '晴禾', '紫苑', '澄音', '松月', '绯芽', '竹露', '白汀'];
const evidence = {source_id: cfg.source.id, rooms: [], checks: {}, screenshots: [], requests: [], page_errors: []};

function save() {
  fs.writeFileSync(path.join(cfg.output, 'evidence.json'), JSON.stringify(evidence, null, 2));
}

async function run(browser) {
  async function login(page, name) {
    await page.locator('#nick').fill(name);
    await page.locator('#btnLogin').click();
    await page.waitForFunction(() => state.uid > 0 && document.querySelector('#main').offsetWidth > 0);
    return page.evaluate(() => state.uid);
  }

  async function player(name, mobile = false) {
    const context = await browser.newContext({
      viewport: mobile ? {width: 390, height: 844} : {width: 1360, height: 900},
      deviceScaleFactor: 1, hasTouch: mobile, isMobile: mobile, reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    page.setDefaultTimeout(8500);
    page.on('pageerror', error => evidence.page_errors.push({name, message: error.message}));
    page.on('request', request => {
      if (request.method() !== 'POST' || !request.url().endsWith('/api/game')) return;
      const {op, room_id, game, action} = request.postDataJSON();
      evidence.requests.push({name, op, room_id, game, action});
    });
    await page.addInitScript(() => {
      window.spyObserved = {public: [], private: []};
      const EventStream = window.EventSource;
      window.EventSource = class extends EventStream {
        constructor(...args) {
          super(...args);
          this.addEventListener('message', event => {
            const frame = JSON.parse(event.data);
            if (frame.t === 'game_state' && frame.room?.game === 'spy') {
              window.spyObserved.public.push({room: frame.room, state: frame.state, events: frame.events});
            }
            if (frame.t === 'game_private' && frame.state?.game === 'spy') {
              window.spyObserved.private.push({roomId: frame.room_id, state: frame.state});
            }
          });
        }
      };
    });
    const response = await page.goto(cfg.url, {waitUntil: 'domcontentloaded'});
    assert.equal(crypto.createHash('sha256').update(await response.body()).digest('hex'), cfg.source.served_sha256);
    return {context, page, name, uid: await login(page, name), mobile};
  }

  async function lobby(person) {
    const rail = person.page.locator('#uxRail [data-ux-nav="game"]');
    if (await rail.isVisible()) {
      await rail.click();
    } else {
      if (!(await person.page.locator('#side').evaluate(side => side.classList.contains('open')))) {
        await person.page.locator('#btnSide').click();
      }
      await person.page.locator('#side [title="游戏大厅"]').click();
    }
    await person.page.locator('#globby').waitFor();
  }

  async function join(person, roomId, label) {
    await lobby(person);
    await person.page.locator('#glRooms > div').filter({hasText:'（' + roomId + '）'})
      .getByRole('button', {name: label, exact: true}).click();
    await person.page.waitForFunction(({roomId, uid}) => state.groom === roomId
      && state.gst?.room?.room_id === roomId
      && (state.gst.room.players.includes(uid) || state.gst.room.spectators.includes(uid)), {roomId, uid: person.uid});
  }

  async function ready(person, roomId, round, revision, ownWord = true) {
    await person.page.waitForFunction(({roomId, round, revision, ownWord}) => {
      const room = state.gst?.room;
      const publicFrame = state.gst?.state;
      const privateFrame = state.gpriv;
      return state.groom === roomId && room?.room_id === roomId && room.round === round
        && publicFrame?.revision === revision && document.querySelector('#gmain .spy-board')
        && (!ownWord || (privateFrame?.owner_uid === state.uid && privateFrame.revision === revision
          && privateFrame.round_key === publicFrame.round_key));
    }, {roomId, round, revision, ownWord});
  }

  async function session(count, prefix) {
    const players = [];
    for (let i = 0; i < count; i++) {
      const suffix = count === 8 && i === 7 ? '合成测试长昵称' : '';
      players.push(await player(prefix + names[i] + suffix, i === 1));
    }
    const [host] = players;
    const spectator = await player(prefix + '旁听', true);
    await lobby(host);
    await host.page.locator('#glQuery').fill('spy');
    await host.page.locator('#glGames [data-game="spy"]').getByRole('button', {name:'创建房间'}).click();
    await host.page.waitForFunction(() => state.gst?.room?.game === 'spy' && state.groom === state.gst.room.room_id);
    const roomId = await host.page.evaluate(() => state.groom);
    for (const person of players.slice(1)) await join(person, roomId, '加入');
    await host.page.locator('#ghead').getByRole('button', {name:/开始对局/}).click();
    await ready(host, roomId, 1, 0);
    await join(spectator, roomId, '观战');
    await ready(spectator, roomId, 1, 0, false);
    await Promise.all(players.map(person => ready(person, roomId, 1, 0)));
    const roles = await Promise.all(players.map(person => person.page.evaluate(() => state.gpriv.role)));
    assert.equal(roles.filter(role => role === 'spy').length, 1);
    const spy = players[roles.indexOf('spy')].uid;
    const entry = {roomId, count, spy, transitions: []};
    evidence.rooms.push(entry);
    save();
    return {roomId, players, host, spectator, spy, entry};
  }

  async function snapshot(person) {
    return person.page.evaluate(() => state.gst.state);
  }

  async function shot(person, name) {
    await person.page.locator(board).evaluate(async root => {
      await Promise.all([...root.querySelectorAll('img')].map(img => img.decode()));
      await document.fonts.ready;
    });
    const view = await person.page.evaluate(() => {
      const root = document.querySelector('#gmain .spy-board');
      const bounds = root.getBoundingClientRect();
      const panel = root.parentElement.getBoundingClientRect();
      const paper = root.querySelector('.spy-paper').getBoundingClientRect();
      const seats = [...root.querySelectorAll('.spy-seat')].map(seat =>
        [...seat.children].map(part => part.getBoundingClientRect()));
      const overlap = (a,b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      const overlaps = seats.filter(parts => parts.some(part => overlap(part, paper))).length;
      const seatCollisions = seats.filter((parts, index) => seats.slice(index + 1).some(other =>
        parts.some(part => other.some(candidate => overlap(part, candidate))))).length;
      return {room: state.groom, round: state.gst.room.round, revision: state.gst.state?.revision,
        phase: state.gst.state?.status, viewer: state.uid, viewport: [innerWidth, innerHeight],
        scrollWidth: document.documentElement.scrollWidth, width: Math.round(bounds.width), overlaps, seatCollisions,
        fullyVisible: bounds.top >= panel.top - 2 && bounds.bottom <= panel.bottom + 2};
    });
    assert.ok(view.scrollWidth <= view.viewport[0], name + ': horizontal overflow');
    assert.equal(view.overlaps, 0, name + ': paper overlaps seat art or label');
    assert.equal(view.seatCollisions, 0, name + ': seat art or labels overlap');
    assert.ok(view.fullyVisible, name + ': tabletop is clipped vertically');
    const file = name + '.png';
    await person.page.screenshot({path:path.join(cfg.output, file), animations:'disabled'});
    evidence.screenshots.push({...view, file, source_id:cfg.source.id,
      sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(cfg.output, file))).digest('hex')});
    save();
  }

  function actionReply(page) {
    return page.waitForResponse(response => response.url().endsWith('/api/game')
      && response.request().postDataJSON()?.op === 'action');
  }

  async function commitAction(person, game, before, interact) {
    const reply = actionReply(person.page);
    await interact();
    const response = await reply;
    assert.equal(response.status(), 200);
    assert.deepEqual(await response.json(), {ok:true});
    await ready(game.host, game.roomId, 1, before.revision + 1, false);
    const next = await snapshot(game.host);
    game.entry.transitions.push({actor:person.name, action:response.request().postDataJSON().action,
      http:response.status(), next:next.status, revision:next.revision, round:next.clue_round});
    return next;
  }

  async function describeRound(game, prefix, capture = false) {
    let current = await snapshot(game.host);
    while (current.status === 'describing') {
      const actor = game.players.find(person => person.uid === current.speaker_uid);
      await ready(actor, game.roomId, 1, current.revision);
      const input = actor.page.getByRole('textbox', {name:'描述你的词'});
      await input.fill(actor.mobile ? '可以在清晨见到。' : '形状看起来很熟悉。');
      if (capture && current.describes.length <= 1) {
        await shot(actor, prefix + (actor.mobile ? '-mobile-describe' : '-desktop-describe'));
      }
      current = await commitAction(actor, game, current, async () => {
        if (actor.mobile) await actor.page.getByRole('button', {name:'发送描述'}).tap();
        else await input.press('Enter');
      });
      assert.ok(current.describes.some(clue => clue.uid === actor.uid));
    }
    assert.equal(current.status, 'voting');
    return current;
  }

  async function voteSeat(person, target) {
    const seat = person.page.locator(board + ' .spy-seat[data-uid="' + target + '"]');
    if (!await seat.count()) await person.page.getByRole('button', {name:'下一页席位'}).click();
    await seat.waitFor();
    return seat;
  }

  async function voteRound(game, pick, prefix, capture = false) {
    let current = await snapshot(game.host);
    const ids = [...current.alive];
    for (const uid of ids) {
      const actor = game.players.find(person => person.uid === uid);
      await ready(actor, game.roomId, 1, current.revision);
      const target = pick(uid, ids);
      const seat = await voteSeat(actor, target);
      const before = current;
      current = await commitAction(actor, game, current, async () => {
        if (actor.mobile) await seat.tap();
        else { await seat.focus(); await seat.press('Enter'); }
      });
      if (capture && ids.indexOf(uid) <= 1) {
        await ready(actor, game.roomId, 1, current.revision);
        await actor.page.locator('.spy-mark').filter({hasText:'票'}).waitFor();
        assert.equal(await actor.page.locator('.spy-action-note').textContent(), '');
        await shot(actor, prefix + (actor.mobile ? '-mobile-vote' : '-desktop-vote'));
      }
      if (current.status === 'voting') {
        assert.ok(current.voted.includes(uid));
        assert.deepEqual(current.vote_counts, {});
        assert.deepEqual(current.last_ballot, before.last_ballot);
      }
    }
    assert.equal(Object.values(current.last_ballot.counts).reduce((sum, n) => sum + n, 0), ids.length);
    return current;
  }

  function targetMost(target) {
    return (uid, ids) => uid === target ? ids.find(other => other !== uid) : target;
  }

  async function checkPrivate(game, beforeReveal = true) {
    const roleProof = [];
    for (const person of [...game.players, game.spectator]) {
      const result = await person.page.evaluate(() => ({
        frames: window.spyObserved,
        wordCard: document.querySelector('.spy-word-card')?.textContent || '',
        privatePanel: document.querySelector('#gpriv')?.textContent || '',
        pending: state.gpriv?.owner_uid ?? null,
      }));
      const plays = person !== game.spectator;
      assert.equal(result.privatePanel, '');
      for (const frame of result.frames.public.filter(frame => frame.state?.status !== 'reveal')) {
        if (!frame.state) continue;
        assert.equal(frame.state.spy_uid, null);
        assert.equal(frame.state.pair_idx, null);
        assert.equal(frame.state.reveal_words, null);
        for (const key of ['role', 'word', 'own_vote', 'owner_uid']) assert.equal(key in frame.state, false);
        assert.ok(frame.events.every(text => !text.includes('本轮词面')));
      }
      assert.ok(result.frames.private.every(frame => frame.state.owner_uid === person.uid));
      if (!plays) {
        assert.equal(result.frames.private.length, 0);
        assert.equal(result.wordCard, '');
        assert.equal(result.pending, null);
      } else if (beforeReveal) {
        const last = result.frames.private.at(-1).state;
        assert.ok(result.wordCard.includes(last.word));
        const card = person.page.getByRole('button', {name:'遮住私密词卡'});
        await card.click();
        const masked = await person.page.locator('.spy-word-card').textContent();
        assert.ok(!masked.includes(last.word));
        const art = await person.page.locator('.spy-word-art').evaluate(node => getComputedStyle(node).backgroundImage);
        assert.match(art, /spy-word-cards\.webp/);
        await person.page.getByRole('button', {name:'翻开私密词卡'}).press('Enter');
        assert.ok((await person.page.locator('.spy-word-card').textContent()).includes(last.word));
      }
      roleProof.push({name: person.name, uid: person.uid, private_frames: result.frames.private.length,
        early_public_frames: result.frames.public.filter(frame => frame.state?.status !== 'reveal').length});
    }
    game.entry.privacy = roleProof;
  }

  async function settleAndRestart(game, expectedWinner, prefix) {
    await game.host.page.waitForFunction(() => state.gst?.state?.status === 'reveal'
      && state.gst.room.status === 'ended');
    const reveal = await snapshot(game.host);
    assert.equal(reveal.winner_uid, expectedWinner);
    assert.ok(reveal.reveal_words.spy && reveal.reveal_words.civilian);
    await game.players[1].page.waitForFunction(() => document.querySelector('.spy-public-reveal'));
    await shot(game.host, prefix + '-desktop-end');
    await shot(game.players[1], prefix + '-mobile-end');
    await checkPrivate(game, false);
    await game.host.page.waitForFunction(() => state.gst?.room?.status === 'created');
    assert.equal(await game.host.page.locator('.spy-paper-title').textContent(),
      expectedWinner == null ? '平民胜' : '卧底胜');
    await game.host.page.locator('#ghead').getByRole('button', {name:/开始对局/}).click();
    await Promise.all(game.players.map(person => ready(person, game.roomId, 2, 0)));
    const restarted = await snapshot(game.host);
    assert.notEqual(restarted.round_key, reveal.round_key);
    assert.equal(restarted.reveal_words, null);
    assert.equal(restarted.last_ballot, null);
    game.entry.result = {winner: expectedWinner == null ? 'civilian' : 'spy',
      revision: reveal.revision, reveal_words: reveal.reveal_words, reopened: true};
    save();
  }

  async function closeGame(game) {
    for (const person of [...game.players, game.spectator]) await person.context.close();
  }

  async function oldCallbacks(game) {
    const page = game.host.page;
    const count = evidence.requests.length;
    const checked = await page.evaluate(() => {
      const header = document.querySelector('#ghead button');
      const submit = document.querySelector('.spy-compose');
      const input = submit.querySelector('input');
      input.value = '合成旧回调';
      const saved = {token:state.token, uid:state.uid, groom:state.groom, gst:state.gst, gpriv:state.gpriv};
      const probes = [
        ['token', () => state.token = 'other-synthetic-session'],
        ['account', () => state.uid = -100],
        ['room_id', () => state.groom = 'g-other'],
        ['room_object', () => state.gst = {...saved.gst, room:{...saved.gst.room}}],
        ['round', () => state.gst = {...saved.gst, room:{...saved.gst.room, round:saved.gst.room.round+1}}],
        ['public_frame', () => state.gst = {...saved.gst, state:{...saved.gst.state}}],
        ['private_frame', () => state.gpriv = {...saved.gpriv}],
      ];
      for (const [name, change] of probes) {
        try {
          change();
          submit.onsubmit(new Event('submit', {cancelable:true}));
          if (name !== 'private_frame') header.onclick();
        } finally { Object.assign(state, saved); }
      }
      const oldSubmit = submit.onsubmit;
      openGamePanel('g-other');
      if (document.querySelector('#gmain .spy-word-card, #gmain .spy-seal:enabled')
          || [...document.querySelectorAll('#ghead button')].some(b => /离开|开始/.test(b.textContent))) {
        throw Error('old Spy room rendered private or actionable controls');
      }
      header.onclick();
      oldSubmit(new Event('submit', {cancelable:true}));
      openGamePanel(saved.groom);
      return [...probes.map(([name]) => name), 'open_panel_with_previous_state', 'detached_room_header'];
    });
    await ready(game.host, game.roomId, 1, 0);
    const actions = evidence.requests.slice(count).filter(request => request.op !== 'sync');
    assert.deepEqual(actions, []);
    evidence.checks.stale = checked;
  }

  async function exerciseCompose(game) {
    const {page} = game.host;
    const input = page.getByRole('textbox', {name:'描述你的词'});
    const count = evidence.requests.filter(r => r.op === 'action').length;
    await input.fill('字'.repeat(101));
    await input.press('Enter');
    assert.match(await page.locator('.spy-action-note').textContent(), /100/);
    await input.fill('合成输入法');
    await input.evaluate(node => {
      node.dispatchEvent(new CompositionEvent('compositionstart'));
      window.composingInput = node;
      renderGamePanel();
    });
    assert.ok(await input.evaluate(node => node === window.composingInput && node === document.activeElement));
    await input.press('Enter');
    assert.equal(evidence.requests.filter(r => r.op === 'action').length, count);
    await input.evaluate(node => node.dispatchEvent(new CompositionEvent('compositionend')));

    await input.fill('🍀'.repeat(100));
    assert.equal(Array.from(await input.inputValue()).length, 100);
    const routeAction = async (route, fail) => {
      if (route.request().postDataJSON()?.op !== 'action') {
        await route.continue();
        return;
      }
      await fail(route);
    };
    const dropped = route => routeAction(route, r => r.abort('failed'));
    await page.route('**/api/game', dropped);
    const failed = page.waitForEvent('requestfailed', {predicate:r => r.url().endsWith('/api/game')
      && r.postDataJSON()?.op === 'action'});
    await input.press('Enter');
    await failed;
    await page.unroute('**/api/game', dropped);
    await page.waitForFunction(() => document.querySelector('.spy-seal:enabled'));
    assert.equal((await snapshot(game.host)).revision, 0);

    const rejected = route => routeAction(route, r => {
      const body = r.request().postDataJSON();
      body.action.spy_context.clue_round += 1;
      return r.continue({postData:JSON.stringify(body)});
    });
    await page.route('**/api/game', rejected);
    const failure = actionReply(page);
    await input.press('Enter');
    const response = await failure;
    assert.equal(response.status(), 409);
    assert.equal((await response.json()).ok, false);
    await page.unroute('**/api/game', rejected);
    await page.waitForFunction(() => document.querySelector('.spy-seal:enabled'));
    assert.equal((await snapshot(game.host)).revision, 0);
    const next = await commitAction(game.host, game, await snapshot(game.host), () => input.press('Enter'));
    assert.equal(Array.from(next.describes[0].text).length, 100);
    evidence.checks.compose = {ime_enter_guarded:true, input_retained:true, unicode_characters:100,
      over_limit_no_request:true, transport_failure_retry:true, server_rejection_retry:true};
  }

  async function changeAccount(game) {
    let person;
    for (const candidate of game.players.slice(1)) {
      if (await candidate.page.evaluate(() => state.gpriv?.role === 'civilian')) {
        person = candidate;
        break;
      }
    }
    assert.ok(person);
    assert.equal(await person.page.locator('.spy-word-card').count(), 1);
    await person.page.locator('#ghead button').last().click();
    await person.page.locator('#head .head-tools summary').click();
    await person.page.locator('#head [title="退出登录"]').click();
    await person.page.locator('#btnLogin').waitFor();
    const newUid = await login(person.page, '再访');
    assert.notEqual(newUid, person.uid);
    assert.equal(await person.page.evaluate(() => state.gpriv), null);
    assert.equal(await person.page.locator('.spy-word-card').count(), 0);
    await join({...person, uid:newUid}, game.roomId, '观战');
    assert.equal(await person.page.locator('.spy-word-card').count(), 0);
    assert.equal(await person.page.evaluate(() => state.gpriv), null);
    evidence.checks.account_change = {old_uid:person.uid, new_uid:newUid, joined_as_spectator:true};
  }

  async function leave(person) {
    await person.page.locator('#ghead').getByRole('button', {name:/离开/}).click();
    await person.page.locator('#gpanel').waitFor({state:'detached'});
    assert.equal(await person.page.evaluate(() => state.gpriv), null);
  }

  async function latchAndDeparture(game) {
    const [first, second] = game.players;
    const [leaver, last] = game.players.filter(person => person !== first && person !== second && person.uid !== game.spy);
    assert.ok(leaver && last);
    const initial = await snapshot(first);
    await ready(first, game.roomId, 1, initial.revision);
    const seat = await voteSeat(first, leaver.uid);
    let release, entered;
    const permit = new Promise(resolve => {release = resolve;});
    const incoming = new Promise(resolve => {entered = resolve;});
    const hold = async route => {
      if (route.request().postDataJSON()?.op === 'action') {
        entered();
        await permit;
      }
      await route.continue();
    };
    await first.page.route('**/api/game', hold);
    const result = actionReply(first.page);
    let afterOther;
    try {
      await seat.click();
      await incoming;
      await first.page.evaluate(() => renderGamePanel());
      assert.ok(await seat.isDisabled());
      await ready(second, game.roomId, 1, initial.revision);
      const otherSeat = await voteSeat(second, first.uid);
      afterOther = await commitAction(second, game, initial, () => otherSeat.tap());
      await ready(first, game.roomId, 1, afterOther.revision);
      assert.ok(await seat.isDisabled());
      const sent = evidence.requests.filter(r => r.name === first.name && r.op === 'action').length;
      await seat.evaluate(node => node.onclick());
      assert.equal(evidence.requests.filter(r => r.name === first.name && r.op === 'action').length, sent);
      assert.equal((await snapshot(first)).voted.includes(first.uid), false);
    } finally { release(); }
    const response = await result;
    assert.equal(response.status(), 200);
    assert.deepEqual(await response.json(), {ok:true});
    await first.page.unroute('**/api/game', hold);
    await ready(first, game.roomId, 1, afterOther.revision + 1);
    game.entry.transitions.push({actor:first.name, action:response.request().postDataJSON().action,
      http:response.status(), next:'voting', revision:afterOther.revision + 1});
    assert.equal(await first.page.locator('.spy-action-note').textContent(), '');
    await leave(leaver);
    await ready(first, game.roomId, 1, afterOther.revision + 2);
    let current = await snapshot(first);
    assert.ok(!current.voted.includes(first.uid) && current.voted.includes(second.uid));
    assert.ok(!current.alive.includes(leaver.uid));
    const replacement = await voteSeat(first, second.uid);
    current = await commitAction(first, game, current, () => replacement.click());
    assert.ok(current.voted.includes(first.uid));
    await leave(last);
    await first.page.waitForFunction(() => state.gst?.room?.status === 'ended'
      && document.querySelector('.spy-paper-title')?.textContent === '对局中止');
    current = await snapshot(first);
    assert.equal(current.status, 'voting');
    assert.equal(current.reveal_words, null);
    assert.equal(await first.page.locator('.spy-word-card, .spy-reveal-words').count(), 0);
    assert.equal(await first.page.evaluate(() => state.gpriv), null);
    assert.equal(await first.page.locator('.spy-paper-label').textContent(), '第 1 轮');
    assert.equal(await first.page.locator('.spy-paper-detail').textContent(), '玩家离开 · 当前 3 人，至少需要 4 人');
    assert.equal(await first.page.locator('.spy-vote-progress, .spy-public-reveal').count(), 0);
    await shot(first, 'departure-desktop-aborted');
    evidence.checks.departure = {pending_through_redraw:true, other_revision_did_not_unlock:true,
      re_voted_after_5_to_4:true, aborted_on_4_to_3:true, terminal_reason:true,
      no_reveal_or_pending_vote:true, private_word_cleared:true};
  }

  async function departureScenario() {
    const five = await session(5, '离');
    await describeRound(five, 'departure');
    await latchAndDeparture(five);
    await closeGame(five);
  }

  if (cfg.stage === 'departure') {
    await departureScenario();
    return;
  }

  const six = await session(6, '');
  await checkPrivate(six);
  await shot(six.host, 'six-desktop-start');
  await shot(six.players[1], 'six-mobile-start');
  await describeRound(six, 'six', true);
  const victim = six.players.find(person => person.uid !== six.spy && person.mobile) || six.host;
  assert.notEqual(victim.uid, six.spy);
  const eliminated = await voteRound(six, targetMost(victim.uid), 'six', true);
  assert.equal(eliminated.status, 'describing');
  assert.equal(eliminated.last_ballot.eliminated_uid, victim.uid);
  await ready(victim, six.roomId, 1, eliminated.revision, false);
  assert.equal(await victim.page.locator('.spy-word-card').count(), 0);
  assert.equal(await victim.page.evaluate(() => state.gpriv), null);
  await shot(six.host, 'six-desktop-elimination');
  await ready(six.players[1], six.roomId, 1, eliminated.revision, false);
  await shot(six.players[1], 'six-mobile-elimination');
  await describeRound(six, 'six-next');
  await voteRound(six, targetMost(six.spy), 'six-next');
  await settleAndRestart(six, null, 'six');
  if (cfg.stage === 'final') await changeAccount(six);
  await closeGame(six);
  if (cfg.stage !== 'final') return;

  const four = await session(4, '四');
  await oldCallbacks(four);
  await exerciseCompose(four);
  await describeRound(four, 'four');
  const tie = await voteRound(four, (uid, ids) => ids[(ids.indexOf(uid) + 1) % ids.length], 'four-tie');
  assert.equal(tie.last_ballot.tie, true);
  assert.equal(tie.last_ballot.eliminated_uid, null);
  await shot(four.host, 'four-desktop-tie');
  await ready(four.players[1], four.roomId, 1, tie.revision, false);
  await shot(four.players[1], 'four-mobile-tie');
  const firstOut = four.players.find(person => person.uid !== four.spy).uid;
  const lastOut = four.players.find(person => person.uid !== four.spy && person.uid !== firstOut).uid;
  await describeRound(four, 'four');
  await voteRound(four, targetMost(firstOut), 'four');
  await describeRound(four, 'four');
  await voteRound(four, targetMost(lastOut), 'four');
  await settleAndRestart(four, four.spy, 'four');
  await closeGame(four);

  await departureScenario();

  const eight = await session(8, '八');
  const current = await describeRound(eight, 'eight');
  const phone = eight.players[1];
  const target = eight.players[7].uid;
  await ready(phone, eight.roomId, 1, current.revision);
  const targetSelector = phone.page.locator(board + ' .spy-seat[data-uid="' + target + '"]');
  if (await targetSelector.count()) await phone.page.getByRole('button', {name:'上一页席位'}).tap();
  assert.equal(await targetSelector.count(), 0);
  await phone.page.getByRole('button', {name:'下一页席位'}).tap();
  await targetSelector.waitFor();
  assert.match(await targetSelector.getAttribute('aria-label'), /合成测试长昵称/);
  await shot(phone, 'eight-mobile-page-two');
  await commitAction(phone, eight, current, () => targetSelector.tap());
  evidence.checks.large_room = {count:8, mobile_page_two_vote:true, target};
  await closeGame(eight);
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({headless:true, args:['--disable-background-networking', '--disable-sync']});
    await run(browser);
    assert.deepEqual(evidence.page_errors, []);
    evidence.passed = true;
  } catch (error) {
    evidence.failure = String(error.stack || error);
    console.error(evidence.failure);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    save();
  }
  console.log(JSON.stringify({passed:evidence.passed || false, rooms:evidence.rooms.length,
    actions:evidence.requests.filter(request => request.op === 'action').length,
    screenshots:evidence.screenshots.length, page_errors:evidence.page_errors}));
})();
