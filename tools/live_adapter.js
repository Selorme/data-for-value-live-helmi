/* ================================================================== Helmi live (demo fair, 18 Nov 2026)
   This is trip mode, unchanged, with one upgrade: the businesses' bots and Helmi's messages to them are written live by AI agents
   on the stand's server, and the stand screen follows every trip. What the person decides still happens here, on the request cards.
   The server only writes the words; the decisions travel from here to there. */
Object.assign(LIVE,{nid:null,seq:-1,vid:'',ready:Promise.resolve({}),quiet:0,byHelmi:0,busy:{},sheet:[],key:'helmi-live-trip',restoring:false,catching:false,nav:0});
try{ LIVE.vid=localStorage.getItem('helmi-vid')||''; if(!LIVE.vid){ LIVE.vid=Math.random().toString(36).slice(2,12); localStorage.setItem('helmi-vid',LIVE.vid); } }catch(e){ LIVE.vid=Math.random().toString(36).slice(2,12); }
window.__live=true; window.__noAutoFU=true;
/* the Okafor family: trip mode's format, built from the fair's data (tools/okafor_trip.py) */
(function(){ const O=LIVE_OKAFOR; if(DATA.okafor) return;
  DATA.okafor=O.data; DATA.okafor.__you=1; BIZ.okafor=O.biz;
  POOL.push(Object.assign({per:{},common:[]},O.kidsclub));
  Object.entries(O.extra).forEach(([id,e])=>{ const x=POOL.find(p=>p.id===id); if(x) x.per.okafor={f:e.f,m:e.m,ms:e.ms,when:e.when,why:e.why}; });
  OWNS.okafor=O.own; NET.okafor={phone:'+358400000909',checks:[]}; ACC.okafor=O.acc; HOME.okafor=O.home; WHO.okafor=O.who; STY.okafor=O.sty; LIVE.pain=O.pain;
  if(!PERSONAS.includes('okafor')) PERSONAS.push('okafor'); })();
/* the landing page: "Send your Helmi on a trip", then who you are today */
LIVE.land=function(){ const tile=p=>{ const w=LIVE_WHO[p]||{}, pr=DATA[p].profile; return `<li><button data-lland="${p}"><span><b>${esc(p==='okafor'?w.short||'The Okafors':pr.name.split(' ')[0])}</b><br><span class="small muted">${esc(w.who||pr.disability)}</span></span><span aria-hidden="true">›</span></button></li>`; };
  return `<div class="v-card" style="display:grid;gap:8px"><p class="v-big"><b>Send your Helmi on a trip</b></p>
     <p class="small">Every place on the trip has a bot that wants details before you arrive. You set rules for your Helmi. Then Helmi talks to each place in turn, live, and your phone buzzes when it needs you.</p>
     <p class="small muted">Everyone here is invented. No real personal data is used.</p></div>
   <h3 class="v-h">Who are you today?</h3><ul class="v-list">${PERSONAS.map(tile).join('')}</ul>`; };
document.addEventListener('click',e=>{ const t=e.target.closest('[data-lland]'); if(t){ e.stopPropagation(); const per=t.dataset.lland; S=fresh(per,'A',randCode()); S.advice=false; S.assign='fair'; LIVE.picked=true; renderAll(); vGo({tab:'start'}); return; }
  if(e.target.closest('[data-v="lland"]')){ e.stopPropagation(); LIVE.picked=false; vGo({tab:'land'}); } },true);
