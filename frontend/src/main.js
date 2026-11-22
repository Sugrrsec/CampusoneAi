import { LIVE_API_ENABLED, fetchChatAnswer } from './api.js';

(()=>{'use strict';
const $=id=>document.getElementById(id), entry=$('entry'),app=$('app'),input=$('message-input'),messages=$('messages'),scroll=$('scroll'),sidebar=$('sidebar'),overlay=$('overlay'),opening=$('opening');
if (LIVE_API_ENABLED) {
  document.querySelectorAll('.fineprint').forEach(el => el.textContent = 'CampusOne AI · Responses depend on indexed university sources');
  const modePill = document.querySelector('.topmeta span:last-child');
  if (modePill) modePill.textContent = '● Live API';
}
const logoMarkup=$('logo-template').innerHTML;document.querySelectorAll('[data-logo]').forEach(el=>el.insertAdjacentHTML('afterbegin',logoMarkup));document.querySelectorAll('[data-logo-only]').forEach(el=>el.innerHTML=logoMarkup);
const STORAGE='campusone-design-v3',NAME='campusone-design-v3-name';let conversations=[],activeId=null,username='Guest',replyTimer=null,toastTimer=null,transitionTimer=null,inflightController=null;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
function save(){try{localStorage.setItem(STORAGE,JSON.stringify(conversations))}catch(e){toast('Browser storage is unavailable; chats may not persist.')}}
function load(){try{const arr=JSON.parse(localStorage.getItem(STORAGE)||'[]');conversations=Array.isArray(arr)?arr.filter(c=>c&&typeof c.id==='string'&&Array.isArray(c.messages)).slice(0,100):[]}catch(e){conversations=[]}}
function uid(){return typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():'id-'+Date.now()+'-'+Math.random().toString(36).slice(2)}
function toast(s){const el=$('toast');el.textContent=s;el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),2400)}
function closeMenu(){sidebar.classList.remove('open');overlay.classList.remove('open')};$('menu').onclick=()=>{sidebar.classList.toggle('open');overlay.classList.toggle('open')};overlay.onclick=closeMenu;
function initials(s){return (s||'G').slice(0,1).toUpperCase()};function setName(n){username=n;$('profile-name').textContent=n;$('avatar').textContent=initials(n)}
function runOpeningSequence(){
  if(opening.classList.contains('on')) return;
  clearTimeout(transitionTimer);
  // Enforce a deliberate, deterministic sequence, regardless of OS motion settings.
  // 5.2s writing + 1.8s full-word hold + 1.4s cross-fade = ~8.4s.
  const writingMs=5200, holdMs=1800, fadeMs=1400, startDelay=250;
  opening.classList.remove('on','leaving');
  $('opening-caption').classList.remove('shown');
  const paths=[...opening.querySelectorAll('.hand-path')];
  paths.forEach(p=>{
    p.classList.remove('draw');
    p.style.removeProperty('--path-length');
    p.style.removeProperty('--duration');
    p.style.removeProperty('--delay');
  });
  // Start with the login beneath the translucent glass; only show chat after writing/hold.
  void opening.offsetWidth;
  opening.classList.add('on');
  const weights=[.19,.12,.15,.115,.125,.20,.12,.025];
  const sum=weights.reduce((a,b)=>a+b,0);
  let elapsed=0;
  paths.forEach((p,i)=>{
    const duration=writingMs*weights[i]/sum;
    const length=p.getTotalLength();
    p.style.setProperty('--path-length',String(length));
    p.style.setProperty('--delay',Math.round(elapsed+startDelay)+'ms');
    p.style.setProperty('--duration',Math.round(duration)+'ms');
    p.classList.add('draw');
    elapsed+=duration;
  });
  transitionTimer=setTimeout(()=>$('opening-caption').classList.add('shown'),startDelay+writingMs+200);
  setTimeout(()=>{
    openApp();
    // Avoid a sudden solid-color flash: the chat fades in behind transparent glass.
    requestAnimationFrame(()=>opening.classList.add('leaving'));
    transitionTimer=setTimeout(()=>opening.classList.remove('on','leaving'),fadeMs+60);
  },startDelay+writingMs+holdMs);
}
function openApp(){entry.classList.add('hidden');app.classList.remove('hidden');const last=conversations[0];if(last)openConversation(last.id);else newChat();input.focus()}
$('entry-form').addEventListener('submit',e=>{e.preventDefault();const n=($('name').value.trim()||'Guest').slice(0,32);setName(n);try{localStorage.setItem(NAME,n)}catch(e){}load();runOpeningSequence()});
$('signout').onclick=()=>{clearTimeout(replyTimer);inflightController?.abort();inflightController=null;app.classList.add('hidden');entry.classList.remove('hidden');closeMenu();$('name').value=username;$('name').focus()};
function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node}
function renderHistory(){const holder=$('history-list');holder.replaceChildren();const q=$('history-search').value.trim().toLowerCase();$('count').textContent=String(conversations.length);const visible=conversations.filter(c=>c.title.toLowerCase().includes(q));if(!visible.length){holder.append(el('div','history-empty',q?'No matching conversations.':'Your chats will appear here.'));return}visible.forEach(c=>{const row=el('div','history-row'+(c.id===activeId?' current':''));const open=el('button','history-open',c.title);open.title=c.title;open.onclick=()=>openConversation(c.id);const menu=el('button','history-menu','···');menu.setAttribute('aria-label','Options for '+c.title);menu.onclick=e=>{e.stopPropagation();const action=prompt('Type R to rename or D to delete this conversation:','R');if(!action)return;if(action.trim().toLowerCase()==='r'){const name=prompt('Conversation title:',c.title);if(name&&name.trim()){c.title=name.trim().slice(0,70);save();renderHistory()}}else if(action.trim().toLowerCase()==='d'){if(confirm('Delete this conversation from this browser?')){conversations=conversations.filter(x=>x.id!==c.id);save();if(activeId===c.id)newChat();else renderHistory();toast('Conversation deleted')}}};row.append(open,menu);holder.append(row)})}
function newChat(){clearTimeout(replyTimer);inflightController?.abort();inflightController=null;activeId=null;messages.replaceChildren();$('welcome').classList.remove('hidden');$('chat-heading').textContent='Campus Assistant';input.value='';resize();renderHistory();closeMenu();scroll.scrollTop=0;input.focus()}
function openConversation(id){clearTimeout(replyTimer);inflightController?.abort();inflightController=null;const c=conversations.find(x=>x.id===id);if(!c)return newChat();activeId=id;$('welcome').classList.toggle('hidden',c.messages.length>0);messages.replaceChildren();c.messages.forEach(m=>drawMessage(m,false));$('chat-heading').textContent=c.title;renderHistory();closeMenu();requestAnimationFrame(()=>scroll.scrollTop=scroll.scrollHeight)}
$('new-chat').onclick=newChat;$('assistant-nav').onclick=newChat;$('history-search').addEventListener('input',renderHistory);
function resize(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'}input.oninput=resize;input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('chat-form').requestSubmit()}});
document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>send(b.dataset.question));document.querySelectorAll('[data-topic]').forEach(b=>b.onclick=()=>{input.value=b.dataset.topic;resize();input.focus();closeMenu()});
const samples=[{terms:['cgpa','sgpa','grade'],domain:'Academics',text:'CGPA is a credit-weighted average of grade points across semesters. CampusOne’s academic-rules document includes details on the calculation and grading structure.'},{terms:['makeup','supplementary','exam'],domain:'Academics',text:'The SCSET undergraduate regulations cover makeup and supplementary examinations. Requirements vary depending on the exam and reason for absence. In the connected version, the assistant would cite the relevant policy.'},{terms:['internship'],domain:'Academics',text:'The SCSET undergraduate rules describe internship duration, approval, and evaluation requirements for different programmes.'},{terms:['wifi','wi-fi','internet','login'],domain:'IT support',text:'This question belongs to the IT domain. The current committed knowledge base does not yet include a dedicated Wi-Fi guide, so a verified answer would require additional documentation.'},{terms:['fee','payment','refund'],domain:'Fees',text:'This question belongs to the Fees domain. Dedicated fee-policy documents have not yet been added to the committed knowledge base.'},{terms:['hostel','facility','transport'],domain:'Facilities',text:'This question belongs to Facilities. The current committed dataset does not contain a dedicated facilities reference document.'}];
function statusLabel(m){
  if(m.demo!==false)return 'Illustrative reply';
  switch(m.status){
    case 'out_of_scope':return 'Out of scope query';
    case 'needs_clarification':return 'Clarification requested';
    case 'no_evidence':
    case 'no_retrieved_evidence':return 'No verified documents';
    case 'provider_rate_limited':return 'AI service temporarily busy';
    case 'error':return 'Connection error';
    default:return 'University knowledge response';
  }
}
function domainChip(m){
  if(m.status==='error')return 'Error';
  if(m.status==='provider_rate_limited')return 'Rate limit';
  if(m.status==='out_of_scope')return 'Out of scope';
  if(m.domain&&m.domain.trim()&&m.domain!=='Assistant')return m.domain;
  return 'Assistant';
}
function drawMessage(m,animate=true){if(m.role==='user'){messages.append(el('div','message user',m.text));return}const row=el('div','message bot'),mark=el('div','bot-icon');mark.innerHTML=logoMarkup;const body=el('div','answer'),name=el('div','answer-label','CampusOne'),answer=el('div','answer-body',m.text),foot=el('div','answer-detail');foot.append(el('span','chip',domainChip(m)),el('small','',statusLabel(m)));body.append(name,answer,foot);
  if (Array.isArray(m.sources) && m.sources.length) {
    const refs=el('div','answer-detail');
    m.sources.slice(0,5).forEach(ref=>{
      const title=String(ref.source_title||'University source');
      if (typeof ref.source_url === 'string' && /^https?:\/\//i.test(ref.source_url)) {
        const link=el('a','source-link',title+(ref.page!=null?' · p. '+ref.page:''));
        link.href=ref.source_url;link.target='_blank';link.rel='noopener noreferrer';refs.append(link);
      } else {refs.append(el('span','chip',title+(ref.page!=null?' · p. '+ref.page:'')));}
    });
    body.append(refs);
  }
  row.append(mark,body);messages.append(row)}
