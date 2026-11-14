"""Build static/trip_live.html: trip mode, exactly as it is, plus the live layer for the demo fair.

Every change to trip mode is listed here as a small patch, so the two stay the same apart from these:
  - the page always opens in trip mode, and the visitor picks a person instead of typing a study code;
  - the businesses' bots and Helmi's messages to them come from live AI agents on the stand's server (tools/live_adapter.js);
  - messages the visitor writes to a business get a live answer; questions Helmi can't answer itself go to the live AI;
  - a refresh keeps the trip, and the phone's back button goes back one screen;
  - the end of the trip offers "Play again" instead of the study's round-table questions.
"""
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/trip/Tell_Once_Trip_Mode.html"
OUT = sys.argv[2] if len(sys.argv) > 2 else "static/trip_live.html"
import json, subprocess
sys.path.insert(0, "tools")
import okafor_trip
WHO = {p["id"]: {"short": p.get("short", p["name"]), "who": p["who"]} for p in json.load(open("static/trip.json", encoding="utf-8"))["people"]}
ADAPTER = okafor_trip.js() + "\nconst LIVE_WHO=" + json.dumps(WHO, ensure_ascii=False) + ";\n" + open("tools/live_adapter.js", encoding="utf-8").read()
s = open(SRC, encoding="utf-8").read()


def patch(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"patch expected {count} match(es), found {n}: {old[:90]!r}")
    s = s.replace(old, new)


# 1. always trip mode
i = s.index("<script>", s.index("</style>"))
s = s[:i] + "<script>if(!(location.hash||'').startsWith('#trip'))history.replaceState(null,'','#trip');</script>\n" + s[i:]
patch("<title>Trip mode · Tell Once, Share Selectively</title>", "<title>Helmi Live · Trip</title>")

# 2. the welcome screen: pick a person (the study's code picked one at random)
patch("""   <div class="v-field"><label for="vcode" style="font-weight:600">Your code</label><input id="vcode" type="text" value="${esc(S.pid||(TRIP&&!BIZM&&rLatest())||randCode())}" autocomplete="off" style="min-height:48px;border:1px solid var(--ink);border-radius:12px;padding:0 12px;font-size:1.0625rem"><span class="tiny muted">Keep this code. If you were given a code, type it here instead. The app picks your person from it.</span></div>""",
      """   ${LIVE.picked?`<p class="small">You are playing <b>${esc(P().profile.name)}</b>. <button class="v-link" data-v="lland">Choose someone else</button></p>`:''}<fieldset class="v-field" ${LIVE.picked?'hidden':''}><legend style="font-weight:600;margin-bottom:6px">Who do you want to be?</legend><div class="tp-opts" role="radiogroup">${PERSONAS.map(p=>{ const pr=DATA[p].profile; return `<label class="v-card tp-opt ${S.persona===p?'on':''}"><input type="radio" name="lpick" value="${p}" ${S.persona===p?'checked':''}><span><b>${esc(pr.name)}, ${esc(pr.age)}</b><span class="small">${esc(pr.disability)}</span></span></label>`; }).join('')}</div></fieldset>""")
patch("""<button class="v-btn" data-v="begin">Start</button>`+(TRIP&&!BIZM?rStartCard():'');""", """<button class="v-btn" data-v="begin">Start</button>`;""")
patch("""  if(a==='begin'){ const c=(($('vcode').value||'').trim()||randCode()).slice(0,24); let per=S.persona, adv=S.advice, how='link';
    if(!FIXED){ const g=GROUPS[groupOf(c)]; per=g[0]; adv=HP.has('advice')?HP.get('advice')==='on':g[1]; how='code'; }""",
      """  if(a==='begin'){ const c=randCode(); const pk=document.querySelector('input[name="lpick"]:checked'); let per=pk?pk.value:S.persona, adv=false, how='fair';""")