function lpost(path,body){ return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({vid:LIVE.vid,nid:LIVE.nid},body||{}))}).then(r=>r.json()).catch(()=>({ok:false})); }
const LRULE={auto:'share',ask:'ask',never:'never'};
LIVE.policy=()=>Object.fromEntries(Object.keys(P().fields).map(k=>[k,LRULE[ruleOf(k)]||'ask']));
LIVE.start=function(){ const plan=tripPlan().filter(s=>s.k==='req').map(s=>s.id), t=TS();
  const body={person:S.persona,places:plan,policy:LIVE.policy(),driven:true,fields:Object.fromEntries(plan.map(id=>[id,bz(id).fields.slice()])),
    setup:{auto:t.auto||'ask',advice:!!S.advice,msg:t.msg||'no',uns:t.uns||'wait',conn:Object.keys(t.conn||{}).filter(k=>t.conn[k])},locked:Object.keys(P().fields).filter(k=>tripLocked(k))};
  LIVE.ready=lpost('/api/start',body).then(j=>{ if(j&&j.ok){ LIVE.nid=j.nid; LIVE.seq=-1; LIVE.save(); } return j; }); return LIVE.ready; };
/* each place on the trip: its bot opens when the person reaches it; the stand may have changed what the bot asks for */
LIVE.stop=function(st){ if(!st||st.k!=='req') return; const id=st.id; LIVE.busy[id]=true;
  LIVE.ready.then(()=>lpost('/api/go',{place:id})).then(j=>{ const b=bz(id); if(j&&j.ok&&Array.isArray(j.keys)&&b&&!S.dec[id]){ const nf=b.fields.filter(k=>j.keys.includes(k)); if(nf.length&&nf.length!==b.fields.length){ b.fields=nf; renderVault(true); } } }); };
LIVE.decided=function(bid,fields,dur,from){ if(LIVE.quiet) return; const b=bz(bid); if(!b) return;
  const why={}; b.fields.forEach(k=>{ if(!fields.includes(k)) why[k]=tripLocked(k)?'noconn':ruleOf(k)==='never'?'rule':'you'; });
  LIVE.busy[bid]=true; LIVE.ready.then(()=>lpost('/api/decide',{place:bid,shares:fields,why,dur,from})); };
LIVE.rules=function(){ if(LIVE.nid) lpost('/api/policy',{policy:LIVE.policy()}); };
LIVE.revoke=function(bid,on){ if(LIVE.quiet) return; LIVE.busy[bid]=true; LIVE.ready.then(()=>lpost('/api/revoke',{place:bid,stop:!!on,shares:on?[]:granted(bid)})); };
LIVE.say=function(bid,text){ LIVE.busy[bid]=true; const by=LIVE.byHelmi?'helmi':''; LIVE.ready.then(()=>lpost('/api/say',{place:bid,text,by})); };
LIVE.echo=function(bid,text,from){ if(from==='live'||!LIVE.nid) return; lpost('/api/say',{place:bid,text,echo:1}); };
LIVE.ask=function(q,m){ const qid=Math.random().toString(36).slice(2,9); m.qid=qid; LIVE.ready.then(()=>lpost('/api/ask',{qid,text:q})).then(j=>{ if(!j||!j.ok){ m.h='I can’t reach the stand right now. Try again in a moment.'; renderVault(true); } }); };
/* what the person sees of the live conversations */
const lbot=id=>{ const b=bz(id); return (b&&b.__bot)||'their bot'; };
LIVE.lastBot=function(id){ const L=msgs(id); for(let i=L.length-1;i>=0;i--) if(L[i].from==='biz'&&L[i].live) return L[i]; return null; };
LIVE.askCard=function(id){ const m=LIVE.lastBot(id), b=bz(id);
  if(m) return `<div class="v-card live-card"><p class="tiny muted">${esc(lbot(id))} · ${esc(b.name)} · live AI</p><p>“${esc(m.text)}”</p></div>`;
  return LIVE.busy[id]?`<p class="small muted live-typing">${esc(b.name)}’s bot is writing…</p>`:''; };