function addTyping(){const row=el('div','message bot'),mark=el('div','bot-icon');mark.innerHTML=logoMarkup;const body=el('div','answer'),label=el('div','answer-label','CampusOne'),dots=el('div','typing');dots.innerHTML='<i></i><i></i><i></i>';body.append(label,dots);row.append(mark,body);messages.append(row);return row}
async function send(q){
  const text=(q||input.value).trim();if(!text)return;
  clearTimeout(replyTimer);
  inflightController?.abort();inflightController=null;
  let c=conversations.find(x=>x.id===activeId);
  if(!c){c={id:uid(),title:text.slice(0,50)+(text.length>50?'…':''),createdAt:Date.now(),messages:[]};conversations.unshift(c);activeId=c.id}
  c.messages.push({role:'user',text});save();
  $('welcome').classList.add('hidden');drawMessage({role:'user',text});
  $('chat-heading').textContent=c.title;input.value='';resize();closeMenu();renderHistory();
  scroll.scrollTop=scroll.scrollHeight;
  const pending=addTyping();scroll.scrollTop=scroll.scrollHeight;
  const cid=c.id;
  const publish=(m)=>{
    const current=conversations.find(x=>x.id===cid);
    if(!current)return;
    current.messages.push(m);save();
    if(activeId===cid){if(pending.isConnected)pending.remove();drawMessage(m);scroll.scrollTop=scroll.scrollHeight}
  };
  if(!LIVE_API_ENABLED){
    replyTimer=setTimeout(()=>{
      const match=samples.find(x=>x.terms.some(t=>text.toLowerCase().includes(t)));
      publish({role:'assistant',text:match?.text||'This is a visual prototype. In the connected version, CampusOne will classify your question, retrieve relevant university documents, and respond based on available evidence.',domain:match?.domain||'General',demo:true});
    },reduced?50:850);
    return;
  }
  const controller=new AbortController();inflightController=controller;
  try {
    const response=await fetchChatAnswer({message:text,session_id:cid},controller.signal);
    if(controller.signal.aborted)return;
    let domain=(response.domains||[]).join(', ');
    const status=response.metadata?.status||(response.is_out_of_scope?'out_of_scope':(response.needs_clarification?'needs_clarification':'answered'));
    if(!domain){
      if(status==='out_of_scope'||response.is_out_of_scope) domain='Out of scope';
      else if(status==='provider_rate_limited') domain='Rate limit';
      else if(status==='needs_clarification') domain='Clarification';
      else domain='Assistant';
    }
    publish({role:'assistant',text:response.answer,domain,sources:response.sources||[],status,demo:false});
  } catch(err) {
    if(controller.signal.aborted)return;
    if(pending.isConnected)pending.remove();
    toast('Could not contact CampusOne API. Check the backend and CORS settings.');
    const errMsg=err instanceof Error?err.message:'Request failed';
    publish({role:'assistant',text:'Connection error: '+errMsg,domain:'Error',status:'error',demo:false,sources:[],isError:true});
  } finally {
    if(inflightController===controller)inflightController=null;
  }
}
$('chat-form').addEventListener('submit',e=>{e.preventDefault();send()});
// Revisit with the same name and browser to see locally saved conversations.
try{const previous=localStorage.getItem(NAME);if(previous)$('name').value=previous}catch(e){}
})();