# the study's "play again with the same code" check has no code to read here
patch("""  if(a==='begin'&&TRIP&&!BIZM){ const c0=(($('vcode').value||'').trim()).slice(0,24),""", """  if(a==='begin'&&TRIP&&!BIZM&&$('vcode')){ const c0=(($('vcode').value||'').trim()).slice(0,24),""")

# 3. the live agents: start, each place, decisions, stopping and sharing again, messages
patch("""else { TS().setupDone=1; tripPlan(); tripGo(0); } return; }""", """else { TS().setupDone=1; tripPlan(); LIVE.start(); tripGo(0); } return; }""")
patch("""function tripGo(i){ TS().i=i; V.autoNote=0; const st=tripPlan()[i]; if(st&&st.k==='chat'){ TS().chatStart=msgs(st.bid).length; msgAuto(st); } vGo({tab:'tstage',biz:null,fu:false}); }""",
      """function tripGo(i){ TS().i=i; V.autoNote=0; const st=tripPlan()[i]; LIVE.stop(st); if(st&&st.k==='chat'){ TS().chatStart=msgs(st.bid).length; msgAuto(st); } vGo({tab:'tstage',biz:null,fu:false}); }""")
patch("""  if(bid==='hotel'&&fields.length&&!msgs('hotel').length&&!window.__noAutoFU){""", """  LIVE.decided(bid,fields,dur,from);
  if(bid==='hotel'&&fields.length&&!msgs('hotel').length&&!window.__noAutoFU){""")
patch("""  log(on?'revoke':'restore',bid+' via '+from);
}""", """  log(on?'revoke':'restore',bid+' via '+from); LIVE.revoke(bid,on);
}""")
patch("""  const sess=S; setTimeout(()=>{ if(S!==sess||S.chatOff[bid]) return; msgs(bid).push({from:'biz',auto:1,text:(TRIP&&tripReply(bid,text))||(/\\?/.test(text)?'Thanks for asking. We’ll check and reply soon.':'Thank you, noted! See you soon.'),t:clock()}); S.unread[bid]=(V.open&&V.biz===bid&&V.fu)?0:(S.unread[bid]||0)+1; renderLive(); },1600); }""",
      """  LIVE.say(bid,text); }""")
patch("""  log('message from business',bid+' via '+from); return true; }""", """  log('message from business',bid+' via '+from); LIVE.echo(bid,text,from); return true; }""")
patch("""t.sentBy[st.id]='helmi'; t.chatStart=msgs(st.bid).length; meSend(st.bid,draftFor(st)); t.chats[st.id]=1; }""",
      """t.sentBy[st.id]='helmi'; t.chatStart=msgs(st.bid).length; LIVE.byHelmi=1; try{ meSend(st.bid,draftFor(st)); }finally{ LIVE.byHelmi=0; } t.chats[st.id]=1; }""")
# what the person sees of the live conversation
patch("""<p class="small">${esc(b.extra?b.why:yb(b).why)}</p></div>
   <button class="v-btn" data-v="topen" data-b="${b.id}">See what they ask</button>""",
      """<p class="small">${esc(b.extra?b.why:yb(b).why)}</p></div>${LIVE.askCard(b.id)}
   <button class="v-btn" data-v="topen" data-b="${b.id}">See what they ask</button>""")
patch("""   <button class="v-btn tp-fade" style="animation-delay:${0.4+b.moments.length*0.8}s" data-v="tnext">Continue</button>`; }""",
      """   ${LIVE.cons(b.id)}<button class="v-btn tp-fade" style="animation-delay:${0.4+b.moments.length*0.8}s" data-v="tnext">Continue</button>`; }""")