LIVE.cons=function(id){ const b=bz(id); if(!b) return ''; return helmi(LIVE.busy[id]?`I’m telling ${esc(lbot(id))}, ${esc(b.name)}’s bot, what you decided. You can watch it live.`:`${esc(lbot(id))} has your answer.`)+chatBtn(b); };
LIVE.typingLine=function(id){ return LIVE.busy[id]?`<p class="small muted live-typing" aria-live="polite">${esc(lbot(id))} and Helmi are writing…</p>`:''; };
LIVE.agentLi=function(m){ const tags=[...(m.shared||[]).map(k=>`<span class="live-tag s">Shared: ${esc((P().fields[k]||{}).label||k)}</span>`),...(m.kept||[]).map(k=>`<span class="live-tag n">Kept: ${esc((P().fields[k]||{}).label||k)}</span>`)].join('');
  return `<li class="me live-agent"><span class="sr">Helmi, for you: </span>${esc(m.text)}${tags?`<span class="live-tags">${tags}</span>`:''}<span class="tiny muted">Helmi, for you · ${esc((m.t||'').slice(0,5))}${m.blocked?' · replaced with a safe line':''}</span></li>`; };
/* plan the trip: the five core places are on every trip; the extras are the visitor's choice */
const LCORE=['ins','rail','hotel','bistro','venue'];
LIVE.places=function(){ const t=TS(), elig=POOL.filter(x=>x.per[S.persona]); if(!t.pick) t.pick=elig.filter(x=>x.force).map(x=>x.id);
  const core=BIZ[S.persona].filter(b=>!b.extra&&LCORE.includes(b.id));
  const li=(id,name,type,when,why,on,dis)=>`<li><label class="sw-row"><span class="sw-txt"><b>${esc(name)}</b><span class="tiny muted">${esc(type)}${when?' · '+esc(String(when).replace(' · ',', ')):''}</span><span class="v-val">${esc(why||'')}</span></span><input type="checkbox" role="switch" class="sw-in" data-lplace="${id}" ${on?'checked':''} ${dis?'disabled':''}><span class="sw-ui" aria-hidden="true"></span></label></li>`;
  return `<p class="tp-k">Plan your trip</p>`+helmi(`Where does your trip take you? These ${core.length} places are on every trip. Add any extras you’d like to try. Each place asks for something different.`)+
   `<h3 class="v-h">On every trip</h3><ul class="v-sw">${core.map(b=>li(b.id,b.name,b.type,b.when,yb(b).why,true,true)).join('')}</ul>`+
   `<h3 class="v-h">Extras</h3><ul class="v-sw">${elig.map(x=>li(x.id,x.name,x.type,x.when,x.why,t.pick.includes(x.id),false)).join('')}</ul>`+
   `<p class="small muted">${core.length+t.pick.length} places on your trip.</p><button class="v-btn" data-v="lplaces">Next: set up Helmi</button>`; };
document.addEventListener('change',e=>{ const c=e.target.closest('[data-lplace]'); if(!c) return; const t=TS(), id=c.dataset.lplace; t.pick=(t.pick||[]).filter(x=>x!==id); if(c.checked) t.pick.push(id); delete t.plan; renderVault(true); });
document.addEventListener('click',e=>{ if(!e.target.closest('[data-v="lplaces"]')) return; e.stopPropagation(); const t=TS(); delete t.plan; tripPlan(); vGo({tab:'tconn'}); },true);
/* rules: start from careful, balanced or open (from the fair version), then change any line */
const LBULK=/^(bank\.|loc\.|msg\.|mail\.|web\.|photos\.|activity|notes\.|voice\.|phone\.)/;
function lpreset(name,k){ const f=F(k)||{}, bulk=f.kind==='bulk'||LBULK.test(k);
  if(name==='careful'){ if(f.kind==='need'||k==='diet'||k==='allergy') return 'auto'; if(k==='card'||k==='trip') return 'ask'; return 'never'; }
  if(name==='open'){ if(/^(msg\.|mail\.|photos\.|web\.|notes\.)/.test(k)) return 'ask'; return 'auto'; }
  if(f.kind==='need'||k==='trip'||k==='diet'||k==='allergy') return 'auto'; if(k==='id.dob'||bulk) return 'never'; return 'ask'; }
