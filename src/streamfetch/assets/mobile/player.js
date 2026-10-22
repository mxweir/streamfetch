"use strict";
const $=id=>document.getElementById(id);
let items=[],filtered=[],current=null,mode="here",pc={},timer,busy=false,polling=false,audioContext;
let switching=false;
const gains=new WeakMap(),active=()=>current?.media_type==="video"?$("video"):$("audio");
const gainTracks=new WeakMap();
const duration=s=>Number.isFinite(s)?`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`:"0:00";
const message=text=>$("status").textContent=text;
const stored=(key,value)=>{try{if(value!==undefined)localStorage.setItem(key,value);return localStorage.getItem(key);}catch{return null;}};
async function api(path,body){
  const response=await fetch(path,{method:body?"POST":"GET",credentials:"same-origin",
    headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined,
    signal:AbortSignal.timeout(8000)});
  if(response.status===401||response.redirected){location.replace("/login");throw Error("Please pair again.");}
  if(!response.ok){let text="Request refused. Check permissions on your computer.";
    try{text=(await response.json()).error||text;}catch{}throw Error(text);}
  return response.json();
}
function sound(media){
  if(current?.gain_db==null&&!gains.has(media))return;
  try{
    audioContext??=new(window.AudioContext||window.webkitAudioContext)();
    audioContext.resume().catch(()=>message("Tap play on this device to enable audio."));
    if(!gains.has(media)){
      const source=audioContext.createMediaElementSource(media),gain=audioContext.createGain();
      source.connect(gain);gain.connect(audioContext.destination);gains.set(media,gain);
    }
    const db=$("normalize").checked?Number(current?.gain_db??0):0;
    const parameter=gains.get(media).gain;
    if(gainTracks.get(media)!==current.id){
      parameter.cancelScheduledValues(audioContext.currentTime);
      parameter.setValueAtTime(10**(db/20),audioContext.currentTime);gainTracks.set(media,current.id);
    }else parameter.setTargetAtTime(10**(db/20),audioContext.currentTime,0.05);
  }catch{message("Loudness matching is unavailable in this browser.");}
}
function remember(sync=false){
  if(!current)return;const position=active().ended?0:active().currentTime||0;
  stored(`sf-home-${current.id}`,String(position));current.resume=position;
  if(sync)api("/api/progress",{item:current.id,position}).catch(()=>{});
}
function play(item,position=null){
  const resume=position??Number(stored(`sf-home-${item.id}`)??item.resume??0);
  remember(true);switching=true;$("audio").pause();$("video").pause();current=item;
  $("title").textContent=item.title;$("artist").textContent=item.artist||item.album||"Local library";
  $("audio").hidden=item.media_type==="video";$("video").hidden=item.media_type!=="video";
  const media=active();sound(media);media.src=`/media/${item.id}`;media.playbackRate=Number($("speed").value);
  $("local-player").hidden=mode!=="here";
  media.onloadedmetadata=()=>{if(resume>=0&&resume<media.duration-1)media.currentTime=resume;
    switching=false;};
  $("gain-status").textContent=item.gain_db==null?"Original sound · no analysis":"Matched · −18 LUFS target";
  $("save-current").hidden=!pc.downloads_allowed;$("save-current").href=`/download/${item.id}`;
  media.play().catch(()=>message("Tap play to continue. Your browser may require a gesture or a supported format."));
  message("");render();updateConnection();
}
function next(direction=1){const i=filtered.findIndex(x=>x.id===current?.id);if(filtered[i+direction])play(filtered[i+direction]);}
function setMode(value){mode=value;$("here").setAttribute("aria-pressed",String(value==="here"));
  $("computer").setAttribute("aria-pressed",String(value==="computer"));$("remote").hidden=value!=="computer";
  $("local-player").hidden=value!=="here"||!current;if(value==="computer"){active().pause();remember(true);}render();}
