/* Trip replay film for Helmi live. Engine and scenes from the trip-mode demo. */
window.LiveFilm=(function(){
/* Cut-paper animation engine. Deterministic: renderAt(seconds) draws one frame. */
const FPS = 24;
const FLOOR = 820;
const C = {
  wall:'#f1e3c8', wall2:'#e9d5b0', floor:'#c9a27a', floor2:'#b88f66', ink:'#2a2420', cream:'#fff8ec',
  teal:'#2f7f7a', teal2:'#245f5b', mustard:'#e2a33b', coral:'#df6a4f', navy:'#2c3e5c', navy2:'#1f2d45',
  sky:'#bcd6e3', snow:'#ffffff', green:'#3f8f5a', red:'#b8432f', grey:'#8d8a84', paper:'#fbf4e6',
  skinA:'#eab894', skinE:'#c48a63', skinS1:'#8d5a3b', skinS2:'#f0c7a4', hairA:'#4a2e1f', hairE:'#7d3519', lab:'#e1b46f', lab2:'#c99a52'
};
let FRAME = 0, T = 0;
/* ---------- helpers ---------- */
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const lerp=(a,b,u)=>a+(b-a)*u;
const ease=u=>{u=clamp(u); return u<.5?2*u*u:1-Math.pow(-2*u+2,2)/2;};
const prog=(t,a,b)=>clamp((t-a)/(b-a));
function hash(s){let h=2166136261; for(let i=0;i<s.length;i++){h^=s.charCodeAt(i); h=Math.imul(h,16777619);} return ((h>>>0)%10000)/10000;}
/* stop-motion boil: small offsets that change every 2 frames */
function boil(id,amt=1){return '';} /* stop-motion jitter removed: calmer to watch */
const G=(tr,inner,extra='')=>`<g transform="${tr}" ${extra}>${inner}</g>`;
const cut=(id,inner,tr='')=>`<g transform="${tr} ${boil(id)}" filter="url(#sh)">${inner}</g>`;
const R=(x,y,w,h,f,rx=0,extra='')=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${f}" ${extra}/>`;
const Ci=(x,y,r,f,extra='')=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${f}" ${extra}/>`;
const P=(d,f,extra='')=>`<path d="${d}" fill="${f}" ${extra}/>`;
const L=(x1,y1,x2,y2,s,w=6,extra='')=>`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${s}" stroke-width="${w}" stroke-linecap="round" ${extra}/>`;
const Tx=(x,y,s,txt,f=C.ink,w=700,anchor='middle',extra='')=>`<text x="${x}" y="${y}" font-size="${s}" font-weight="${w}" fill="${f}" text-anchor="${anchor}" font-family="Archivo, 'Helvetica Neue', Arial, sans-serif" ${extra}>${txt}</text>`;
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');

/* ---------- sets ---------- */
function room(wall=C.wall,floor=C.floor){return R(-200,-200,2320,FLOOR+200,wall)+R(-200,FLOOR,2320,500,floor)+R(-200,FLOOR-14,2320,18,C.floor2);}
function windowSnow(x,y,w,h,t){let s=R(x-14,y-14,w+28,h+28,C.cream,6)+R(x,y,w,h,'#9fc3d6')+R(x,y+h*.72,w,h*.28,'#e9f2f6');
  // distant roofs
  s+=P(`M${x} ${y+h*.75} l${w*.2} -${h*.18} l${w*.2} ${h*.12} l${w*.25} -${h*.22} l${w*.35} ${h*.2} v${h*.1} h-${w} z`,'#7f9fb0');
  for(let i=0;i<26;i++){const sx=x+((hash('sx'+i)*w + t*14*(0.5+hash('sv'+i)))%w); const sy=y+((hash('sy'+i)*h + t*60*(0.6+hash('sw'+i)))%h); s+=Ci(sx.toFixed(1),sy.toFixed(1),3+hash('sr'+i)*3,'#fff');}
  s+=R(x+w/2-5,y,10,h,C.cream)+R(x,y+h/2-5,w,10,C.cream);
  return cut('win'+x,s);}
function sign(x,y,w,h,txt,sub,bg=C.navy,fg='#fff'){return cut('sign'+x+y,R(x,y,w,h,bg,10)+Tx(x+w/2,y+h/2+(sub?-4:12),sub?34:38,esc(txt),fg)+(sub?Tx(x+w/2,y+h/2+34,22,esc(sub),fg,500):''));}
function clock(x,y,hh,mm,r=56){const ha=((hh%12)+mm/60)*30, ma=mm*6;
  return cut('clock'+x,Ci(x,y,r+8,C.ink)+Ci(x,y,r,C.cream)+[0,90,180,270].map(a=>L(x+Math.sin(a*Math.PI/180)*(r-10),y-Math.cos(a*Math.PI/180)*(r-10),x+Math.sin(a*Math.PI/180)*(r-4),y-Math.cos(a*Math.PI/180)*(r-4),C.ink,4)).join('')+
   L(x,y,x+Math.sin(ha*Math.PI/180)*r*.5,y-Math.cos(ha*Math.PI/180)*r*.5,C.ink,8)+L(x,y,x+Math.sin(ma*Math.PI/180)*r*.8,y-Math.cos(ma*Math.PI/180)*r*.8,C.ink,5)+Ci(x,y,6,C.coral)
   +Tx(x,y+r+40,26,`${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}`,C.ink,700));}
function desk(x,w,h,col=C.teal,top=C.cream){return cut('desk'+x+h,R(x,FLOOR-h,w,h,col,4)+R(x-12,FLOOR-h-16,w+24,20,top,4)+R(x+20,FLOOR-h+30,w-40,8,'rgba(0,0,0,.12)'));}
function plant(x){return cut('plant'+x,R(x-30,FLOOR-80,60,80,C.coral,6)+P(`M${x} ${FLOOR-80} q-60 -60 -30 -140 q20 60 30 140 q10 -110 50 -150 q-10 90 -50 150z`,C.green));}
function door(x,label,open=0){return cut('door'+x,R(x-10,FLOOR-430,200,430,C.cream,4)+R(x,FLOOR-420,180,420,open?C.ink:'#a5714a',2)+(open?'':Ci(x+150,FLOOR-210,9,C.mustard))+(label?R(x+40,FLOOR-480,100,40,C.navy,6)+Tx(x+90,FLOOR-451,24,label,'#fff'):''));}
function lift(x){return cut('lift'+x,R(x,FLOOR-430,190,430,'#9aa3a8',4)+R(x+8,FLOOR-422,84,422,'#b9c1c5')+R(x+98,FLOOR-422,84,422,'#b9c1c5')+Ci(x+215,FLOOR-230,12,C.mustard)+Tx(x+95,FLOOR-450,26,'LIFT',C.ink));}
function steps(x,n=2,w=420,stepH=46){let s=''; for(let i=0;i<n;i++) s+=R(x+i*0,FLOOR-(i+1)*stepH,w-i*0,stepH,i%2?C.floor2:'#a87d55'); return cut('steps'+x,s);}
function table(x,y=FLOOR,top=C.cream){return cut('tab'+x+y,R(x-110,y-170,220,22,top,6)+R(x-10,y-150,20,150,C.ink)+R(x-60,y-8,120,10,C.ink,4)+Ci(x-30,y-185,14,'#fff')+R(x+20,y-205,12,30,C.coral,3));}
function bed(x,h){return cut('bed'+x+h,R(x,FLOOR-h,420,h-30,'#f6efe2',10)+R(x,FLOOR-h-10,420,30,'#cfe3e6',10)+R(x+10,FLOOR-h-46,110,40,'#fff',16)+R(x-14,FLOOR-h-130,26,h+130,'#a5714a',6)+R(x+20,FLOOR-30,20,30,C.ink)+R(x+380,FLOOR-30,20,30,C.ink));}
function shower(x){let s=R(x,FLOOR-520,330,520,'#dfeef0'); for(let i=0;i<6;i++) for(let j=0;j<8;j++) s+=R(x+i*55+4,FLOOR-520+j*65+4,47,57,'#cfe5e8',3);
  s+=L(x+250,FLOOR-500,x+250,FLOOR-420,'#8a9599',10)+P(`M${x+215} ${FLOOR-420} h70 l-10 18 h-50z`,'#8a9599')+R(x+40,FLOOR-280,120,16,'#8a9599',4)+R(x+40,FLOOR-264,12,60,'#8a9599')+L(x+190,FLOOR-330,x+300,FLOOR-330,C.mustard,10);
  return cut('shower'+x,s);}
function bathtub(x){return cut('tub'+x,R(x,FLOOR-520,330,520,'#dfeef0')+R(x-20,FLOOR-170,370,170,'#ffffff',24)+R(x-20,FLOOR-170,370,24,'#e7eef0',12)+L(x+40,FLOOR-260,x+140,FLOOR-260,'#8a9599',10)+Tx(x+165,FLOOR-60,30,'BATHTUB',C.grey));}
function tablet(x,y,w,img,tilt=0){const h=w*0.72; return cut('tablet'+x,G(`rotate(${tilt} ${x+w/2} ${y+h/2})`,R(x-12,y-12,w+24,h+24,C.ink,18)+`<image href="${IMG[img]}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMin slice"/>`));}
function clipboard(x,y,lines){return cut('clip'+x,R(x,y,260,330,'#a5714a',10)+R(x+18,y+30,224,282,'#fff',4)+R(x+90,y-12,80,32,'#8a9599',6)+lines.map((l,i)=>Tx(x+30,y+80+i*44,i?24:26,esc(l),C.ink,i?500:700,'start')).join(''));}
function bubble(x,y,w,txt,size=34,tail='left'){const lines=Array.isArray(txt)?txt:[txt]; const h=40+lines.length*size*1.25;
  return cut('bub'+x+y,R(x,y,w,h,'#fff',26)+(tail==='left'?P(`M${x+50} ${y+h-2} l-10 40 l50 -40z`,'#fff'):P(`M${x+w-60} ${y+h-2} l10 40 l-50 -40z`,'#fff'))+lines.map((l,i)=>Tx(x+w/2,y+20+size+i*size*1.25,size,esc(l),C.ink,700)).join(''));}
function lockIcon(x,y,open,s=1){return G(`translate(${x} ${y}) scale(${s})`,(open?P('M-14 -6 v-16 a14 14 0 0 1 28 0','none',`stroke="${C.green}" stroke-width="7" transform="translate(-16 -2)"`):P('M-14 -6 v-14 a14 14 0 0 1 28 0 v14','none',`stroke="${C.ink}" stroke-width="7"`))+R(-22,-8,44,36,open?C.green:C.ink,6));}

/* ---------- characters ---------- */
function head(x,y,skin,hair,style,face='smile',r=46){let s='';
  if(style==='long') s+=P(`M${x-r-6} ${y-6} q0 -${r+16} ${r+6} -${r+16} q${r+6} 0 ${r+6} ${r+16} v${r*1.9} h-${2*r+12}z`,hair);
  if(style==='bob') s+=P(`M${x-r-8} ${y+8} q0 -${r+22} ${r+8} -${r+22} q${r+8} 0 ${r+8} ${r+22} v${r*.9} h-${2*r+16}z`,hair);
  s+=Ci(x,y,r,skin);
  if(style==='bob') s+=P(`M${x-r-4} ${y-4} q${r*.4} -${r*1.25} ${r*1.6} -${r*.85} q-${r*.6} ${r*.2} -${r*1.2} ${r*.9}z`,hair);
  if(style==='long') s+=P(`M${x-r} ${y-8} q${r} -${r*1.3} ${2*r} 0 q-${r*.8} -${r*.5} -${2*r} 0z`,hair);
  if(style==='short') s+=P(`M${x-r} ${y-6} q0 -${r+10} ${r} -${r+10} q${r} 0 ${r} ${r+10} q-${r*.5} -${r*.4} -${r} -${r*.35} q-${r*.6} 0 -${r} ${r*.35}z`,hair);
  if(style==='bun') s+=Ci(x-r*.6,y-r*.9,r*.45,hair)+P(`M${x-r} ${y-4} q0 -${r+8} ${r} -${r+8} q${r} 0 ${r} ${r+8} q-${r} -${r*.5} -${2*r} 0z`,hair);
  s+=Ci(x+r*.35,y-4,5,C.ink);
  if(face==='smile') s+=P(`M${x+r*.12} ${y+16} q${r*.25} ${r*.22} ${r*.5} 0`,'none',`stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`);
  else if(face==='flat') s+=L(x+r*.15,y+20,x+r*.55,y+18,C.ink,4);
  else if(face==='sad') s+=P(`M${x+r*.12} ${y+24} q${r*.25} -${r*.18} ${r*.5} 0`,'none',`stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`);
  s+=Ci(x+r*.35,y+10,7,'rgba(223,106,79,.35)');
  return s;}
/* Aino in her wheelchair, facing right. (x,y)=ground under big wheel. */
function aino(x,y,o={}){const s=o.s||1, roll=o.roll||0, arm=o.arm||'rest', face=o.face||'smile', id=o.id||'aino';
  let w=''; const wy=-108;
  // chair back + seat
  w+=R(-78,-330,20,170,C.teal2,6)+R(-70,-196,170,20,C.ink,6);
  // body: thighs, shins, shoes
  w+=R(-55,-238,160,46,C.navy,20)+R(80,-230,44,150,C.navy,18)+R(84,-92,70,26,C.ink,12);
  // torso
  w+=R(-62,-410,92,190,C.mustard,34);
  // arm
  if(arm==='phone') w+=L(-20,-370,44,-290,C.mustard,30)+L(44,-290,92,-340,C.skinA,22)+R(80,-392,44,74,C.ink,8)+R(85,-386,34,60,'#9fd0d8',4);
  else if(arm==='up') w+=L(-20,-370,40,-300,C.mustard,30)+L(40,-300,110,-330,C.skinA,22);
  else if(arm==='lap') w+=L(-20,-370,30,-290,C.mustard,30)+L(30,-290,90,-250,C.skinA,22);
  else w+=L(-20,-370,0,-250,C.mustard,30)+L(0,-250,20,-170,C.skinA,22);
  w+=head(-14,-462,C.skinA,C.hairA,'bob',face,48);
  // wheel
  let sp=''; for(let i=0;i<8;i++){const a=roll+i*Math.PI/4; sp+=L(0,wy,Math.cos(a)*92,wy+Math.sin(a)*92,'#6b6560',4);}
  w+=`<circle cx="0" cy="${wy}" r="104" fill="none" stroke="${C.ink}" stroke-width="14"/><circle cx="0" cy="${wy}" r="88" fill="none" stroke="#8a9599" stroke-width="5"/>`+sp+Ci(0,wy,14,C.ink);
  w+=L(40,-176,128,-60,C.ink,10)+Ci(128,-26,26,C.ink)+Ci(128,-26,10,'#8a9599');
  return cut(id,w,`translate(${x} ${y}) scale(${s})`);}
/* standing person facing right (dir=1) or left (dir=-1). */
function person(x,y,o={}){const s=o.s||1, dir=o.dir||1, id=o.id||('p'+x), skin=o.skin||C.skinS2, hair=o.hair||C.ink, style=o.style||'short', top=o.top||C.navy, legs=o.legs||C.ink, arm=o.arm||'down', face=o.face||'smile', walk=o.walk||0;
  let w=''; const sw=Math.sin(walk)*22;
  if(o.seated){ w+=R(-40,-250,170,44,legs,18)+R(96,-240,40,240,legs,14)+R(96,-22,70,22,C.ink,8); w+=R(-48,-470,96,240,top,38); }
  else { w+=R(-30+sw*.5,-250,30,250,legs,12)+R(4-sw*.5,-250,30,250,legs,12)+R(-36+sw*.5,-20,46,22,C.ink,8)+R(-2-sw*.5,-20,46,22,C.ink,8);
  w+=R(-48,-470,96,240,top,38); }
  if(o.badge) w+=R(10,-420,30,20,'#fff',3);
  const A={down:[-10,-440,-6,-320,0,-240],desk:[10,-440,60,-350,120,-360],phone:[10,-440,50,-360,70,-430],point:[10,-440,90,-400,160,-430],hold:[10,-440,60,-360,100,-360],wave:[10,-440,60,-500,70,-580],harness:[10,-440,40,-370,70,-300],elbow:[10,-440,50,-350,50,-300]}[arm]||[-10,-440,-6,-320,0,-240];
  w+=L(A[0],A[1],A[2],A[3],top,28)+L(A[2],A[3],A[4],A[5],skin,20);
  if(arm==='phone') w+=R(A[4]-6,A[5]-46,36,62,C.ink,7);
  if(arm==='hold'&&o.holdItem) w+=o.holdItem;
  w+=head(4,-522,skin,hair,style,face,46);
  if(o.earbud) w+=Ci(-12,-516,7,'#fff');
  return cut(id,w,`translate(${x} ${y}) scale(${s*dir} ${s})`);}
/* Kide the guide dog. facing right. lying=true for lying down */
function kide(x,y,o={}){const s=o.s||1, walk=o.walk||0, lying=o.lying, id=o.id||'kide', dir=o.dir||1; let w='';
  if(lying){ w+=P('M-130 -10 q0 -70 120 -70 q90 0 110 50 l0 20z',C.lab)+Ci(120,-70,40,C.lab)+P('M140 -70 q40 0 50 18 q-14 16 -50 10z',C.lab)+Ci(186,-58,8,C.ink)+P('M98 -96 q-20 10 -10 52 q16 -16 22 -44z',C.lab2)+Ci(132,-80,5,C.ink)+P('M-130 -20 q-50 0 -70 -14','none',`stroke="${C.lab}" stroke-width="14" stroke-linecap="round"`); }
  else { const a=Math.sin(walk)*16;
    w+=R(-110+a*.6,-120,24,120,C.lab2,10)+R(-70-a*.6,-120,24,120,C.lab,10)+R(60+a*.6,-120,24,120,C.lab2,10)+R(96-a*.6,-120,24,120,C.lab,10);
    w+=P('M-130 -110 q0 -70 120 -70 h110 q50 0 50 60 v20 h-280z',C.lab)+Ci(170,-190,44,C.lab)+P('M196 -192 q46 2 54 24 q-16 18 -54 10z',C.lab)+Ci(246,-176,9,C.ink)+P('M146 -222 q-22 10 -12 56 q18 -18 24 -48z',C.lab2)+Ci(184,-202,6,C.ink)+P('M-130 -150 q-50 -10 -64 -50','none',`stroke="${C.lab}" stroke-width="16" stroke-linecap="round"`);
    // harness
    w+=R(-20,-186,130,26,C.coral,8)+R(70,-200,22,70,C.coral,6)+L(-10,-178,-60,-300,C.ink,8); }
  return cut(id,w,`translate(${x} ${y}) scale(${s*dir} ${s})`);}
/* Elina with harness hand (left) and phone/other arm */
function elina(x,y,o={}){return person(x,y,Object.assign({id:'elina',skin:C.skinE,hair:C.hairE,style:'long',top:C.teal,legs:C.navy,earbud:true},o));}
function staff(x,y,o={}){return person(x,y,Object.assign({top:C.navy,badge:true},o));}
/* big phone close-up with real app screen */
function bigPhone(cx,cy,img,o={}){const w=o.w||410, h=w*2.05, x=cx-w/2, y=cy-h/2; let s='';
  s+=R(x-22,y-22,w+44,h+44,C.ink,58)+`<clipPath id="pc${cx}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="36"/></clipPath>`;
  s+=`<g clip-path="url(#pc${cx})">${R(x,y,w,h,'#fff')}<image href="${IMG[img]}" x="${x}" y="${y}" width="${w}" height="${w*1600/780}" preserveAspectRatio="xMidYMin slice"/>${o.overlay||''}</g>`;
  s+=R(cx-60,y-8,120,14,'#3a332e',7);
  return cut('phone'+cx,s,o.tr||'');}
function thumb(x,y,press){return cut('thumb',P(`M${x} ${y+(press?6:0)} q-30 10 -40 90 q-10 120 30 200 h170 q20 -140 -40 -230 q-40 -60 -120 -60z`,C.skinA)+P(`M${x-6} ${y+(press?6:0)} q-14 4 -18 36 q24 10 46 -6 q0 -30 -28 -30z`,'#f5d2b6'),'');}
function ripple(x,y,t){let s=''; for(let i=0;i<3;i++){const u=((t*0.45+i/3)%1); s+=`<circle cx="${x}" cy="${y}" r="${30+u*120}" fill="none" stroke="${C.teal}" stroke-width="${6*(1-u)+1}" opacity="${(1-u).toFixed(2)}"/>`;} return s;}
/* title cards */
function titleCard(lines,t,bg=C.teal,fg='#fff',sub){let s=R(-200,-200,2320,1480,bg);
  lines.forEach((ln,li)=>{const chars=[...ln]; const total=chars.length; const startX=960-total*34; chars.forEach((ch,i)=>{const u=ease(prog(t,0.1+i*0.03+li*0.3,0.9+i*0.03+li*0.3)); if(ch===' ')return;
    s+=G(`translate(${startX+i*68+34} ${470+li*130-(1-u)*60}) rotate(${(hash('r'+i+li)-.5)*3})`,R(-30,-62,60,84,C.cream,6,`filter="url(#sh)"`)+Tx(0,4,64,esc(ch),bg,800),`opacity="${u}"`);});});
  if(sub) s+=Tx(960,840,40,esc(sub),fg,600,'middle',`opacity="${ease(prog(t,1.6,2.4))}"`);
  return s;}
function rewindFx(t){let s=''; for(let i=0;i<8;i++){const y=((i*135+t*520)%1080); s+=R(-20,y,1960,3,'rgba(255,255,255,.45)');}
  s+=G('translate(190 140)',P('M0 -40 l-50 40 l50 40z M-56 -40 l-50 40 l50 40z','#fff','opacity=".85"'));
  return s;}
function labelTag(txt,good){if(window.__noLabel) return ''; return G('translate(70 70)',R(0,0,txt.length*22+70,70,good?C.green:'#5c5852',35,`filter="url(#sh)"`)+Ci(38,35,12,'#fff')+Tx(62,48,34,esc(txt),'#fff',800,'start'));}

/* ---------- player ---------- */
let SCENES=[], CAPS=[], DURATION=0, GREYS=[];
function film(def){SCENES=def.scenes; DURATION=def.duration; CAPS=[];
  SCENES.forEach(sc=>{ if(!sc.say) return; const words=sc.say.split(' '); const chunks=[]; let cur=[];
    words.forEach((wd,i)=>{cur.push(wd); const left=words.length-1-i; const endS=/[.!?]["”]?$/.test(wd), endC=/[,;:]$/.test(wd);
      if(left===0) return; if((endS&&cur.length>=4)||(endC&&cur.length>=10)||cur.length>=16){ if(left<4&&!endS){return;} chunks.push(cur.join(' ')); cur=[];}});
    if(cur.length){ if(cur.length<3&&chunks.length) chunks[chunks.length-1]+=' '+cur.join(' '); else chunks.push(cur.join(' ')); }
    const a=sc.from+(sc.sayDelay||0.4), b=sc.sayEnd?sc.from+sc.sayEnd:sc.to-0.3, total=words.length; let acc=0;
    chunks.forEach(ch=>{const n=ch.split(' ').length; CAPS.push({from:a+(b-a)*acc/total,to:a+(b-a)*(acc+n)/total,text:ch}); acc+=n;});
    if(sc.helmi){ const H=sc.helmi, ss=H.text.match(/[^.:]+[.:]/g)||[H.text], tw=H.text.split(' ').length; let ac=0; const h0=sc.from+H.at, h1=sc.from+H.end;
      const grp=[]; let cur=''; ss.forEach(x=>{ if((cur+x).split(' ').length>14&&cur){ grp.push(cur.trim()); cur=x; } else cur+=x; }); if(cur.trim()) grp.push(cur.trim());
      grp.forEach(g=>{ const n=g.split(' ').length; CAPS.push({from:h0+(h1-h0)*ac/tw,to:h0+(h1-h0)*(ac+n)/tw,text:'Helmi: '+g}); ac+=n; }); } });
  CAPS.sort((x,y)=>x.from-y.from);
}
function renderAt(t){T=t; FRAME=Math.floor(t*FPS+1e-6); if(playing) window.__filmMax=Math.max(window.__filmMax||0,t);
  const sc=SCENES.find(s=>t>=s.from&&t<s.to)||SCENES[SCENES.length-1];
  const lt=t-sc.from, d=sc.to-sc.from;
  let inner=sc.draw(lt,d);
  const grey=sc.grey?'url(#grey)':'none';
  // quick paper wipe in first 0.25s of each scene
  const wipe=lt<0.5&&!sc.noWipe?R(-10,-10,1940,1100,C.paper,0,`opacity="${(1-ease(lt/0.5)).toFixed(3)}"`):'';
  document.getElementById('world').innerHTML=`<g filter="${grey}">${inner}</g>${wipe}`;
  const cap=CAPS.find(c=>t>=c.from&&t<c.to);
  const ce=document.getElementById('cap'); ce.textContent=cap?cap.text:''; ce.style.opacity=cap?1:0;
  const pr=document.getElementById('prog'); if(pr) pr.value=t;
  const tm=document.getElementById('tm'); if(tm) tm.textContent=fmtT(t)+' / '+fmtT(DURATION);
}
const fmtT=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
window.renderAt=renderAt;
let playing=false, t0=0, tStart=0, raf=null;
function loop(){ if(!playing) return; let t=tStart+(performance.now()-t0)/1000; if(t>=DURATION){t=DURATION-0.001; stop();}
  const ft=Math.floor(t*FPS)/FPS; if(ft!==T) renderAt(ft); raf=requestAnimationFrame(loop);}
function play(){ if(playing) return; const au=document.getElementById('music'); if(T>=DURATION-0.05) T=0; playing=true; tStart=T; t0=performance.now(); if(au){au.currentTime=T; au.play().catch(()=>{});} document.getElementById('pp').textContent='Pause'; document.getElementById('pp').setAttribute('aria-label','Pause'); loop();}
function stop(){ playing=false; cancelAnimationFrame(raf); const au=document.getElementById('music'); if(au) au.pause(); document.getElementById('pp').textContent='Play'; document.getElementById('pp').setAttribute('aria-label','Play');}
function initPlayer(){
  const pp=document.getElementById('pp'), pr=document.getElementById('prog');
  pr.max=DURATION; pp.onclick=()=>playing?stop():play();
  pr.oninput=()=>{const was=playing; stop(); renderAt(+pr.value); if(was) play();};
  document.getElementById('cc').onchange=e=>document.getElementById('cap').hidden=!e.target.checked;
  const seek=d=>{const was=playing; stop(); renderAt(Math.max(0,Math.min(DURATION,T+d))); if(was) play();};
  const wrap=document.querySelector('.wrap');
  const fsEl=()=>document.fullscreenElement||document.webkitFullscreenElement;
  const fsBtn=document.getElementById('fs');
  const setFsLabel=()=>{const on=!!fsEl()||wrap.classList.contains('pfs'); const sm=document.body.classList.contains('embed')&&innerWidth<560; fsBtn.textContent=sm?(on?'✕':'⛶'):(on?'Exit full screen':'Full screen'); fsBtn.setAttribute('aria-label',on?'Exit full screen':'Full screen'); fsBtn.setAttribute('aria-pressed',on);};
  const toggleFs=()=>{ if(fsEl()){ (document.exitFullscreen||document.webkitExitFullscreen).call(document); return; }
    if(wrap.classList.contains('pfs')){ wrap.classList.remove('pfs'); setFsLabel(); return; }
    const rq=wrap.requestFullscreen||wrap.webkitRequestFullscreen;
    if(rq){ try{ const r=rq.call(wrap); if(r&&r.catch) r.catch(()=>{wrap.classList.add('pfs'); setFsLabel();}); }catch(_){ wrap.classList.add('pfs'); setFsLabel(); } }
    else { wrap.classList.add('pfs'); setFsLabel(); } };
  fsBtn.onclick=toggleFs; setTimeout(setFsLabel,0); addEventListener('resize',setFsLabel); document.addEventListener('fullscreenchange',setFsLabel); document.addEventListener('webkitfullscreenchange',setFsLabel);
  document.getElementById('back').onclick=()=>seek(-10); document.getElementById('fwd').onclick=()=>seek(10);
  document.querySelector('.stage').addEventListener('dblclick',toggleFs);
  document.querySelector('.stage').addEventListener('click',()=>{ playing?stop():play(); });
  document.addEventListener('keydown',e=>{ if(e.target.tagName==='INPUT'&&e.target.type!=='range') return;
    if(e.key===' '&&(e.target===document.body||e.target.classList.contains('stage'))){e.preventDefault(); playing?stop():play();}
    else if(e.key==='ArrowRight'&&e.target.type!=='range'){e.preventDefault(); seek(5);}
    else if(e.key==='ArrowLeft'&&e.target.type!=='range'){e.preventDefault(); seek(-5);}
    else if(e.key==='f'||e.key==='F'){toggleFs();}
    else if(e.key==='Escape'&&wrap.classList.contains('pfs')){wrap.classList.remove('pfs'); setFsLabel();} });
  renderAt(0);
  if(location.hash==='#capture') document.body.classList.add('capture');
  if(location.hash==='#embed') document.body.classList.add('embed');
}
/* phone geometry helpers: map image pixel (of 780x1600 capture) to stage coords */
function phonePt(cx,cy,w,ix,iy){const h=w*2.05; return [cx-w/2+ix*w/780, cy-h/2+iy*w/780];}
function offSwitch(cx,cy,w,iy){const [x,y]=phonePt(cx,cy,w,666,iy); const k=w/780; return R(x-60*k,y-36*k,120*k,72*k,'#f4f4f2',8*k)+R(x-52*k,y-32*k,104*k,64*k,'#b9b9b2',32*k)+Ci(x-20*k,y,26*k,'#fff');}
function tapSeq(cx,cy,w,ys,t,t0,step){ // returns {overlay, thumb}
  let ov='', th=''; const i=Math.floor((t-t0)/step);
  ys.forEach((y,j)=>{ if(j>=i) ov+=offSwitch(cx,cy,w,y); });
  if(i>=0&&i<ys.length){ const [x,y]=phonePt(cx,cy,w,668,ys[i]); th=thumb(x+4,y+4,((t-t0)/step)%1<.45); }
  return {ov,th};}

function chair(x){return cut('chair'+x,R(x-70,FLOOR-210,190,26,'#a5714a',8)+R(x-80,FLOOR-440,26,256,'#a5714a',8)+R(x-60,FLOOR-190,16,190,'#7d5536')+R(x+90,FLOOR-190,16,190,'#7d5536'));}

/* Extra characters and props for the Sanna and Laura films */
C.skinSa='#ecc29f'; C.hairSa='#c99a3f'; C.skinL='#b97c55'; C.hairL='#2a1d17';
function sanna(x,y,o={}){return person(x,y,Object.assign({id:'sanna',skin:C.skinSa,hair:C.hairSa,style:'bob',top:C.coral,legs:C.navy},o));}
function laura(x,y,o={}){return person(x,y,Object.assign({id:'laura',skin:C.skinL,hair:C.hairL,style:'bun',top:C.green,legs:'#3b3f5c'},o));}
/* baby bundle, held against the chest (person-local coords) */
const babyHeld=(sk='#f2c9a5')=>R(20,-450,110,90,'#f4d35e',40)+Ci(96,-462,30,sk)+P('M70 -480 q26 -30 54 0z','#7fb3d5')+Ci(106,-466,4,C.ink);
/* pushchair facing right; (x,y) = ground under it */
function pram(x,y,o={}){const s=o.s||1, roll=o.roll||0, id=o.id||'pram', tilt=o.tilt||0; let w='';
  const wheel=(cx)=>{let sp=''; for(let i=0;i<6;i++){const a=roll+i*Math.PI/3; sp+=L(cx,-40,cx+Math.cos(a)*30,-40+Math.sin(a)*30,'#6b6560',3);} return `<circle cx="${cx}" cy="-40" r="38" fill="none" stroke="${C.ink}" stroke-width="10"/>`+sp+Ci(cx,-40,8,C.ink);};
  w+=L(-80,-40,-20,-150,C.ink,8)+L(90,-40,20,-150,C.ink,8)+L(-150,-330,-40,-170,C.ink,9)+R(-176,-350,56,22,C.ink,10);
  w+=P('M-110 -250 h240 q0 110 -120 110 q-120 0 -120 -110z',C.navy)+R(-116,-262,252,26,C.navy2,12);
  if(o.baby!==false) w+=Ci(70,-262,30,o.skin||'#f2c9a5')+P('M44 -276 q26 -34 54 0z','#7fb3d5')+Ci(82,-266,4,C.ink);
  w+=P('M-112 -258 q10 -120 120 -120 v120z',C.teal2);
  w+=wheel(-80)+wheel(90);
  return cut(id,w,`translate(${x} ${y}) rotate(${tilt}) scale(${s})`);}
function laptop(x,y,s=1){return cut('lap'+x,G(`translate(${x} ${y}) scale(${s})`,R(-70,-90,140,90,'#3a3f45',8)+R(-62,-84,124,76,'#9fd0d8',4)+R(-84,-4,168,12,'#55595e',5)));}
function cot(x){let s=R(x,FLOOR-330,360,24,'#c9a27a',8)+R(x,FLOOR-140,360,24,'#c9a27a',8)+R(x+10,FLOOR-180,340,40,'#fff',10)+R(x-12,FLOOR-360,24,360,'#a5714a',6)+R(x+348,FLOOR-360,24,360,'#a5714a',6);
  for(let i=1;i<8;i++) s+=R(x+i*45-5,FLOOR-310,10,175,'#c9a27a',4);
  return cut('cot'+x,s);}
function fridgeKettle(x){return cut('fridge'+x,R(x,FLOOR-300,220,300,'#e9eef0',14)+R(x+10,FLOOR-290,200,8,'#cfd8dc')+R(x+180,FLOOR-230,12,70,'#8a9599',5)
  +R(x+40,FLOOR-380,90,80,'#2f7f7a',20)+R(x+120,FLOOR-360,30,14,'#2f7f7a',6)+R(x+70,FLOOR-396,30,18,C.ink,6));}
function iceMachine(x){return cut('ice'+x,R(x,FLOOR-380,200,380,'#b9c1c5',10)+R(x+30,FLOOR-330,140,110,'#8fa3ad',8)+Tx(x+100,FLOOR-260,40,'ICE','#fff',800));}
function nightWin(x,y,w,h){return cut('nw'+x,R(x-14,y-14,w+28,h+28,C.cream,6)+R(x,y,w,h,'#1f2d45')+Ci(x+w*.72,y+h*.3,34,'#f4e3a1')+Ci(x+w*.72+14,y+h*.3-8,30,'#1f2d45')+[0,1,2,3,4].map(i=>Ci(x+20+i*w/5,y+20+(i%2)*40,3,'#fff')).join(''));}
function highChair(x){return cut('hc'+x,L(x-60,FLOOR,x-20,FLOOR-330,'#a5714a',10)+L(x+60,FLOOR,x+20,FLOOR-330,'#a5714a',10)+R(x-70,FLOOR-360,140,30,'#e2a33b',10)+R(x-60,FLOOR-480,22,130,'#e2a33b',8)+R(x-80,FLOOR-400,170,16,'#fff',8));}
function playArea(x){return cut('play'+x,R(x,FLOOR-160,420,160,'#f6d7a7',16)+R(x+30,FLOOR-110,70,70,C.coral,8)+R(x+120,FLOOR-90,60,60,C.teal,8)+Ci(x+250,FLOOR-60,40,C.mustard)+R(x+310,FLOOR-130,70,90,'#7a5a9a',8)+Tx(x+210,FLOOR-180,30,'PLAY AREA',C.ink,800));}
function trainSide(stepsDoor){let s=R(-200,FLOOR-40,2320,400,'#9aa0a6')+R(-200,FLOOR-40,2320,20,C.mustard);
  s+=cut('car',R(-100,120,2120,FLOOR-180,'#e9eef0',30)+R(-100,FLOOR-240,2120,40,'#2c3e5c')+[0,1,2,3].map(i=>R(60+i*480,220,300,180,'#9fc3d6',18)).join('')
    +R(1180,190,240,FLOOR-250,'#cfd8dc',10)+R(1190,200,220,FLOOR-270,'#b9c1c5',8)+Tx(1300,170,32,stepsDoor?'CAR 6':'CAR 2',C.ink,800));
  if(stepsDoor) s+=cut('tsteps',R(1180,FLOOR-60,240,30,'#55595e',4)+R(1200,FLOOR-30,200,30,'#55595e',4));
  else s+=cut('tramp',P(`M1180 ${FLOOR-60} h240 l40 60 h-320z`,'#55595e')+Ci(1300,FLOOR-140,40,'#2c78c4')+P(`M1282 ${FLOOR-156} h36 v10 h-16 v24 h-10z`,'#fff'));
  return s;}
function lobbyBase(nm){return room('#efe0c4')+sign(1180,110,520,90,nm)+desk(1100,440,190)+staff(1300,FLOOR,{dir:-1,arm:'desk',id:'st1',skin:C.skinS2,style:'bun',hair:C.hairA});}
function capTag(id,x,y,w,txt,rot=0,size=32){return cut(id,R(x-w/2,y-46,w,72,C.cream,12)+Tx(x,y,size,txt,C.ink,800),rot?`rotate(${rot} ${x} ${y})`:'');}
function rewindTo(T){const sc=SCENES.find(s=>T>=s.from&&T<s.to); window.__noLabel=true; const out=sc.draw(T-sc.from,sc.to-sc.from); window.__noLabel=false; return out;}
function fmtN(n){return n.toLocaleString('en-GB');}
function station(lt){ let s=room('#dfe3e6','#9aa0a6');
  s+=sign(700,90,520,100,'TAMPERE','railway station',C.navy)+cut('board',R(1450,200,440,260,'#1d1f22',8)+['IC 47  HELSINKI  08:05  4','R  RIIHIMÄKI  08:12  2','IC 26  OULU  08:20  1','H  JYVÄSKYLÄ  08:31  3'].map((r,i)=>Tx(1466,250+i*56,26,r,'#f4c542',700,'start',`font-family="ui-monospace,monospace"`)).join(''));
  return s; }
function trainInside(){ let s=R(-200,-200,2320,1500,'#e7e1d6')+R(-200,FLOOR,2320,400,'#6b6f73');
  for(let i=0;i<4;i++) s+=cut('tw'+i,R(80+i*470,200,380,240,'#9fc3d6',20)+R(80+i*470,380,380,60,'#c6dbe4',0));
  return s; }
function seat(x){return cut('seat'+x,R(x-35,FLOOR-420,70,420,C.teal2,14)+R(x-35,FLOOR-210,260,40,C.teal,10)+R(x+65,FLOOR-170,24,170,'#4a4e52'));}
function bistroBase(nm,sub){ return room('#f3dcc6','#b58a62')+sign(640,100,640,110,nm,sub,C.coral); }
function phoneScene(bg,img,t,o={}){let s=R(-10,-10,1940,1100,bg)+bigPhone(o.cx||960,500,img,{w:340,overlay:o.ov||''})+(o.th||''); return s;}
/* phone where each tap swaps to a real capture with one more switch on */
function stepPhone(cx,cy,w,pre,ys,t,t0,step){ const u=(t-t0)/step; const i=Math.floor(u), fr=u-i;
  const k=Math.max(0,Math.min(ys.length,u<0?0:i+(fr>=0.3?1:0)));
  let s=bigPhone(cx,cy,pre+'_s'+k,{w});
  if(i>=0&&i<ys.length){ const [x,y]=phonePt(cx,cy,w,668,ys[i]); s+=thumb(x+4,y+4,fr<.45); }
  return s; }

/* ---- bus and ferry sets ---- */
function busStation(){ let s=room('#e4e2dc','#9aa0a6')+sign(660,90,600,100,'TAMPERE','bus station',C.navy);
  s+=cut('bboard',R(1440,200,460,230,'#1d1f22',8)+['07:30  TURKU      12','07:45  HELSINKI    4','08:00  PORI        9'].map((r,i)=>Tx(1456,260+i*60,28,r,'#f4c542',700,'start',`font-family="ui-monospace,monospace"`)).join(''));
  s+=cut('coach',R(-120,FLOOR-430,1000,400,'#e9eef0',36)+R(-120,FLOOR-140,1000,40,C.teal)+[0,1,2].map(i=>R(-60+i*300,FLOOR-390,250,150,'#9fc3d6',14)).join('')+R(800,FLOOR-400,60,300,'#cfd8dc',8)+Ci(120,FLOOR-30,52,C.ink)+Ci(680,FLOOR-30,52,C.ink)+Tx(380,FLOOR-170,40,'VÄYLÄ BUS','#fff',800));
  return s; }
function busInside(){ let s=R(-200,-200,2320,1500,'#e3e1da')+R(-200,FLOOR,2320,400,'#5f6368');
  for(let i=0;i<4;i++) s+=cut('bw'+i,R(60+i*470,190,400,220,'#9fc3d6',24));
  return s; }
function busSeat(x){return cut('bseat'+x,R(x-35,FLOOR-430,74,430,C.navy,16)+R(x-35,FLOOR-210,250,40,C.navy2,10)+R(x+80,FLOOR-170,24,170,'#4a4e52'));}
function socket(x,y){return cut('sock'+x,R(x,y,60,60,'#fff',8)+Ci(x+20,y+30,6,C.ink)+Ci(x+40,y+30,6,C.ink));}
function toiletDoor(x){return cut('wc'+x,R(x,FLOOR-480,220,480,'#b9c1c5',8)+R(x+70,FLOOR-430,80,50,'#fff',6)+Tx(x+110,FLOOR-394,30,'WC',C.ink,800));}
function ferrySide(lift){ let s=R(-200,-200,2320,1500,'#cfe3ee')+R(-200,FLOOR-40,2320,420,'#7f9fb0');
  s+=cut('hull',R(-100,140,2120,FLOOR-160,'#ffffff',30)+R(-100,FLOOR-170,2120,60,C.navy)+[0,1,2,3,4,5].map(i=>Ci(120+i*300,260,40,'#9fc3d6')).join('')+Tx(520,420,56,'AALTO LINE',C.navy,800));
  if(lift) s+=cut('liftd',R(1220,FLOOR-430,240,410,'#9aa3a8',8)+R(1230,FLOOR-420,105,400,'#b9c1c5')+R(1345,FLOOR-420,105,400,'#b9c1c5')+R(1260,FLOOR-490,160,46,C.green,8)+Tx(1340,FLOOR-457,28,'LIFT','#fff',800));
  else { let st=''; for(let i=0;i<7;i++) st+=R(1220+i*60,FLOOR-60-i*60,300-i*0,60,i%2?'#8a9599':'#9aa3a8'); s+=cut('stairs',st+L(1200,FLOOR-80,1640,FLOOR-480,C.ink,8)); }
  return s; }
function ferryLounge(){ let s=R(-200,-200,2320,1500,'#efe7da')+R(-200,FLOOR,2320,400,'#6f7a80');
  for(let i=0;i<5;i++) s+=cut('ph'+i,Ci(180+i*400,280,90,C.cream)+Ci(180+i*400,280,74,'#9fc3d6')+R(110+i*400,300,140,50,'#7f9fb0'));
  return s; }
function terminalDesk(){ return room('#e6e2da','#9aa0a6')+sign(660,90,600,100,'HELSINKI','West Harbour terminal',C.navy)+desk(1200,520,200,C.navy)+staff(1500,FLOOR,{dir:-1,arm:'desk',id:'tdesk',skin:C.skinS2,style:'bun',hair:C.hairA,face:'flat'}); }
function shareScene(px,bg,bistroWord,t){ let s=R(-10,-10,1940,1100,bg); const img=t<4?px+'_see_hotel':t<6.6?px+'_share':t<9?px+'_share_stopped1':px+'_share_stopped';
  s+=bigPhone(960,500,img,{w:340})+ripple(1240,300,t);
  if(t<4&&t>1) s+=cut('lb',R(1300,560,460,90,C.cream,12)+Tx(1530,618,32,'what the hotel sees',C.ink,800));
  if(t>=4&&t<9.2){const [x,y]=phonePt(960,500,340,420,1216); s+=thumb(x,y,(t>6&&t<6.6)||(t>8.4&&t<9));}
  if(t>6.7) s+=cut('ok1',R(1300,380,440,84,C.cream,12)+Tx(1520,435,32,'hotel: access ended',C.ink,800));
  if(t>9.1) s+=cut('ok2',R(1300,490,440,84,C.cream,12)+Tx(1520,545,32,bistroWord+': access ended',C.ink,800));
  return s+labelTag('With the vault',true);}
/* v2: she sends it herself (10 s). pre = capture before the tap, tap = [ix,iy] in capture pixels */
function sendScene(px,bg,pre,tap,lines,tag,t){ const cx=560,cy=520,w=340, tapT=4.2, up=t>=tapT+0.4;
  let s=R(-10,-10,1940,1100,bg)+bigPhone(cx,cy,up?px+'_x_sent':px+'_'+pre,{w});
  if(t>=tapT-1&&t<tapT+1){ const [x,y]=phonePt(cx,cy,w,tap[0],tap[1]); s+=thumb(x+4,y+4,t>=tapT&&t<tapT+0.4); }
  if(!up){ s+=ripple(1240,300,t)+cut('ln',R(1000,380,760,60+lines.length*56,C.cream,16)+lines.map((l,i)=>Tx(1380,440+i*56,36,esc(l),C.ink,700)).join('')); }
  else { const k=Math.min(1,(t-tapT-0.4)/0.6); s+=G(`translate(0 ${Math.round((1-k)*40)})`,tablet(980,250,760,px+'_x_staff',1))+(t>tapT+1.6?capTag('sent',1360,190,640,tag,-1,34):''); }
  return s+labelTag('With the vault',true); }
/* v2: Helmi reads the screen aloud. h0,h1 = scene-relative seconds of Helmi's voice */
function wrapTxt(s,n){ const w=s.split(' '), L=[]; let c=''; w.forEach(x=>{ if((c+' '+x).trim().length>n){ L.push(c.trim()); c=x; } else c+=' '+x; }); if(c.trim()) L.push(c.trim()); return L; }
function speakerIcon(x,y,s,col){ return P(`M${x} ${y-8*s} h${10*s} l${12*s} ${-10*s} v${36*s} l${-12*s} ${-10*s} h${-10*s}z`,col)+P(`M${x+28*s} ${y-6*s} q${8*s} ${10*s} 0 ${20*s} M${x+34*s} ${y-14*s} q${16*s} ${18*s} 0 ${36*s}`,'none',`stroke="${col}" stroke-width="${4*s}" stroke-linecap="round"`); }
function helmiRead(t,h0,h1,text,cx=960,cy=500,w=340){ if(t<h0-0.6) return '';
  const [bx,by]=phonePt(cx,cy,w,524,62); let s=cut('rdon',Ci(bx,by,22,C.mustard)+speakerIcon(bx-14,by-2,0.75,C.ink));
  if(t>=h0&&t<h1+1.5){ for(let i=0;i<3;i++){ const u=((t*0.7+i/3)%1); s+=`<circle cx="${cx}" cy="${cy-w*1.02-10}" r="${20+u*70}" fill="none" stroke="${C.mustard}" stroke-width="${5*(1-u)+1}" opacity="${(1-u).toFixed(2)}"/>`; } }
  const L=wrapTxt(text,30), words=text.split(' ').length, k=clamp((t-h0)/(h1-h0)); let shown=Math.ceil(k*words), acc=0;
  let card=R(1220,170,620,96+L.length*52,C.cream,16)+speakerIcon(1258,214,1,C.ink)+Tx(1310,226,30,'Helmi is reading aloud',C.ink,800,'start');
  L.forEach((ln,i)=>{ const n=ln.split(' ').length; const vis=Math.max(0,Math.min(n,shown-acc)); acc+=n; const a=ln.split(' ').slice(0,vis).join(' '), b=ln.split(' ').slice(vis).join(' ');
    card+=`<text x="1250" y="${290+i*52}" font-size="34" font-weight="700" text-anchor="start" font-family="Archivo, 'Helvetica Neue', Arial, sans-serif"><tspan fill="${C.ink}">${esc(a)}</tspan><tspan fill="#b7ad9c">${b?(a?' ':'')+esc(b):''}</tspan></text>`; });
  return s+cut('rdcard',card); }

/* ---------- trip replay: scenes (runs inside the film-engine scope) ---------- */
function tfChar0(per,x,face,t,moving){ const walk=moving?t*9:0, roll=moving?t*4:0;
  if(per==='aino') return aino(x,FLOOR,{face,roll});
  if(per==='elina') return kide(x+170,FLOOR,{walk})+elina(x,FLOOR,{face,walk});
  if(per==='laura') return pram(x+170,FLOOR,{roll})+laura(x,FLOOR,{face,walk});
  if(per==='juho') return person(x,FLOOR,{id:'juho',skin:'#efc8a8',hair:'#6b4a2b',style:'short',top:'#3d6fb0',legs:C.ink,face,walk});
  if(per==='ahmed') return person(x,FLOOR,{id:'ahmed',skin:'#6b4428',hair:'#1b1512',style:'short',top:'#2f7a5a',legs:'#3b3f5c',face,walk})+`<g transform="translate(${x} ${FLOOR})"><path d="M-30 -500 q34 58 72 0 q-6 34 -36 40 q-30 -6 -36 -40z" fill="#1b1512"/><rect x="40" y="-420" width="16" height="22" rx="5" fill="#d9e2ea"/></g>`;
  if(per==='pekka') return rollator(x+125,FLOOR,roll)+person(x,FLOOR,{id:'pekka',skin:'#f1cdb0',hair:'#d8d8d8',style:'short',top:'#8a5a3c',legs:'#4a4a4a',face,walk:walk*.5,arm:'hold'})+`<g transform="translate(${x} ${FLOOR})"><circle cx="-38" cy="-520" r="9" fill="#c9b18a"/></g>`;
  if(per==='ravi') return person(x,FLOOR,{id:'ravi',skin:'#9a6544',hair:'#16120f',style:'short',top:'#6a4c93',legs:C.navy,face,walk})+`<g transform="translate(${x} ${FLOOR})"><path d="M-46 -530 q50 -80 100 0" fill="none" stroke="#222" stroke-width="12" stroke-linecap="round"/><rect x="-58" y="-548" width="22" height="40" rx="8" fill="#222"/><rect x="42" y="-548" width="22" height="40" rx="8" fill="#222"/></g>`;
  return sanna(x,FLOOR,{face,walk}); }
function rollator(x,y,roll){ const wh=(cx)=>`<circle cx="${cx}" cy="${y-26}" r="26" fill="none" stroke="${C.ink}" stroke-width="9"/>`; return `<g>${wh(x-60)}${wh(x+60)}<path d="M${x-60} ${y-26} L${x-40} ${y-300} M${x+60} ${y-26} L${x+40} ${y-300} M${x-50} ${y-170} L${x+50} ${y-170}" stroke="#b33a3a" stroke-width="12" stroke-linecap="round" fill="none"/><rect x="${x-70}" y="${y-312}" width="140" height="22" rx="10" fill="${C.ink}"/></g>`; }
function tfSky(){ return R(-200,-200,2320,FLOOR+200,'#bcd6e3')+R(-200,FLOOR,2320,400,'#8d8f8c')+R(-200,FLOOR-14,2320,18,'#a7a9a5'); }
function tfHouses(){ let s=''; const cols=['#e9c46a','#e76f51','#8ab17d','#f4a261','#b5c99a','#d4a5a5']; for(let i=0;i<7;i++){ const x=-60+i*290, h=380+((i*97)%160); s+=R(x,FLOOR-h,260,h,cols[i%cols.length],4)+R(x+40,FLOOR-h+60,60,80,'#fff8ec',4)+R(x+150,FLOOR-h+60,60,80,'#fff8ec',4)+P(`M${x-10} ${FLOOR-h} l140 -90 l140 90z`,'#7a4a35'); } return s; }
function tfCar(x){ return cut('car',R(x,FLOOR-170,420,120,'#f2c94c',30)+R(x+70,FLOOR-250,260,100,'#f2c94c',30)+R(x+95,FLOOR-235,95,70,'#cfe3ee',8)+R(x+210,FLOOR-235,95,70,'#cfe3ee',8)+Ci(x+95,FLOOR-45,45,C.ink)+Ci(x+330,FLOOR-45,45,C.ink)+R(x+170,FLOOR-290,80,34,C.ink,6)+Tx(x+210,FLOOR-264,24,'TAXI','#f2c94c',800)); }
function tfFrames(){ let s=''; [[260,210],[620,250],[1500,230]].forEach(([x,y],i)=>{ s+=cut('fr'+i,R(x,y,260,200,'#a5714a',6)+R(x+16,y+16,228,168,['#7fb3d5','#e9c46a','#8ab17d'][i])+Ci(x+130,y+100,40,'#fff8ec','opacity=".7"')); }); return s; }
function tfBg0(st){ const per=st.per, n=st.name;
  try{
  switch(st.id){
    case 'rail': if(per==='elina') return station(0); if(per==='sanna') return busStation(); if(per==='laura') return terminalDesk();
      if(per==='ahmed'||per==='pekka') return station(0);
      if(per==='juho'||per==='ravi') return room('#dfe7ec','#9aa0a6')+sign(640,90,640,100,per==='juho'?'OULU AIRPORT':'TAMPERE-PIRKKALA','airport',C.navy)+desk(1150,440,190)+staff(1350,FLOOR,{dir:-1});
      return room('#dfe7ec','#9aa0a6')+sign(640,90,640,100,'TAMPERE-PIRKKALA','airport',C.navy)+desk(1150,440,190)+staff(1350,FLOOR,{dir:-1});
    case 'hotel': return lobbyBase(n);
    case 'bistro': return bistroBase(n,'restaurant')+table(1350)+chair(1180);
    case 'venue': return room('#3a2f4a','#5c3b2a')+R(1000,120,900,520,'#7a1f2b',10)+R(1000,600,900,40,'#4a1520')+sign(260,110,620,100,n,'tonight',C.mustard,C.ink);
    case 'ins': return room('#eef0f2','#9aa0a6')+sign(640,90,640,100,n,'travel insurance',C.navy)+desk(1150,440,190)+staff(1350,FLOOR,{dir:-1});
    case 'taxi': return tfSky()+tfHouses()+tfCar(1150);
    case 'tour': return tfSky()+tfHouses()+sign(1250,140,560,90,n,'guided walk',C.teal);
    case 'pharmacy': return room('#e3f1e8','#9aa0a6')+sign(640,90,640,100,n,'pharmacy',C.green)+desk(1150,440,190)+staff(1350,FLOOR,{dir:-1});
    case 'spa': return room('#dcefee','#b9c9c7')+sign(640,90,640,100,n,'spa',C.teal)+plant(300)+plant(1750)+staff(1450,FLOOR,{dir:-1,top:C.teal});
    case 'work': return room('#e9e4f0')+sign(640,90,640,100,n,'conference',C.navy)+table(1350)+laptop(1350,FLOOR-190,1)+chair(1520);
    case 'grocery': return room('#efe0c4')+sign(640,90,640,100,n,'delivery',C.green)+door(1300,'')+cut('bag',R(1150,FLOOR-160,140,160,'#d9b38c',10)+R(1170,FLOOR-200,30,60,C.green,6)+Ci(1250,FLOOR-180,26,C.coral));
    case 'museum': return room('#f4efe6')+tfFrames()+sign(980,560,520,80,n,'',C.ink);
    case 'babysit': return room('#f6e7f0')+sign(640,90,640,100,n,'babysitting',C.coral)+cot(1200);
    case 'planner': return room('#e6eef6')+sign(640,90,640,100,n,'travel planner app',C.navy)+table(1350)+laptop(1350,FLOOR-190,1)+plant(1700);
    case 'school': return room('#f3eadb')+sign(640,90,640,100,n,'school visit',C.green)+table(1350)+chair(1520);
    case 'unreach': return room('#3a2f4a','#5c3b2a')+R(1000,120,900,520,'#7a1f2b',10)+R(1000,600,900,40,'#4a1520')+sign(260,110,620,100,'PHONE ON SILENT','',C.mustard,C.ink);
    case 'cowork': return room('#e7ece8')+sign(640,90,640,100,n,'coworking',C.ink)+table(1350)+laptop(1350,FLOOR-190,1)+plant(1700);
  } }catch(e){}
  return room()+sign(640,90,640,100,n,'',C.navy); }
function tfBand(col,icon,title,text,u){ const lines=wrapTxt(String(text),78).slice(0,3); const h=78+lines.length*44, y=1064-h;
  return G(`translate(40 ${(y+(1-u)*40).toFixed(1)})`,R(0,0,1840,h,C.cream,22,'filter="url(#sh)"')+R(0,0,16,h,col,8)+(icon?Ci(66,46,27,col)+Tx(66,58,32,icon,'#fff',900):'')+Tx(icon?110:48,58,38,esc(title),C.ink,800,'start')+lines.map((l,k)=>Tx(48,104+k*44,32,esc(l),C.ink,500,'start')).join(''),`opacity="${u.toFixed(3)}"`); }
function tfPanel(st,t){ if(t<1.3) return ''; const u=ease(prog(t,1.3,1.8)), col=st.ok==null?C.mustard:st.ok?C.green:C.red;
  return tfBand(col,st.ok==null?'–':st.ok?'✓':'✗',st.title,st.text,u); }
function tfTop0(st){ return G('translate(40 18)',R(0,0,560,84,'rgba(255,248,236,.94)',18,'filter="url(#sh)"')+Tx(28,36,26,esc(st.when.toUpperCase()),C.coral,800,'start')+Tx(28,70,30,esc(st.name),C.ink,800,'start'))+
  G('translate(1440 18)',R(0,0,440,66,'rgba(42,36,32,.88)',16)+Tx(70,42,32,String(st.e),'#fff',800)+Tx(105,42,18,'times explaining','#e8dccb',600,'start')+Tx(285,42,32,String(st.m),'#fff',800)+Tx(320,42,18,'min lost','#e8dccb',600,'start')); }
function tfStop(st){ return (t,d)=>{ const x=lerp(-260,560,ease(prog(t,0,1.2))); const moving=t<1.2; const face=st.ok==null?'smile':st.ok?'smile':'sad';
  return tfBg(st)+tfChar(st.per,x,t<1.2?'smile':face,t,moving)+tfTop(st)+tfPanel(st,t); }; }
function tfBreach(st){ return (t,d)=>{ const flash=(Math.sin(t*9)+1)/2; let s=room('#1f2d45','#141c2b')+R(-200,-200,2320,1500,C.red,0,`opacity="${(0.18*flash).toFixed(3)}"`);
  for(let i=0;i<3;i++) s+=cut('rack'+i,R(260+i*260,260,200,560,'#2c3e5c',10)+[0,1,2,3,4,5].map(j=>R(285+i*260,290+j*85,150,50,'#1a2333',6)+Ci(415+i*260,315+j*85,8,j%2?'#e63946':'#3f8f5a')).join(''));
  if(t>0.6) s+=tfBand(C.red,'!','Break-in at '+st.name,st.text,ease(prog(t,0.6,1.1)));
  return s; }; }
function tfAccident(st){ return (t,d)=>{ let s=room('#3a2f4a','#5c3b2a')+steps(-100,4,700,60); const x=lerp(380,520,ease(prog(t,0,0.8)));
  s+=G(t>0.8&&t<1.4?`rotate(${Math.sin(t*30)*3} ${x} ${FLOOR})`:'',tfChar(st.per,x,t>0.8?'sad':'smile',t,false));
  if(t>1.4) s+=tfBand(st.ok?C.green:C.red,st.ok?'✓':'✗',st.title,st.text,ease(prog(t,1.4,1.9)));
  return s; }; }
function tfOutro(st){ return (t,d)=>{ let s=R(-200,-200,2320,1480,C.teal); s+=Tx(960,250,72,'YOUR TRIP','#fff',900);
  st.rows.forEach(([n,l],i)=>{ const u=ease(prog(t,0.4+i*0.35,1+i*0.35)); s+=G(`translate(${300+i*460} 380)`,R(0,0,400,300,C.cream,24,'filter="url(#sh)"')+Tx(200,150,96,esc(String(n)),C.ink,900)+Tx(200,220,30,esc(l),C.ink,600),`opacity="${u}"`); });
  s+=Tx(960,820,40,esc(st.sub),'#fff',600,'middle',`opacity="${ease(prog(t,1.6,2.2))}"`); return s; }; }
function tfBuild(data){ let at=0; const scenes=[], caps=[];
  const arr=x=>Array.isArray(x)?x.filter(Boolean):(x?[x]:[]);
  const add=(dur,draw,say)=>{ const L=arr(say); scenes.push({from:at,to:at+dur,draw,say:L}); if(L.length) caps.push({from:at+0.2,to:at+dur-0.1,text:L.join(' '),parts:L}); at+=dur; };
  const one=s=>{ const v=false; return v?v[1]+0.35:String(s||'').split(' ').length*0.42+0.9; };
  const dur=(base,say)=>{ const L=arr(say); if(!L.length) return base; return Math.max(base-0.8,L.reduce((a,s)=>a+one(s),0)+0.6); };
  add(dur(3.4,data.intro),(t)=>titleCard(['YOUR TRIP'],t,C.teal,'#fff',data.sub),data.intro);
  data.stops.forEach(st=>{ if(st.kind==='breach') add(dur(4.2,st.say),tfBreach(st),st.say); else if(st.kind==='accident') add(dur(5,st.say),tfAccident(st),st.say); else add(dur(4.0,st.say),tfStop(st),st.say); });
  add(dur(5,data.outro.say),tfOutro(data.outro),data.outro.say);
  return {scenes,caps,duration:at}; }


/* ---------- live version: counters show what was shared and kept; a family for the Okafors ---------- */
function tfKid(x,o){ return G(`translate(${x} ${FLOOR}) scale(.6) translate(${-x} ${-FLOOR})`,person(x,FLOOR,o)); }
function tfChar(per,x,face,t,moving){ const walk=moving?t*9:0;
  if(per==='okafor') return person(x,FLOOR,{id:'chidi',skin:'#5a3a24',hair:'#141010',style:'short',top:'#2f6fb3',legs:C.ink,face,walk})
    +person(x+190,FLOOR,{id:'ada',skin:'#6b4428',hair:'#141010',style:'long',top:'#c0503a',legs:'#3b3f5c',face,walk})
    +tfKid(x+330,{id:'amara',skin:'#6b4428',hair:'#141010',style:'long',top:'#e9c46a',legs:'#3b3f5c',face,walk})
    +tfKid(x+430,{id:'tobi',skin:'#5a3a24',hair:'#141010',style:'short',top:'#3f8f5a',legs:C.ink,face,walk});
  return tfChar0(per,x,face,t,moving); }
function tfBg(st){ return tfBg0(st.per==='okafor'?Object.assign({},st,{per:'elina'}):st); }
function tfTop(st){ return G('translate(40 18)',R(0,0,620,84,'rgba(255,248,236,.94)',18,'filter="url(#sh)"')+Tx(28,36,26,esc(st.when.toUpperCase()),C.coral,800,'start')+Tx(28,70,30,esc(st.name),C.ink,800,'start'))+
  G('translate(1440 18)',R(0,0,440,66,'rgba(42,36,32,.88)',16)+Tx(70,42,32,String(st.e),'#fff',800)+Tx(105,42,18,'details shared','#e8dccb',600,'start')+Tx(285,42,32,String(st.m),'#fff',800)+Tx(320,42,18,'kept','#e8dccb',600,'start')); }

/* ---------- trip replay: player ---------- */
let tfF=null, tfPlaying=false, tfT=0, tfT0=0, tfS=0, tfRaf=null, tfVoice=true, tfLast=-1;
let tfAu=null;
let tfQ=[];
let tfBusy=false, tfHoldStart=0, tfCapNow='', tfCapScene=-1, tfSaidAt=0, tfDoneAt=0, tfDoneScene=-1;
function tfSpeak(txt){ tfBusy=true;  if(Array.isArray(txt)){ tfQ=txt.slice(1); tfSpeak1(txt[0]); return; } tfQ=[]; tfSpeak1(txt); }
function tfNextQ(){ const quick=performance.now()-tfSaidAt<300; if(tfPlaying&&tfQ.length){ const n=tfQ.shift(); setTimeout(()=>{ if(tfPlaying) tfSpeak1(n); },60); } else { tfBusy=false; tfDoneAt=quick?0:performance.now(); tfDoneScene=tfLast; } }
function tfSpeak1(txt){ if(!tfVoice||!txt){ tfBusy=false; return; } tfCapNow=txt; tfCapScene=tfLast; tfSaidAt=performance.now(); const v=false; if(v){ try{ if(!tfAu){ tfAu=new Audio(); tfAu.onended=tfNextQ; } tfAu.pause(); tfAu.src='data:audio/mpeg;base64,'+v[0]; tfAu.currentTime=0; tfAu.play().catch(()=>{}); }catch(e){} return; }
  try{ if(!window.speechSynthesis){ tfBusy=false; return; } speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(txt); u.lang='en-GB'; u.rate=1.05; const v=speechSynthesis.getVoices().find(v=>/^en(-|_)GB/i.test(v.lang))||speechSynthesis.getVoices().find(v=>/^en/i.test(v.lang)); if(v) u.voice=v; u.onend=tfNextQ; u.onerror=()=>{ tfSaidAt=performance.now(); tfNextQ(); }; speechSynthesis.speak(u); }catch(e){} }
function tfRender(t){ tfT=t; const i=Math.max(0,tfF.scenes.findIndex(s=>t>=s.from&&t<s.to)), sc=tfF.scenes[i<0?tfF.scenes.length-1:i];
  const lt=t-sc.from, wipe=lt<0.4?R(-10,-10,1940,1100,C.paper,0,`opacity="${(1-ease(lt/0.4)).toFixed(3)}"`):'';
  document.getElementById('tf-world').innerHTML=sc.draw(lt,sc.to-sc.from)+wipe;
  const cap=tfF.caps.find(c=>t>=c.from&&t<c.to); let ct=''; if(cap){ if(tfVoice&&tfPlaying&&tfCapScene===i&&tfCapNow) ct=tfCapNow; else { const P=cap.parts||[cap.text], W=P.map(x=>x.split(' ').length), tot=W.reduce((a,b)=>a+b,0); let f=(t-cap.from)/(cap.to-cap.from)*tot, j=0; while(j<P.length-1&&f>W[j]){ f-=W[j]; j++; } ct=P[j]; } } document.getElementById('tf-cap').textContent=ct;
  if(i!==tfLast){ tfLast=i; if(tfPlaying&&sc.say) tfSpeak(sc.say); }
  const pr=document.getElementById('tf-prog'); if(pr) pr.value=t; }
function tfLoop(){ if(!tfPlaying) return; let t=tfS+(performance.now()-tfT0)/1000;
  { const sc=tfF.scenes[tfLast]; if(tfVoice&&!tfBusy&&tfDoneAt&&tfDoneScene===tfLast&&sc&&tfLast<tfF.scenes.length-1&&performance.now()-tfDoneAt>700&&t>sc.from+2.6&&t<sc.to){ t=sc.to; tfS=t; tfT0=performance.now(); tfDoneAt=0; } if(tfVoice&&tfBusy&&sc&&t>=sc.to-0.15){ if(!tfHoldStart) tfHoldStart=performance.now(); if(performance.now()-tfHoldStart<40000){ t=sc.to-0.15; tfS=t; tfT0=performance.now(); } } else tfHoldStart=0; } if(t>=tfF.duration){ t=tfF.duration-0.01; tfRender(t); tfPause(); return; } tfRender(Math.floor(t*24)/24); tfRaf=requestAnimationFrame(tfLoop); }
function tfPlay(){ if(tfPlaying) return; if(tfT>=tfF.duration-0.05){ tfT=0; } tfPlaying=true; tfS=tfT; tfT0=performance.now(); tfLast=-1; tfDoneAt=0; tfCapNow=''; document.getElementById('tf-pp').textContent='Pause'; tfLoop(); }
function tfPause(){ tfPlaying=false; tfQ=[]; cancelAnimationFrame(tfRaf); try{ speechSynthesis.cancel(); }catch(e){} try{ if(tfAu) tfAu.pause(); }catch(e){} const b=document.getElementById('tf-pp'); if(b) b.textContent='Play'; }
function tfOpen(data){ tfF=tfBuild(data); {  } let el=document.getElementById('tfilm'); if(!el){ el=document.createElement('div'); el.id='tfilm'; el.setAttribute('role','dialog'); el.setAttribute('aria-label','Your trip, replayed'); document.body.appendChild(el); }
  el.innerHTML=`<div class="tf-box"><div class="tf-stage"><svg viewBox="0 0 1920 1080" aria-hidden="true"><defs><filter id="sh" x="-10%" y="-10%" width="130%" height="130%"><feDropShadow dx="5" dy="7" stdDeviation="3" flood-color="#3b2a1a" flood-opacity=".28"/></filter></defs><g id="tf-world"></g></svg></div>
   <p class="tf-cap" id="tf-cap" aria-live="polite"></p><input type="range" id="tf-prog" min="0" max="${tfF.duration.toFixed(2)}" step="0.05" value="0" aria-label="Position in the replay">
   <div class="tf-ctl"><button id="tf-pp">Pause</button><button id="tf-re">Restart</button><button id="tf-snd" aria-pressed="true">Voice on</button><button id="tf-fs" aria-label="Full screen">⛶ Full screen</button><button id="tf-x">Close</button></div><p class="tf-tip">Tap Full screen, or turn your phone sideways, for a bigger picture.</p></div>`;
  el.hidden=false; document.body.classList.add('tf-on');
  document.getElementById('tf-pp').onclick=()=>tfPlaying?tfPause():tfPlay();
  document.getElementById('tf-re').onclick=()=>{ tfPause(); tfRender(0); tfPlay(); };
  document.getElementById('tf-snd').onclick=e=>{ tfVoice=!tfVoice; e.target.textContent=tfVoice?'Voice on':'Voice off'; e.target.setAttribute('aria-pressed',tfVoice); if(!tfVoice){ try{ speechSynthesis.cancel(); }catch(_){} try{ if(tfAu) tfAu.pause(); }catch(_){} } };
  const fsEl=()=>document.fullscreenElement||document.webkitFullscreenElement;
  const fsBtn=document.getElementById('tf-fs'); if(!(el.requestFullscreen||el.webkitRequestFullscreen)) fsBtn.hidden=true;
  fsBtn.onclick=()=>{ if(fsEl()){ (document.exitFullscreen||document.webkitExitFullscreen).call(document); return; } const r=(el.requestFullscreen||el.webkitRequestFullscreen).call(el); const lock=()=>{ try{ screen.orientation&&screen.orientation.lock&&screen.orientation.lock('landscape').catch(()=>{}); }catch(e){} }; if(r&&r.then) r.then(lock).catch(()=>{}); else lock(); };
  document.addEventListener('fullscreenchange',()=>{ fsBtn.textContent=fsEl()?'Exit full screen':'⛶ Full screen'; if(!fsEl()){ try{ screen.orientation.unlock(); }catch(e){} } });
  document.getElementById('tf-x').onclick=()=>{ tfPause(); if(fsEl()) try{ (document.exitFullscreen||document.webkitExitFullscreen).call(document); }catch(e){} el.hidden=true; document.body.classList.remove('tf-on'); };
  document.getElementById('tf-prog').oninput=e=>{ const w=tfPlaying; tfPause(); tfRender(+e.target.value); if(w) tfPlay(); };
  try{ speechSynthesis.cancel(); }catch(e){} tfT=0; tfRender(0); tfPlay(); }

let LiveFilm_last=null;
function tfLead(ty,name,when,nm,pl){ const h=(/(\d\d):\d\d/.exec(when)||[])[1], meal=h&&+h<16?'Lunch':'Dinner', be=pl?'are':'is';
  const L={'insurer':`Before the trip, ${nm} ${pl?'buy':'buys'} travel insurance from ${name}.`,'trip planner app':`Before the trip, ${nm} ${pl?'plan':'plans'} it all in ${name}.`,
   'transport':`The journey, with ${name}.`,'taxi':`A ride with ${name}.`,'hotel':`Arriving at ${name}.`,'restaurant':`${meal} at ${name}.`,
   'venue':`${/concert|music/i.test(name)?'The concert':/circus/i.test(name)?'The circus':/arena/i.test(name)?'The evening':'The show'} at ${name}.`,'work event':`The work event at ${name}.`,'course':`The course at ${name}.`,'pharmacy':`A stop at ${name}, the pharmacy.`,
   'grocery delivery':`A delivery from ${name}.`,'spa':`A visit to ${name}.`,'museum':`A visit to ${name}.`,'tour':`A walking tour with ${name}.`,
   'childcare':`An evening with ${name}.`,'school':`A visit to ${name}.`,'coworking space':`A day at ${name}.`};
  return L[ty]||`Next, ${name}.`; }
function trip(cur,results,info){
  const {PN,BN,PTY,OFF,STORY}=info; const SENT=t=>(String(t||'').match(/[^.!?]+(?:[.!?]+["”’]?|$)/g)||[]).map(x=>x.trim()).filter(Boolean); const SAY=STORY?Object.fromEntries((STORY.stops||[]).map(x=>[x.id,SENT(x.text)])):{};
  const nm=cur.short;
  const stops=[];let e=0,m=0;
  Object.entries(results).forEach(([id,r])=>{
    e+=r.shared.length;m+=r.kept.length;
    const pl=(cur.places||[]).find(x=>x.id===id)||{}, ms=pl.moments||[], g=r.shared;
    const out=ms.map(mo=>{const on=mo.dep.every(k=>g.includes(k))||(mo.alt&&[].concat(mo.alt).some(k=>g.includes(k)));
      return {mo,on,text:on?mo.b:mo.w,good:mo.trade?!(on&&mo.neg):on,trade:mo.trade}});
    const core=out.filter(x=>!x.trade), trades=out.filter(x=>x.trade&&x.on);
    const pickA=core.find(x=>!x.good)||core[0]||out[0];
    const pickB=core.find(x=>x!==pickA&&x.good!==(pickA&&pickA.good))||core.find(x=>x!==pickA)||trades[0];
    const picks=[pickA,pickB,...(trades.length&&!trades.includes(pickB)?[trades[0]]:[])].filter(Boolean).slice(0,3);
    const bad=picks.some(x=>x.trade&&!x.good), slow=picks.some(x=>!x.trade&&!x.good);
    const lines=picks.map(x=>x.text.trim());
    const lead=tfLead(pl.type||PTY[id]||'',PN[id]||pl.name||id,pl.when||'',nm,cur.plural); if(lead) lines.unshift(lead);
    stops.push({kind:'stop',id,per:cur.id,name:PN[id]||id,when:(pl.when||PTY[id]||''),ok:bad?false:slow?null:true,
      title:picks[0]?picks[0].mo.t:(PN[id]||id),text:lines.join(' '),e,m,
      say:SAY[id]&&SAY[id].length?SAY[id]:lines.length?lines:[`${nm} ${cur.plural?'are':'is'} at ${PN[id]||id}.`]});
  });
  LiveFilm_last=stops; tfOpen({intro:STORY&&STORY.intro?SENT(STORY.intro):`This is how your trip as ${nm} went.`,sub:cur.who,stops,
    outro:{rows:[[e,'details shared'],[m,'details kept'],[OFF.n?OFF.yes+' of '+OFF.n:'0','offers taken']],
      sub:`You decided what went where. Nothing went anywhere you didn’t allow.`,say:STORY&&STORY.outro?SENT(STORY.outro):'And then you were home again.'}});
}
return {open:tfOpen,trip,last:()=>LiveFilm_last};
})();