LIVE.ruleKeys=function(){ const seen=[]; tripPlan().filter(s=>s.k==='req').forEach(s=>{ const b=bz(s.id); if(b) b.fields.forEach(k=>{ if(!seen.includes(k)) seen.push(k); }); });
  const rank=k=>{ const f=F(k)||{}; return f.kind==='need'?0:f.kind==='bulk'?2:1; }; return seen.sort((a,b)=>rank(a)-rank(b)); };
LIVE.applyPreset=function(name){ const t=TS(); t.pre=name; Object.keys(P().fields).forEach(k=>{ const v=lpreset(name,k); if(v==='ask') delete S.rules[k]; else S.rules[k]=v; }); LIVE.rules(); };
LIVE.presetFirst=function(){ const t=TS(); if(t.pre===undefined) LIVE.applyPreset('balanced'); };
LIVE.presetBtns=function(){ const p=TS().pre; return `<div class="seg live-pre" role="group" aria-label="Start from">${[['careful','Careful'],['balanced','Balanced'],['open','Open']].map(([v,l])=>`<button type="button" data-lpre="${v}" aria-pressed="${p===v}">${l}</button>`).join('')}</div>`; };
document.addEventListener('click',e=>{ const b=e.target.closest('[data-lpre]'); if(!b) return; LIVE.applyPreset(b.dataset.lpre); renderVault(true); });
document.addEventListener('change',e=>{ if(e.target.matches&&e.target.matches('[data-vchg="rule"]')&&V.tab==='trules'){ TS().pre=null; setTimeout(()=>renderVault(true),0); } });
/* the Helmi tab: Ask Helmi, then what Helmi did, one place at a time; tap a place for the details */
LIVE.offers={};
LIVE.helmiTab=function(){ const L=tripPlan().filter(s=>s.k==='req').map(s=>bz(s.id)).filter(Boolean), here=(tripPlan()[TS().i]||{}).id;
  const why=(b,k)=>tripLocked(k)?'not connected':ruleOf(k)==='never'?'your rule':'you said no';
  const row=b=>{ const d=S.dec[b.id], g=d?sharedOf(b):[], asked=b.fields.length, started=d||msgs(b.id).length||LIVE.busy[b.id]||b.id===here;
    const st=!started?'Coming up':LIVE.busy[b.id]?'Talking now':d?(S.revoked[b.id]?'You stopped sharing':`Shared ${g.length} of ${asked}`):'Waiting for you';
    const items=[];
    if(started) items.push(`${esc(b.__bot||'Their bot')} asked for ${asked} thing${asked===1?'':'s'}: ${esc(b.fields.map(k=>lcl(F(k).label)).join(', '))}.`);
    if(d){ if(g.length) items.push(`I shared: ${esc(g.map(k=>lcl(F(k).label)).join(', '))}.`);
      const kept=b.fields.filter(k=>!g.includes(k)); if(kept.length) items.push(`I kept: ${esc(kept.map(k=>lcl(F(k).label)+' ('+why(b,k)+')').join(', '))}.`); }
    (LIVE.offers[b.id]||[]).forEach(o=>items.push(`${esc(b.name)} offered ${esc(o.offer)} for your ${esc(lcl(o.label))}: ${o.ok===true?'you said yes, so I shared it':o.ok===false?'you said no':'waiting for you'}.`));
    const lb=LIVE.lastBot(b.id); if(lb) items.push(`Last from ${esc(b.__bot||b.name)}: “${esc(lb.text.slice(0,160))}${lb.text.length>160?'…':''}”`);
    if(d&&b.moments&&b.moments.length){ const os=b.moments.map(m=>momOut(m,g)); const good=os.filter(o=>!o.bad&&!o.trade).length, tot=os.filter(o=>!o.trade).length; if(tot) items.push(`${good} of ${tot} moments went smoothly.`); }
    return `<details class="v-card live-doing" ${b.id===here?'open':''}><summary><span><b>${esc(b.name)}</b><br><span class="small muted">${esc(b.when?String(b.when).replace(' · ',', '):'')}</span></span><span class="pill ${LIVE.busy[b.id]?'acc':d?'good':''}">${st}</span></summary>
      ${items.length?`<ul class="v-plain">${items.map(x=>`<li>${x}</li>`).join('')}</ul>`:'<p class="small muted">Nothing yet.</p>'}
      ${started?`<div class="v-quick two">${chatBtn(b)}${d?`<button class="v-btn alt" data-v="see" data-b="${b.id}">See what they see</button>`:''}</div>`:''}</details>`; };
  return helmi(`Hi ${esc(first())}, I’m Helmi. Ask me anything, or tell me what to do. Below is what I’ve done for you at each place on your trip.`)+chatBox()+`<h3 class="v-h">What I’m doing</h3>`+L.map(row).join(''); };