patch("""`<ol class="thread" aria-label="Messages">${L.map((m,i)=>m.from==='helmi'?""", """`<ol class="thread" aria-label="Messages">${L.map((m,i)=>m.from==='agent'?LIVE.agentLi(m):m.from==='helmi'?""")
patch("""   ${off?`<p class="note">You closed this chat.""", """   ${LIVE.typingLine(b.id)}${off?`<p class="note">You closed this chat.""")
patch("""helmi(L.length?`Your messages with ${esc(b.name)}. I watch for requests for your data and tell you if something looks wrong.`""",
      """helmi(L.length?`Your messages with ${esc(b.name)}. I talk to ${esc(b.__bot||'their bot')} for you here, live, and I watch for requests for your data.`""")
# Ask Helmi: what Helmi can't answer itself goes to the live AI
patch("""S.chat.push({me:1,t:q}); const h=helmiAnswer(q); S.chat.push({h});""",
      """S.chat.push({me:1,t:q}); let h=helmiAnswer(q); const idk=LIVE.nid&&/not sure what you mean/i.test(h); if(idk) h='<span class="muted">Thinking…</span>'; const hm={h}; S.chat.push(hm); if(idk) LIVE.ask(q,hm);""")
patch("""In this prototype I run inside the page, so nothing you type leaves it.""", """Questions I can’t answer myself go to the live AI at the stand.""")

# a rule changed in About me reaches the stand's server too (it decides whether Helmi refuses an offer outright)
patch("""    if(c==='rule'){ if(t.value==='ask') delete S.rules[t.dataset.k]; else S.rules[t.dataset.k]=t.value; log('rule',t.dataset.k+'='+t.value); say('Rule saved.'); }""",
      """    if(c==='rule'){ if(t.value==='ask') delete S.rules[t.dataset.k]; else S.rules[t.dataset.k]=t.value; log('rule',t.dataset.k+'='+t.value); say('Rule saved.'); LIVE.rules(); }""")

# a Messages tab, as in the fair version: every business on the trip, with its live conversation
patch("""const TTABS=[['tstage','Trip','trip'],['thelmi','Helmi','home'],['data','My data'],['me','About me'],['share','Sharing']];
function tNavOn(k){ if(k==='tstage') return V.tab==='tstage'&&!V.tAsk; if(k==='thelmi') return V.tab==='tstage'&&!!V.tAsk; return V.tab===k; }""",
      """const TTABS=[['tstage','Trip','trip'],['thelmi','Helmi','home'],['tmsgs','Messages','msgs'],['data','My data'],['me','About me'],['share','Sharing']];
function tNavOn(k){ if(k==='tstage') return V.tab==='tstage'&&!V.tAsk; if(k==='thelmi') return V.tab==='tstage'&&!!V.tAsk; if(k==='tmsgs') return V.tab==='tmsgs'||(V.tab==='trip'&&!!V.fu&&!!V.fromMsgs); return V.tab===k; }""")
patch("""const VIC={
""", """const VIC={
  msgs:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h12v8H8l-5 4V6z"/><path d="M15 9h6v8l-4-3h-2"/></svg>',
""")
patch("""else if(V.tab==='tstory') body=tStory();""", """else if(V.tab==='tstory') body=tStory(); else if(V.tab==='tmsgs') body=LIVE.inbox();""")
patch("""${k==='home'&&np?""", """${k==='tmsgs'&&LIVE.unread()?` <span class="badge" aria-label="${LIVE.unread()} new">${LIVE.unread()}</span>`:''}${k==='home'&&np?""")
patch("""!['tstage','data','me','share'].includes(V.tab)""", """!(['tstage','tmsgs','data','me','share'].includes(V.tab)||(V.tab==='trip'&&V.fu&&V.fromMsgs))""")
patch("""  if(a==='back'){ V.redo=false;""", """  if(a==='back'&&V.fromMsgs&&V.fu){ vGo({tab:'tmsgs',biz:null,fu:false,fromMsgs:false}); return; }
  if(a==='back'){ V.redo=false;""")