function render(){
  const query=$("search").value.toLowerCase(),playlist=$("playlist").value;
  filtered=items.filter(i=>(!playlist||i.playlists.includes(playlist))&&`${i.title} ${i.artist} ${i.album}`.toLowerCase().includes(query));
  $("tracks").replaceChildren();
  filtered.forEach((item,index)=>{
    const row=document.createElement("div");row.className="track-row";
    const button=document.createElement("button");button.className="track"+((mode==="here"?current?.id:pc.item)===item.id?" active":"");
    const number=document.createElement("span");number.className="number";number.textContent=String(index+1).padStart(2,"0");
    const info=document.createElement("span");info.className="info";
    const title=document.createElement("strong");title.textContent=item.title;
    const artist=document.createElement("small");artist.textContent=item.artist||"Local library";info.append(title,artist);
    const time=document.createElement("span");time.textContent=duration(item.duration);button.append(number,info,time);
    button.onclick=()=>{if(mode==="computer")command("play",{item:item.id,position:0}).catch(e=>message(e.message));else play(item);};row.append(button);
    if(pc.downloads_allowed){const link=document.createElement("a");link.className="save-track";link.href=`/download/${item.id}`;
      link.textContent="↓";link.setAttribute("aria-label",`Save original: ${item.title}`);row.append(link);}$("tracks").append(row);
  });
  $("summary").textContent=`${filtered.length} tracks · ${mode==="here"?"Playing on this device":"Controlling computer speakers"}`;
}
function updateConnection(){
  const item=items.find(i=>i.id===pc.item);$("pc-title").textContent=item?.title||"Computer player";
  $("pc-status").textContent=!pc.remote_allowed?"Computer control is off. Enable it in StreamFetch → Home player."
    :!pc.online?"Open this library on your computer and press play once. Keep its tab open."
    :pc.blocked?"Audio blocked: press play once on the computer.":pc.paused?"Connected · paused":"Connected · playing on computer";
  $("computer").disabled=!pc.remote_allowed;
  $("takeover").disabled=busy||!pc.remote_allowed||!pc.online||!item;
  $("send-pc").disabled=busy||!pc.remote_allowed||!pc.online||!current;
  for(const id of["pc-play","pc-pause","pc-next","pc-previous","pc-seek","pc-volume"]){$(id).disabled=busy||!pc.remote_allowed||!pc.online;}
  if(document.activeElement!==$("pc-seek")){$("pc-seek").max=String(item?.duration||1);$("pc-seek").value=String(pc.position||0);}
  if(document.activeElement!==$("pc-volume"))$("pc-volume").value=String(pc.volume??1);
  $("pc-time").textContent=`${duration(pc.position)} / ${duration(item?.duration)}`;
  $("download-note").textContent=pc.downloads_allowed?"Save originals with ↓. Copies stay on your device after disconnecting; open them in your music or files app."
    :"Saving files is off. Ask the computer owner to enable original-file downloads.";
  $("save-current").hidden=!pc.downloads_allowed||!current;
  if(!pc.remote_allowed&&mode==="computer")setMode("here");
}
async function poll(){
  if(polling)return;polling=true;
  try{const previous=pc;pc=await api("/api/playback");updateConnection();
    if(previous.downloads_allowed!==pc.downloads_allowed||previous.item!==pc.item)render();
  }catch{message("Computer unreachable. Check Wi-Fi, sharing and whether it is awake. Saved files remain available locally.");}
  finally{polling=false;}
}
async function command(action,details={}){
  if(busy)throw Error("Wait for the current command to finish.");busy=true;updateConnection();
  try{const result=await api("/api/control",{action,...details});
    for(let n=0;n<12;n++){
      await new Promise(resolve=>setTimeout(resolve,750));await poll();const status=pc.results?.[result.command];
      if(status==="applied"){message("Computer updated.");return;}
      if(status==="blocked")throw Error("Press play once on the computer to allow audio. Playback has not moved.");
      if(status==="expired")break;
    }throw Error("Computer did not confirm. Keep the library tab open and try again.");
  }finally{busy=false;updateConnection();}
}
$("here").onclick=()=>setMode("here");$("computer").onclick=()=>setMode("computer");
$("takeover").onclick=async()=>{
  const item=items.find(i=>i.id===pc.item);if(!item)return;
  try{audioContext??=new(window.AudioContext||window.webkitAudioContext)();audioContext.resume().catch(()=>{});
    await command("pause");const position=pc.position||0;setMode("here");play(item,position);
  }catch(e){message(e.message);}
};
$("send-pc").onclick=async()=>{if(!current)return;
  try{await command("play",{item:current.id,position:active().currentTime||0});active().pause();remember(true);setMode("computer");}
  catch(e){message(e.message);}
};
for(const[id,action]of[["pc-play","play"],["pc-pause","pause"],["pc-next","next"],["pc-previous","previous"]]){
  $(id).onclick=()=>command(action).catch(e=>message(e.message));
}
$("pc-seek").onchange=()=>command("seek",{position:Number($("pc-seek").value)}).catch(e=>message(e.message));
$("pc-volume").onchange=()=>command("volume",{volume:Number($("pc-volume").value)}).catch(e=>message(e.message));
$("search").oninput=render;$("playlist").onchange=render;$("previous").onclick=()=>next(-1);$("next").onclick=()=>next();
$("normalize").onchange=()=>{sound(active());$("gain-status").textContent=$("normalize").checked&&current?.gain_db!=null?"Matched · −18 LUFS target":"Original sound";};
$("speed").onchange=()=>active().playbackRate=Number($("speed").value);
$("sleep").onchange=()=>{clearTimeout(timer);const minutes=Number($("sleep").value);if(minutes)timer=setTimeout(()=>{active().pause();remember(true);$("sleep").value="0";message("Sleep timer finished.");},minutes*60000);};
for(const media of[$("audio"),$("video")]){
  media.onpause=()=>{if(!switching)remember(true);};media.onended=()=>{remember(true);next();};
  media.onerror=()=>{switching=false;message("Cannot play this file. Check the computer is awake and your browser supports the format.");};
}
setInterval(()=>{if(current&&!active().paused)remember(true);},5000);window.addEventListener("pagehide",()=>remember());
api("/api/library").then(data=>{items=data;[...new Set(items.flatMap(i=>i.playlists))].sort().forEach(name=>{
  const o=document.createElement("option");o.value=name;o.textContent=name;$("playlist").append(o);});
  render();poll();setInterval(poll,2000);
}).catch(e=>message(e.message));