/* the Messages tab: one conversation per business on the trip */
LIVE.unread=function(){ try{ return tripReqs().reduce((n,b)=>n+(S.unread[b.id]||0),0); }catch(e){ return 0; } };
LIVE.inbox=function(){ const L=tripReqs(), pl=tripPlan(), here=(pl[TS().i]||{}).id;
  const row=b=>{ const ms=msgs(b.id), m=ms.filter(x=>x.from!=='helmi').pop(), n=S.unread[b.id]||0;
    const st=LIVE.busy[b.id]?'<span class="pill acc">Talking</span>':S.dec[b.id]?'<span class="pill good">Done</span>':ms.length?'':'<span class="pill">Not yet</span>';
    const who=m?(m.from==='me'?'You: ':m.from==='agent'?'Helmi: ':(b.__bot||b.name)+': '):'';
    return `<li><button data-v="fu" data-b="${b.id}" data-inbox="1"><span><b>${esc(b.__bot?b.__bot+' · ':'')}${esc(b.name)}</b>${n?` <span class="badge" aria-label="${n} new">${n}</span>`:''}<br><span class="small muted">${m?esc(who+m.text.slice(0,70))+(m.text.length>70?'…':''):'No messages yet'}</span></span>${st}</button></li>`; };
  return helmi(`Each place on your trip has its own conversation. I talk to their bot for you here, live, and you can write to them yourself.`)+`<ul class="v-list">${L.map(row).join('')}</ul>`; };
/* an offer from a business: the person decides again */
LIVE.showSheet=function(){ let el=document.getElementById('live-sheet'); if(!el){ el=document.createElement('div'); el.id='live-sheet'; el.setAttribute('role','dialog'); el.setAttribute('aria-label','An offer'); document.getElementById('vault').appendChild(el); }
  const o=LIVE.sheet[0]; if(!o){ el.hidden=true; el.innerHTML=''; return; }
  const b=bz(o.place); el.hidden=false;
  el.innerHTML=helmi(`<b>${esc(b?b.name:o.pname)}</b> offers <b>${esc(o.offer)}</b> if you share your <b>${esc(lcl(F(o.k)?F(o.k).label:o.label))}</b>. You said no before. Change your mind?`)+
   `<div class="v-quick two"><button class="v-btn" data-live-ans="1">Share it</button><button class="v-btn alt" data-live-ans="0">Still no</button></div><p class="tiny muted">If you don’t answer in 45 seconds, I keep it.</p>`;
  try{ navigator.vibrate&&navigator.vibrate([150,80,150]); }catch(e){} };
document.addEventListener('click',e=>{ const a=e.target.closest('[data-live-ans]'); if(!a) return; const o=LIVE.sheet.shift(); if(!o) return; const ok=a.dataset.liveAns==='1';
  lpost('/api/answer',{place:o.place,k:o.k,ok});
  if(ok){ const d=S.dec[o.place]; const f=d?d.fields.slice():[]; if(!f.includes(o.k)) f.push(o.k); LIVE.quiet++; try{ decide(o.place,f,d?d.dur:'trip','offer'); }finally{ LIVE.quiet--; } renderLive(); }
  LIVE.showSheet(); renderVault(true); });