patch("""  if(a==='fu'){ vGo({tab:'trip',biz:bid,fu:true,vol:false,see:null,hist:false});""", """  if(a==='fu'){ vGo({tab:'trip',biz:bid,fu:true,vol:false,see:null,hist:false,fromMsgs:!!v.dataset.inbox});""")
patch("""function vTitle(){ """, """function vTitle(){ if(V.tab==='tmsgs') return 'Messages'; """)

# the fair's own choices, kept: which places to visit, and a starting point for the rules (careful, balanced or open)
patch("""if(TRIP){ tripYouData(); vGo({tab:'tconn'}); return; }""", """if(TRIP){ tripYouData(); vGo({tab:'tplaces'}); return; }""")
patch("""else if(V.tab==='tconn') body=tConn();""", """else if(V.tab==='tplaces') body=LIVE.places(); else if(V.tab==='thelmi') body=LIVE.helmiTab(); else if(V.tab==='tconn') body=tConn();""")
patch("""const pick=forced.concat(shuffle(elig.filter(x=>!x.force),r).slice(0,3)).map(makeExtra).filter(b=>b.fields.length);""",
      """const pick=(t.pick?elig.filter(x=>t.pick.includes(x.id)):forced.concat(shuffle(elig.filter(x=>!x.force),r).slice(0,3))).map(makeExtra).filter(b=>b.fields.length);""")
patch("""function tRules(){ return `<p class="tp-k">Set up Helmi · 6 of 6</p>`+helmi(`Any rules? For each item, should I always share it when a place asks, never share it, or ask you?`)+
   `<ul class="tp-rules">${tripRuleKeys().map(k=>{""", """function tRules(){ LIVE.presetFirst(); return `<p class="tp-k">Set up Helmi · 6 of 6</p>`+helmi(`Any rules? For each item, should I always share it when a place asks, never share it, or ask you? Start from one of these, then change anything.`)+LIVE.presetBtns()+
   `<ul class="tp-rules">${LIVE.ruleKeys().map(k=>{""")
# the Helmi tab: Ask Helmi, then what Helmi did at each place, one place at a time
patch("""  if(a==='tab'&&TRIP&&(v.dataset.t==='thelmi'||v.dataset.t==='tstage')){ V.tAsk=v.dataset.t==='thelmi'?1:0;""", """  if(a==='tab'&&TRIP&&v.dataset.t==='tstage'){ V.tAsk=0;""")
patch("""if(k==='thelmi') return V.tab==='tstage'&&!!V.tAsk;""", """if(k==='thelmi') return V.tab==='thelmi';""")
patch("""!(['tstage','tmsgs','data','me','share'].includes(V.tab)""", """!(['tstage','thelmi','tmsgs','data','me','share'].includes(V.tab)""")
patch("""function vTitle(){ if(V.tab==='tmsgs') return 'Messages'; """, """function vTitle(){ if(V.tab==='tmsgs') return 'Messages'; if(V.tab==='thelmi') return 'Helmi'; if(V.tab==='tplaces') return 'Your trip'; """)

