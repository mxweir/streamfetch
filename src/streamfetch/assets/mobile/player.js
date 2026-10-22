"use strict";
const $ = id => document.getElementById(id);
let items = [], filtered = [], current = null, timer;
const active = () => current?.media_type === "video" ? $("video") : $("audio");
const positionKey = item => `sf-home-${item.id}`;
const remember = () => {if(current) localStorage.setItem(positionKey(current),String(active().currentTime));};
const duration = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,"0")}` : "";
function play(item) {
  remember(); $("audio").pause(); $("video").pause(); current = item;
  $("title").textContent=item.title; $("artist").textContent=item.artist || item.album || "Local library";
  $("audio").hidden=item.media_type==="video"; $("video").hidden=item.media_type!=="video";
  const media=active(); media.src=`/media/${item.id}`; media.playbackRate=Number($("speed").value);
  media.onloadedmetadata=()=>{const pos=Number(localStorage.getItem(positionKey(item)) || 0);if(pos>0 && pos<media.duration-2)media.currentTime=pos;};
  media.play().catch(()=>{$("status").textContent="Press play to start. If this format is unsupported by your browser, convert it to MP3 or MP4 in StreamFetch.";}); render();
}
function next(direction=1) {const index=filtered.findIndex(item=>item.id===current?.id);const item=filtered[index+direction];if(item)play(item);}
function render() {
  const query=$("search").value.toLowerCase(), playlist=$("playlist").value;
  filtered=items.filter(item=>(!playlist || item.playlists.includes(playlist)) && `${item.title} ${item.artist} ${item.album}`.toLowerCase().includes(query));
  $("tracks").replaceChildren();
  filtered.forEach((item,index)=>{const button=document.createElement("button");button.className="track"+(current?.id===item.id?" active":"");
    const number=document.createElement("span");number.className="number";number.textContent=String(index+1).padStart(2,"0");
    const info=document.createElement("span");info.className="info";const title=document.createElement("strong");title.textContent=item.title;const artist=document.createElement("small");artist.textContent=item.artist || "Local library";info.append(title,artist);
    const time=document.createElement("span");time.textContent=duration(item.duration);button.append(number,info,time);button.onclick=()=>play(item);$("tracks").append(button);});
  $("summary").textContent=`${filtered.length} tracks · Private home session`;
}
$("search").oninput=render;$("playlist").onchange=render;$("previous").onclick=()=>next(-1);$("next").onclick=()=>next();
$("speed").onchange=()=>active().playbackRate=Number($("speed").value);
$("sleep").onchange=()=>{clearTimeout(timer);const minutes=Number($("sleep").value);if(minutes)timer=setTimeout(()=>{active().pause();remember();$("sleep").value="0";$("status").textContent="Sleep timer finished.";},minutes*60000);};
for(const media of [$("audio"),$("video")]){media.onpause=remember;media.onended=()=>{if(current)localStorage.removeItem(positionKey(current));next();};media.onerror=()=>{$("status").textContent="Cannot play this file. Check the computer is online and your browser supports this format.";};}
setInterval(remember,5000);window.addEventListener("pagehide",remember);
fetch("/api/library").then(response=>{if(!response.ok || response.redirected){location.href="/login";throw Error("Please pair again.");}return response.json();}).then(data=>{items=data;[...new Set(items.flatMap(item=>item.playlists))].sort().forEach(name=>{const option=document.createElement("option");option.value=name;option.textContent=name;$("playlist").append(option);});render();}).catch(error=>$("status").textContent=error.message);