/* events from the server */
LIVE.on=function(t,d){
  const id=d.place, b=id&&bz(id);
  if(t==='place'&&b){ LIVE.busy[id]=true; b.__bot=d.bot; }
  else if(t==='msg'&&b){ const tm=clock();
    if(d.who==='bot'){ if(d.echo) return; if(d.to==='me'){ LIVE.busy[id]=false; bizSend(id,d.text,'live'); } else { msgs(id).push({from:'biz',text:d.text,t:tm,live:1,src:d.src}); if(!(V.tab==='trip'&&V.biz===id&&V.fu)) S.unread[id]=(S.unread[id]||0)+1; } }
    else if(d.who==='helmi') msgs(id).push({from:'agent',text:d.text,t:tm,shared:d.shared||[],kept:d.kept||[],blocked:d.blocked,src:d.src}); }
  else if(t==='stepin'&&d.offer){ (LIVE.offers[id]=LIVE.offers[id]||[]).push({k:d.k,offer:d.offer,label:d.label,ok:null}); LIVE.sheet.push({place:id,k:d.k,offer:d.offer,label:d.label,pname:d.pname}); if(!LIVE.restoring) LIVE.showSheet(); }
  else if((t==='stepin_done'||t==='stepin_timeout')){ const of=(LIVE.offers[id]||[]).find(o=>o.k===d.k); if(of) of.ok=t==='stepin_done'?!!d.ok:false; const i=LIVE.sheet.findIndex(o=>o.place===id&&o.k===d.k); if(i>=0){ LIVE.sheet.splice(i,1); LIVE.showSheet(); } }
  else if(t==='place_done'||t==='place_update'){ LIVE.busy[id]=false; }
  else if(t==='ask_reply'){ const m=S.chat.find(x=>x.qid===d.qid); if(m){ m.h=esc(d.a); const ch=Object.entries(d.rules||{}); ch.forEach(([k,v])=>{ if(v==='ask') delete S.rules[k]; else S.rules[k]=v==='share'?'auto':'never'; });
      if(ch.length) m.h+=`<br><span class="tiny"><b>Rule${ch.length>1?'s':''} saved:</b> ${ch.map(([k,v])=>esc(lcl(F(k).label))+': '+({share:'always share',ask:'ask me',never:'never share'})[v]).join('; ')}</span>`;
      if(READ&&!LIVE.restoring) speak(d.a); } }
  else if(t==='done'){ LIVE.story=d.story||null; }
  else if(t==='error'){ if(!LIVE.restoring&&d.text) say(d.text); }
  if(!LIVE.restoring){ renderLive(); renderVault(true); }
};
LIVE.feed=function(t,d){ if(!LIVE.nid||d.nid!==LIVE.nid) return; if(d.seq!=null){ if(d.seq<=LIVE.seq) return; if(d.seq>LIVE.seq+1){ LIVE.catchUp(); return; } LIVE.seq=d.seq; } LIVE.on(t,d); };
LIVE.catchUp=async function(){ if(!LIVE.nid||LIVE.catching) return; LIVE.catching=true;
  try{ const r=await (await fetch('/api/resume?vid='+encodeURIComponent(LIVE.vid),{cache:'no-store'})).json();
    if(r.ok&&r.nid===LIVE.nid){ const miss=r.events.filter(ev=>ev.seq>LIVE.seq); LIVE.restoring=true; miss.forEach(ev=>{ LIVE.seq=ev.seq; LIVE.on(ev.t,ev); }); LIVE.restoring=false; if(miss.length){ LIVE.showSheet(); renderLive(); renderVault(true); } } }
  catch(e){ LIVE.restoring=false; } finally{ LIVE.catching=false; } };
LIVE.connect=function(){ let es; try{ es=new EventSource('/events?vid='+encodeURIComponent(LIVE.vid)); }catch(e){ return; } let lost=false;
  es.onopen=()=>{ document.body.classList.add('live-on'); if(lost){ lost=false; LIVE.catchUp(); } };
  es.onerror=()=>{ lost=true; document.body.classList.remove('live-on'); };
  ['place','msg','stepin','stepin_done','stepin_timeout','place_done','place_update','ask','ask_reply','done','error','request','request_done','start','writing'].forEach(t=>es.addEventListener(t,e=>{ try{ LIVE.feed(t,JSON.parse(e.data)); }catch(_){} }));
  document.addEventListener('visibilitychange',()=>{ if(document.visibilityState==='visible') LIVE.catchUp(); }); };