# the landing page from the fair ("Send your Helmi on a trip"), and the Okafor family alongside trip mode's eight people
patch("""else if(V.tab==='tplaces') body=LIVE.places();""", """else if(V.tab==='land') body=LIVE.land(); else if(V.tab==='tplaces') body=LIVE.places();""")
patch("""function vTitle(){ if(V.tab==='tmsgs') return 'Messages';""", """function vTitle(){ if(V.tab==='land') return 'Helmi Live'; if(V.tab==='tmsgs') return 'Messages';""")
patch("""  const fields=p.f.filter(has); const moms=[]; if(p.m) moms.push(p.m);""", """  const fields=p.f.filter(has); const moms=[]; if(p.m) moms.push(p.m); if(p.ms) p.ms.forEach(m=>moms.push(m));""")
patch("""return {id:x.id,name:x.name,type:x.type,when:x.when,why:x.why,""", """return {id:x.id,name:x.name,type:x.type,when:p.when||x.when,why:p.why||x.why,""")
patch("""ravi:'Oslo'})[S.persona]""", """ravi:'Oslo',okafor:'Helsinki'})[S.persona]""")
patch("""XDATA[S.persona].wa.pain""", """(XDATA[S.persona]?XDATA[S.persona].wa.pain:LIVE.pain)""")
patch("""  const o=OWN[b.id], d=S.dec[b.id], g=granted(b.id), p=P().profile;""", """  const o=OWN[b.id]||{app:'Bookings',ref:'',item:b.name}, d=S.dec[b.id], g=granted(b.id), p=P().profile;""", 2)
patch("""function tfChar(per,x,face,t,moving){ const walk=moving?t*9:0, roll=moving?t*4:0;""", """function tfChar(per,x,face,t,moving){ const walk=moving?t*9:0, roll=moving?t*4:0;
  if(per==='okafor'){ const kid=(x0,o)=>`<g transform="translate(${x0} ${FLOOR}) scale(.6) translate(${-x0} ${-FLOOR})">${person(x0,FLOOR,o)}</g>`;
    return person(x,FLOOR,{id:'ada',skin:'#6b4428',hair:'#141010',style:'long',top:'#c0503a',legs:'#3b3f5c',face,walk})+person(x+190,FLOOR,{id:'chidi',skin:'#5a3a24',hair:'#141010',style:'short',top:'#2f6fb3',legs:C.ink,face,walk})
      +kid(x+330,{id:'amara',skin:'#6b4428',hair:'#141010',style:'long',top:'#e9c46a',legs:'#3b3f5c',face,walk})+kid(x+430,{id:'tobi',skin:'#5a3a24',hair:'#141010',style:'short',top:'#3f8f5a',legs:C.ink,face,walk}); }""")
# the Nokia network check is not part of this project
patch("""{id:'network',ord:9}""", """""")
patch("""+netCard();""", """;""")

# 4. refresh and the back button
patch("""function vGo(o){ Object.assign(V,o); V.shown=50; if(o.src) V.tbl=0; renderVault();""", """function vGo(o){ Object.assign(V,o); V.shown=50; if(o.src) V.tbl=0; renderVault(); LIVE.push(); LIVE.save();""")
patch("""  if(key){ let f=null; if(key.startsWith('v:')){""", """  LIVE.save();
  if(key){ let f=null; if(key.startsWith('v:')){""")

# 5. the end: play again instead of the study's questions
patch("""(S.prev?prevCompare()+`<button class="v-btn" data-v="tfinish">Two quick questions, then send</button>`:helmi(`Keep this screen open for the discussion. First, a few questions about what you would want in your own life.`)+`<button class="v-btn" data-v="tround">Your choices (before the discussion)</button>`); }""",
      """helmi(`Thank you for playing. Have a look at the stand screen: it shows how each business did.`)+`<button class="v-btn" data-v="liveagain">Play again as someone else</button>`; }""")

# 0. a stand-in for the live layer, so trip mode's start-up code can call it before the real one below is ready
i = s.index('(function(){\n"use strict";')
j = i + len('(function(){\n"use strict";')
s = s[:j] + "\nvar LIVE={nid:null,picked:false,land(){return ''},places(){return ''},helmiTab(){return ''},presetFirst(){},presetBtns(){return ''},ruleKeys(){return []},inbox(){return ''},unread(){return 0},rules(){},push(){},save(){},stop(){},start(){},decided(){},revoke(){},say(){},echo(){},ask(){},askCard(){return ''},cons(){return ''},typingLine(){return ''},agentLi(){return ''}};" + s[j:]

# 6. the live layer itself, inside trip mode's script so it can use trip mode's own functions
end = s.rindex("})();\n</script>")
s = s[:end] + ADAPTER + "\n" + s[end:]
open(OUT, "w", encoding="utf-8").write(s)
print("wrote", OUT, len(s))