/* a refresh keeps the trip: this phone saves where it was */
let liveSaveT;
LIVE.save=function(){ if(LIVE.restoring) return; clearTimeout(liveSaveT); liveSaveT=setTimeout(()=>{ try{ if(!S||!S.trip||!S.trip.setupDone&&V.tab==='start') return;
  localStorage.setItem(LIVE.key,JSON.stringify({S,V:{tab:V.tab,fromMsgs:!!V.fromMsgs,biz:V.biz||null,fu:!!V.fu,src:V.src||null,see:V.see||null,hist:!!V.hist,tAsk:!!V.tAsk,cb:V.cb||null},nid:LIVE.nid,seq:LIVE.seq,
    fields:Object.fromEntries(biz().map(b=>[b.id,b.fields])),bots:Object.fromEntries(biz().filter(b=>b.__bot).map(b=>[b.id,b.__bot])),busy:LIVE.busy,offers:LIVE.offers})); }catch(e){} },300); };
LIVE.forget=function(){ try{ localStorage.removeItem(LIVE.key); }catch(e){} };
LIVE.restore=function(){ let L=null; try{ L=JSON.parse(localStorage.getItem(LIVE.key)||'null'); }catch(e){} if(!L||!L.S||!L.S.persona) return false;
  try{ S=L.S; if(S.trip&&S.trip.plan){ const have=new Set(BIZ[S.persona].map(b=>b.id)); S.trip.plan.filter(s=>s.k==='req'&&!have.has(s.id)).forEach(s=>{ const x=POOL.find(p=>p.id===s.id); if(x){ const e=makeExtra(x); if(e) BIZ[S.persona].push(e); } }); }
    if(S.trip) tripYouData();
    biz().forEach(b=>{ if(L.fields&&L.fields[b.id]) b.fields=L.fields[b.id]; if(L.bots&&L.bots[b.id]) b.__bot=L.bots[b.id]; });
    LIVE.nid=L.nid; LIVE.seq=L.seq==null?-1:L.seq; LIVE.busy=L.busy||{}; LIVE.offers=L.offers||{}; if(LIVE.nid) LIVE.ready=Promise.resolve({ok:true});
    Object.assign(V,L.V||{}); V.open=true; renderAll(); renderVault(); return true; }catch(e){ console.warn('restore failed',e); LIVE.forget(); return false; } };
/* the phone's back button goes back one screen; during the trip it never goes back to an earlier stop */
const LSTAGE=['tstage','tcons'], LSETUP=['land','start','meet','tplaces','tconn','tauto','tadv','tmsg','tuns','trules'];
LIVE.snap=()=>({tab:V.tab,biz:V.biz||null,fu:!!V.fu,vol:!!V.vol,src:V.src||null,see:V.see||null,hist:!!V.hist,tAsk:!!V.tAsk,fromMsgs:!!V.fromMsgs});
LIVE.same=(a,b)=>!!a&&!!b&&['tab','biz','fu','vol','src','see','hist','tAsk','fromMsgs'].every(k=>(a[k]||null)===(b[k]||null));
LIVE.push=function(){ if(LIVE.nav) return; const s=LIVE.snap(); if(LIVE.same(s,history.state)) return; try{ history.pushState(s,''); LIVE.depth=(LIVE.depth||0)+1; }catch(e){} };
/* the app's own back arrow does the same as the phone's back button */
document.addEventListener('click',e=>{ const b=e.target.closest('[data-v="back"]'); if(!b||!(LIVE.depth>0)) return; e.stopPropagation(); e.preventDefault(); history.back(); },true);
window.addEventListener('popstate',e=>{ const s=e.state; LIVE.depth=Math.max(0,(LIVE.depth||0)-1); if(!s||!s.tab) return; LIVE.nav=1; try{
  const started=S&&S.trip&&S.trip.setupDone;
  if(started&&LSETUP.includes(s.tab)){ say('Your trip has started. Use the tabs at the bottom.'); history.pushState(LIVE.snap(),''); return; }
  if(LSTAGE.includes(s.tab)&&started){ const st=tripPlan()[TS().i]; const cons=st&&st.k==='req'&&S.dec[st.id]&&V.cb===st.id; Object.assign(V,{tab:cons?'tcons':'tstage',biz:null,fu:false,vol:false,src:null,see:null,hist:false,tAsk:!!s.tAsk}); }
  else Object.assign(V,{tab:s.tab,biz:s.biz,fu:s.fu,vol:s.vol,src:s.src,see:s.see,hist:s.hist,tAsk:s.tAsk,fromMsgs:!!s.fromMsgs});
  renderVault(); $('v-screen').scrollTop=0; }finally{ LIVE.nav=0; } });
/* start again as someone else */
document.addEventListener('click',e=>{ if(!e.target.closest('[data-v="liveagain"]')) return; e.stopPropagation(); LIVE.forget(); lpost('/api/leave',{}); location.hash='#trip'; location.reload(); },true);
/* boot: pick the trip up again after a refresh, then listen for the live agents */
(function(){ const st=document.createElement('style'); st.textContent=`
  #v-nav{grid-template-columns:repeat(6,minmax(0,1fr))} #v-nav button{font-size:.6875rem;min-width:0} #v-nav button span{white-space:nowrap} #v-nav button{position:relative} #v-nav button .badge{position:absolute;top:4px;left:calc(50% + 6px);margin:0}
  .live-pre{margin:4px 0 12px} .live-pre button{flex:1;min-height:44px;border:0;background:none;font:inherit;font-weight:600;cursor:pointer} .live-pre button[aria-pressed=true]{background:var(--ink);color:#fff}
  .live-doing summary{display:flex;justify-content:space-between;align-items:center;gap:10px;cursor:pointer;list-style:none} .live-doing summary::-webkit-details-marker{display:none}
  .live-doing[open] summary{margin-bottom:8px} .live-doing ul{display:grid;gap:6px}
  .live-card{border-left:4px solid var(--accent)} .live-card p:last-child{font-size:1rem;margin-top:4px}
  .live-typing{animation:livepulse 1.4s ease-in-out infinite} @keyframes livepulse{50%{opacity:.45}} @media (prefers-reduced-motion:reduce){.live-typing{animation:none}}
  .thread li.live-agent{background:var(--accent);color:#fff} .thread li.live-agent .tiny{color:rgba(255,255,255,.85)}
  .live-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px} .live-tag{font-size:.75rem;border-radius:999px;padding:2px 8px;background:rgba(255,255,255,.2)}
  #live-sheet{position:fixed;left:0;right:0;bottom:0;z-index:60;background:var(--paper,#fff);border-top:2px solid var(--ink);padding:14px 16px calc(14px + env(safe-area-inset-bottom));box-shadow:0 -10px 30px rgba(0,0,0,.2);max-width:560px;margin:0 auto}
  .live-badge{position:fixed;right:52px;top:21px;z-index:70;font:600 11px system-ui;padding:3px 8px;border-radius:999px;background:#ddd;color:#333;pointer-events:none;opacity:.9}
  body.live-on .live-badge{background:#1f7a4d;color:#fff}`; document.head.appendChild(st);
  const bd=document.createElement('span'); bd.className='live-badge'; bd.textContent='Live AI'; bd.setAttribute('aria-hidden','true'); document.body.appendChild(bd);
  if(LIVE.restore()){ LIVE.restoring=true; LIVE.showSheet(); LIVE.restoring=false; LIVE.catchUp(); } else { V.open=true; V.tab='land'; renderVault(); }
  try{ history.replaceState(LIVE.snap(),''); }catch(e){}
  LIVE.connect(); })();
