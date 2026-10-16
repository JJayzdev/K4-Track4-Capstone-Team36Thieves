const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (seconds) => `${String(Math.floor(Math.max(0, seconds) / 60)).padStart(2,'0')}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2,'0')}`;
const timeOf = value => new Date(value).toLocaleTimeString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'});
const dateOf = value => new Date(value).toLocaleDateString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'});
const labels = {observing:'Đang theo dõi', suspected:'Cần chú ý', alert:'Có cảnh báo', unknown:'Thiếu điểm khớp', loading:'Đang nạp', error:'Lỗi camera', empty:'Chưa có video', offline:'Webcam chưa bật'};
const eventLabel = event => event.kind==='occlusion'?'Nghi té ngã do che khuất':'Phát hiện nghi té ngã';
const peopleLabel = event => (event.observations||[]).filter(o=>o.track_id).map(o=>`CAM ${o.camera} · ID ${o.track_id}${o.kind==='occlusion'?` · mất dấu ${o.missing_seconds}s`:''}`).join('; ');
const EDGES = [[5,6],[5,7],[7,9],[6,8],[8,10],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
let currentState = null, currentView = 'monitor', sources = [], knownEvents = new Set(), initializedEvents = false;
let feedKey = '', historyKey = '', audioContext = null, connected = false;
let sound = localStorage.getItem('vinfall-sound') !== 'false';
const videoNodes = new Map();
let webcamStream=null, webcamSession=null, webcamTimer=null, webcamRequest=null, webcamStarting=false;
let drawingExit=false, exitStart=null, exitDraft=null;
const captureCanvas=document.createElement('canvas');

function toast(title, message, info=false) {
  const node = document.createElement('div');
  node.className = `toast${info ? ' info' : ''}`;
  node.innerHTML = `<b>${escapeHTML(title)}</b><p>${escapeHTML(message)}</p>`;
  $('#toast-stack').append(node);
  while ($('#toast-stack').children.length > 4) $('#toast-stack').firstChild.remove();
  setTimeout(() => node.remove(), 6500);
}

async function api(url, method='GET', body) {
  const response = await fetch(url, {method, headers:body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Yêu cầu thất bại (${response.status})`);
  return payload;
}

function initializeAudio() {
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  audioContext.resume().catch(() => {});
}

function beep() {
  if (!sound || !audioContext) return;
  for (let i=0;i<2;i++) {
    const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
    const start = audioContext.currentTime + i*.25;
    oscillator.type='sine'; oscillator.frequency.value=740;
    gain.gain.setValueAtTime(0,start); gain.gain.linearRampToValueAtTime(.09,start+.025); gain.gain.linearRampToValueAtTime(0,start+.18);
    oscillator.connect(gain);gain.connect(audioContext.destination);oscillator.start(start);oscillator.stop(start+.2);
  }
}

function setView(view) {
  currentView=view;
  for (const name of ['monitor','history','data']) $(`#${name}-view`).hidden = view !== name;
  $('#webcam-settings').hidden=view!=='data';
  $$('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  const titles = {monitor:'Giám sát phòng bệnh',history:'Nhật ký cảnh báo',data:'Nguồn video & mô hình'};
  const subtitles = {monitor:'Theo dõi từng phòng. Kịp thời nhận biết, chủ động chăm sóc.',history:'Mỗi sự kiện được ghi nhận, mỗi phòng đều được chú ý.',data:'5 phòng phát lại video và phòng 106 dùng webcam laptop.'};
  $('#page-title').innerHTML = `${titles[view]}<span>.</span>`;
  $('#page-subtitle').textContent=subtitles[view];
  if (view==='data' && currentState) currentState.rooms.forEach(room=>{const select=$(`#source-${room.id}`);if(select)select.value=room.source;});
  if (currentState) render(currentState);
}

function buildRoom(room) {
  const card=document.createElement('article');
  card.className='room-card';card.id=`room-${room.id}`;
  card.innerHTML=`<div class="room-head"><div class="room-label"><div class="room-number">${room.id}</div><div><h3>${escapeHTML(room.name)}</h3><small class="room-camera-count"></small></div></div><span class="status-pill"><i class="dot"></i><span>Đang nạp</span></span></div><div class="camera-pair"></div><div class="room-foot"><button class="source-button" data-source-room="${room.id}">${icon('link')}<span>${escapeHTML(room.source)}</span></button><time>00:00 / 00:00</time></div>`;
  $('#rooms-grid').append(card);
  if(room.kind==='live') {
    card.classList.add('webcam-room');
    card.querySelector('.camera-pair').classList.add('single-camera');
    card.querySelector('.camera-pair').innerHTML=`<div class="camera-frame raw-camera" id="camera-106-0"><video muted playsinline aria-label="Webcam laptop phòng 106"></video><canvas width="640" height="480"></canvas><div class="camera-placeholder">${icon('camera')}Bật webcam để giám sát trực tiếp</div><span class="camera-label"><i></i>CAM 00 · TRỰC TIẾP</span><span class="camera-quality">Camera chưa bật</span><button class="icon-button camera-expand" data-expand="106-0" aria-label="Phóng to webcam">${icon('expand')}</button></div>`;
    card.querySelector('.room-foot').innerHTML=`<button class="button primary webcam-button" id="webcam-button">Bật webcam</button><button class="source-button" data-source-room="106">${icon('shield')}Cài đặt mất dấu</button><time>TRỰC TIẾP</time>`;
    const frame=$('#camera-106-0'), video=frame.querySelector('video'), canvas=frame.querySelector('canvas');
    videoNodes.set('106-0',{frame,video,canvas,live:true});
    canvas.addEventListener('pointerdown',event=>{if(!drawingExit)return;exitStart=canvasPoint(event,canvas);exitDraft=null;canvas.setPointerCapture(event.pointerId);});
    canvas.addEventListener('pointermove',event=>{if(!exitStart)return;const end=canvasPoint(event,canvas);exitDraft=[Math.min(exitStart[0],end[0]),Math.min(exitStart[1],end[1]),Math.max(exitStart[0],end[0]),Math.max(exitStart[1],end[1])];if(currentState)render(currentState);});
    canvas.addEventListener('pointerup',async()=>{exitStart=null;if(exitDraft&&exitDraft[2]-exitDraft[0]>.02&&exitDraft[3]-exitDraft[1]>.02){try{await saveTracking([...(currentState?.tracking.exit_zones||[]),exitDraft]);toast('Đã lưu vùng cửa','Người mất dấu khi ở vùng này được xem là đã đi ra.',true);}catch(error){toast('Không lưu được vùng cửa',error.message);}}exitDraft=null;setExitDrawing(false);});
    canvas.addEventListener('pointercancel',()=>{exitStart=null;exitDraft=null;setExitDrawing(false);});
  }
}

function syncRoomCameras(room,card) {
  if(room.kind==='live')return;
  const pair=card.querySelector('.camera-pair');
  const members=room.cameras.map(camera=>camera.index).join(',');
  if(pair.dataset.members===members) return;
  for(const [key,node] of videoNodes) if(key.startsWith(`${room.id}-`)) {
    node.video.pause();node.video.removeAttribute('src');node.video.load();videoNodes.delete(key);
  }
  pair.dataset.members=members;
  pair.classList.toggle('single-camera',room.cameras.length===1);
  pair.innerHTML=room.cameras.map(({index:i})=>`<div class="camera-frame" id="camera-${room.id}-${i}"><video muted playsinline preload="auto" aria-label="${escapeHTML(room.name)}, camera ${i}"></video><canvas width="640" height="480"></canvas><div class="camera-placeholder">${icon('camera')}Đang nạp video…</div><span class="camera-label"><i></i>CAM ${String(i).padStart(2,'0')} · ${i===0?'GÓC NGANG':'GÓC TRẦN'}</span><span class="camera-quality">Chờ phân tích</span><button class="icon-button camera-expand" data-expand="${room.id}-${i}" title="Phóng to camera ${i}" aria-label="Phóng to ${escapeHTML(room.name)}, camera ${i}">${icon('expand')}</button></div>`).join('');
  if(!room.cameras.length) pair.innerHTML=`<div class="room-empty">${icon('camera')}<span>${room.source?'Đang nạp video…':'Chưa có video cho phòng này'}</span></div>`;
  for (const {index:i} of room.cameras) {
    const frame=$(`#camera-${room.id}-${i}`), video=frame.querySelector('video');
    video.muted=true;
    video.addEventListener('loadeddata',()=>{frame.querySelector('.camera-placeholder').hidden=true;});
    video.addEventListener('error',()=>{const placeholder=frame.querySelector('.camera-placeholder');placeholder.hidden=false;placeholder.textContent='Không đọc được video';});
    videoNodes.set(`${room.id}-${i}`,{frame,video,canvas:frame.querySelector('canvas')});
  }
}

function drawSkeleton(canvas,camera,alert) {
  const ctx=canvas.getContext('2d'), w=canvas.width, h=canvas.height;
  ctx.clearRect(0,0,w,h);
  if (!$('#skeleton-toggle').checked || !camera) return;
  const colors=['#c8ef9f','#a8dcff','#eed0ff','#ffe294','#99f0e1'];
  for(const person of camera.people||[]) {
    const points=person.points, bad=['alert','occluded'].includes(person.state);
    ctx.strokeStyle=bad?'#ffac91':person.visible?colors[(person.track_id-1)%colors.length]:'#ffd47e';
    ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=2.3;
    ctx.setLineDash(person.visible?[]:[7,5]);
    const [x1,y1,x2,y2]=person.box;
    ctx.strokeRect(x1*w,y1*h,(x2-x1)*w,(y2-y1)*h);
    ctx.font='bold 15px system-ui';
    const text=`ID ${person.track_id} · ${person.visible?`${Math.round(person.score*100)}%`:person.state==='occluded'?'NGHI CHE KHUẤT':`mất dấu ${person.missing_seconds}s`}`;
    ctx.fillText(text,Math.max(4,Math.min(x1*w,w-190)),Math.max(20,y1*h-8));
    ctx.setLineDash([]);
    if(!person.visible)continue;
    for (const [a,b] of EDGES) if (points[a][2]>=.25 && points[b][2]>=.25) {
      ctx.beginPath();ctx.moveTo(points[a][0]*w,points[a][1]*h);ctx.lineTo(points[b][0]*w,points[b][1]*h);ctx.stroke();
    }
    for (const [x,y,score] of points) if(score>=.25) {ctx.beginPath();ctx.arc(x*w,y*h,3,0,Math.PI*2);ctx.fill();}
  }
}

function updateRoom(room,state) {
  if (!$(`#room-${room.id}`)) buildRoom(room);
  const card=$(`#room-${room.id}`);
  syncRoomCameras(room,card);
  if(room.kind==='live'){updateWebcamRoom(room,state,card);return;}
  card.querySelector('.room-camera-count').textContent=room.cameras.length?`${String(room.cameras.length).padStart(2,'0')} CAMERA · ${room.cameras.length===1?'MỘT GÓC QUAY':'CÙNG BỘ VIDEO'}`:'CHƯA CÓ CAMERA';
  const sourceInfo=$(`[data-source-camera-info="${room.id}"]`);
  if(sourceInfo) sourceInfo.textContent=room.cameras.length?room.cameras.map(c=>`Camera ${c.index}`).join(' + '):'Chưa có video';
  card.classList.toggle('is-alert',room.state==='alert');card.classList.toggle('is-suspected',room.state==='suspected');
  card.hidden = $('#room-filter').value==='alert' && room.state!=='alert' && room.state!=='suspected';
  const pill=card.querySelector('.status-pill');pill.className=`status-pill ${room.state}`;
  pill.querySelector('span').textContent=labels[room.state]||room.state;
  card.querySelector('time').textContent=`${fmt(room.elapsed)} / ${fmt(room.duration)}`;
  card.querySelector('.source-button span').textContent=room.source||'Chọn nguồn video';
  card.title=room.error||'';
  for (const camera of room.cameras) {
    const {frame,video,canvas}=videoNodes.get(`${room.id}-${camera.index}`);
    if (video.dataset.source!==camera.video_url) {
      video.dataset.source=camera.video_url;video.src=camera.video_url;
      frame.querySelector('.camera-placeholder').hidden=false;
    }
    video.playbackRate=state.speed;
    if(video.readyState>=1 && Math.abs(video.currentTime-room.elapsed)>.3) video.currentTime=Math.min(room.elapsed,Math.max(0,video.duration-.03));
    const shouldPlay=connected && currentView==='monitor' && state.playing && !room.waiting && !room.ended && room.state!=='loading' && !room.error;
    if(shouldPlay && video.paused) video.play().catch(()=>{});
    if(!shouldPlay && !video.paused) video.pause();
    drawSkeleton(canvas,camera,room.state==='alert');
    const quality=frame.querySelector('.camera-quality');
    quality.textContent=room.waiting?'Chờ lượt phát':cameraSummary(camera);
    quality.classList.toggle('low',(camera.people||[]).some(p=>!p.visible));
  }
}

function cameraSummary(camera) {
  const missing=(camera.people||[]).filter(p=>!p.visible);
  return `${camera.visible_count||0} người${missing.length?` · ${missing.length} mất dấu`:''}`;
}

function canvasPoint(event,canvas) {
  const rect=canvas.getBoundingClientRect();
  return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
}

function setExitDrawing(value) {
  drawingExit=value;
  $('#camera-106-0 canvas')?.classList.toggle('drawing-zone',value);
  $('#draw-exit').textContent=value?'Hủy đánh dấu cửa':'Đánh dấu cửa ra/vào';
}

async function saveTracking(zones=currentState?.tracking.exit_zones||[]) {
  await api('/api/tracking','PUT',{missing_seconds:Number($('#missing-seconds').value),minimum_seen:Number($('#minimum-seen').value),exit_margin:Number($('#exit-margin').value)/100,exit_zones:zones});
}

function updateWebcamRoom(room,state,card) {
  const camera=room.cameras[0], node=videoNodes.get('106-0');
  card.querySelector('.room-camera-count').textContent='CAMERA LAPTOP · THEO DÕI NHIỀU NGƯỜI';
  card.classList.toggle('is-alert',room.state==='alert');card.classList.toggle('is-suspected',room.state==='suspected');
  card.hidden=$('#room-filter').value==='alert'&&!['alert','suspected'].includes(room.state);
  const pill=card.querySelector('.status-pill');pill.className=`status-pill ${room.state}`;pill.querySelector('span').textContent=labels[room.state]||room.state;
  card.title=room.error||'';
  const button=$('#webcam-button');
  button.textContent=webcamStarting?'Đang mở…':webcamStream?'Dừng webcam':'Bật webcam';
  button.disabled=webcamStarting||!connected||state.status!=='ready'||(state.webcam.active&&!webcamSession);
  node.frame.querySelector('.camera-placeholder').hidden=!!webcamStream;
  node.frame.querySelector('.camera-placeholder').textContent=state.webcam.active&&!webcamSession?'Webcam đang được giám sát tại tab khác.':'Bật webcam để giám sát trực tiếp';
  node.frame.querySelector('.camera-quality').textContent=room.error||cameraSummary(camera||{});
  if(node.video.videoWidth) {
    node.frame.style.aspectRatio=`${node.video.videoWidth} / ${node.video.videoHeight}`;
    node.canvas.width=node.video.videoWidth;node.canvas.height=node.video.videoHeight;
  }
  drawSkeleton(node.canvas,camera,false);
  const ctx=node.canvas.getContext('2d'), w=node.canvas.width,h=node.canvas.height;
  for(const zone of [...(state.tracking.exit_zones||[]),...(exitDraft?[exitDraft]:[])]) {
    const [x1,y1,x2,y2]=zone;ctx.fillStyle='#68d6e533';ctx.strokeStyle='#82e7f5';ctx.lineWidth=2;
    ctx.fillRect(x1*w,y1*h,(x2-x1)*w,(y2-y1)*h);ctx.strokeRect(x1*w,y1*h,(x2-x1)*w,(y2-y1)*h);
    ctx.fillStyle='#c5f7ff';ctx.font='14px system-ui';ctx.fillText('Cửa ra/vào',x1*w+5,y1*h+18);
  }
  card.querySelector('time').textContent=webcamStream?`LIVE · ${fmt(room.elapsed)}`:'TRỰC TIẾP';
  $('#webcam-status').textContent=room.error||(webcamStream?'Đang giám sát tại phòng 106. Giữ tab này mở.':state.webcam.active?'Camera đang chạy tại một tab khác.':'Bấm Bật webcam ở phòng 106 để cấp quyền camera.');
  if(!$('#missing-seconds').dataset.initialized) {
    $('#missing-seconds').value=state.tracking.missing_seconds;$('#minimum-seen').value=state.tracking.minimum_seen;$('#exit-margin').value=Math.round(state.tracking.exit_margin*100);
    $('#missing-seconds').dataset.initialized='true';
  }
}

async function startWebcam() {
  if(webcamStarting)return;
  webcamStarting=true;if(currentState)render(currentState);initializeAudio();
  try {
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('Mở ứng dụng qua http://localhost:8000 hoặc http://127.0.0.1:8000 để dùng camera.');
    const device=$('#webcam-device').value;
    webcamStream=await navigator.mediaDevices.getUserMedia({audio:false,video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20},...(device?{deviceId:{exact:device}}:{})}});
    const result=await api('/api/webcam/start','POST');webcamSession=result.session;
    const video=videoNodes.get('106-0').video;video.srcObject=webcamStream;await video.play();
    webcamStream.getVideoTracks()[0].addEventListener('ended',()=>{if(webcamStream)stopWebcam();});
    const selected=webcamStream.getVideoTracks()[0].getSettings().deviceId;
    const devices=await navigator.mediaDevices.enumerateDevices();
    $('#webcam-device').innerHTML=devices.filter(d=>d.kind==='videoinput').map((d,i)=>`<option value="${escapeHTML(d.deviceId)}">${escapeHTML(d.label||`Camera ${i+1}`)}</option>`).join('');
    $('#webcam-device').value=selected;$('#webcam-device').disabled=true;
    sendWebcamFrame();
  } catch(error) {
    await stopWebcam();
    const messages={NotAllowedError:'Chưa được cấp quyền camera. Cho phép camera trong trình duyệt rồi bật lại.',NotFoundError:'Không tìm thấy webcam. Kiểm tra camera laptop.',NotReadableError:'Không mở được camera. Kiểm tra ứng dụng khác đang sử dụng camera.'};
    toast('Không bật được webcam',messages[error.name]||error.message);
  } finally {webcamStarting=false;if(currentState)render(currentState);}
}

async function stopWebcam() {
  clearTimeout(webcamTimer);webcamRequest?.abort();
  const session=webcamSession;webcamSession=null;
  const stream=webcamStream;webcamStream=null;stream?.getTracks().forEach(track=>track.stop());
  const video=videoNodes.get('106-0')?.video;if(video){video.pause();video.srcObject=null;}
  $('#webcam-device').disabled=false;
  if(session)await api('/api/webcam/stop','POST',{session}).catch(()=>{});
  if(currentState)render(currentState);
}

async function sendWebcamFrame() {
  const session=webcamSession;if(!session||!webcamStream)return;
  const started=performance.now(),video=videoNodes.get('106-0').video;
  if(video.readyState<2){webcamTimer=setTimeout(sendWebcamFrame,100);return;}
  captureCanvas.width=Math.min(640,video.videoWidth);captureCanvas.height=Math.round(captureCanvas.width*video.videoHeight/video.videoWidth);
  captureCanvas.getContext('2d').drawImage(video,0,0,captureCanvas.width,captureCanvas.height);
  const blob=await new Promise(resolve=>captureCanvas.toBlob(resolve,'image/jpeg',.8));
  if(!blob||session!==webcamSession)return;
  webcamRequest=new AbortController();const timeout=setTimeout(()=>webcamRequest?.abort(),4500);
  try {
    const response=await fetch('/api/webcam/frame',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Vinfall-Session':session},body:blob,signal:webcamRequest.signal});
    if(!response.ok){const body=await response.json();throw new Error(body.detail||'Không xử lý được webcam');}
  } catch(error) {
    if(session===webcamSession){toast('Webcam đã dừng',error.name==='AbortError'?'Không nhận được kết quả phân tích. Bật lại camera để thử tiếp.':error.message);await stopWebcam();}
  } finally {clearTimeout(timeout);}
  if(session===webcamSession)webcamTimer=setTimeout(sendWebcamFrame,Math.max(0,100-(performance.now()-started)));
}

function renderAlerts(state) {
  const pending=state.alerts.filter(event=>!event.acknowledged_at);
  const key=state.alerts.map(e=>`${e.id}:${e.acknowledged_at}:${e.cameras}:${e.kind}:${e.observations?.length}`).join('|');
  if(feedKey!==key || !$('#alert-feed').children.length) {
    feedKey=key;
    $('#alert-feed').innerHTML=pending.length?pending.slice(0,12).map(event=>`<article class="alert-item"><div class="alert-item-top"><b>${escapeHTML(event.room_name)}</b><time>${timeOf(event.created_at)}</time></div><p>${eventLabel(event)}</p><small>${escapeHTML(peopleLabel(event)||`CAM ${event.cameras.join(' + ')}`)} · ${fmt(event.video_time)}</small><div class="alert-item-actions"><button data-ack="${event.id}">Đã tiếp nhận</button><button data-event="${event.id}">Xem ảnh</button></div></article>`).join(''):`<div class="feed-empty"><div class="empty-circle">${icon('shield')}</div><b>Chưa có cảnh báo cần xử lý</b><p>Khi phát hiện nghi té ngã, phòng và hình ảnh sẽ xuất hiện tại đây.</p></div>`;
  }
  if(historyKey!==key) {
    historyKey=key;
    $('#history-body').innerHTML=state.alerts.map(e=>`<tr><td>${timeOf(e.created_at)}<br><small>${dateOf(e.created_at)}</small></td><td><strong>${escapeHTML(e.room_name)}</strong><br><small>${eventLabel(e)}</small></td><td>${escapeHTML(e.source)} · ${fmt(e.video_time)}</td><td>${escapeHTML(peopleLabel(e)||e.cameras.map(i=>`CAM ${i}`).join(' + '))}</td><td><span class="tag ${e.acknowledged_at?'':'pending'}">${e.acknowledged_at?'Đã tiếp nhận':'Chờ xác nhận'}</span></td><td><button data-event="${e.id}">Chi tiết</button></td></tr>`).join('');
  }
  $('#history-empty').hidden=state.alerts.length>0;
  $('#pending-count').textContent=pending.length;
  $('#alert-stat').innerHTML=`${String(pending.length).padStart(2,'0')}<small>cảnh báo</small>`;
  $('.alert-stat').classList.toggle('has-alerts',pending.length>0);
  $('#alert-note').textContent=pending.length?'Cần người trực kiểm tra':'Không có cảnh báo chờ';
  $('#rail-count').hidden=!pending.length;$('#rail-count').textContent=pending.length;
  if(!initializedEvents) {state.alerts.forEach(e=>knownEvents.add(e.id));initializedEvents=true;}
  for(const event of [...state.alerts].reverse()) if(!knownEvents.has(event.id)) {
    knownEvents.add(event.id);
    toast(`${eventLabel(event)} · ${event.room_name}`,`${peopleLabel(event)||`Camera ${event.cameras.join(', ')}`} · ${fmt(event.video_time)}. Vui lòng kiểm tra.`);
    beep();
    if('Notification' in window && Notification.permission==='granted') new Notification(`VinFall · ${event.room_name}`,{body:`${eventLabel(event)}. ${peopleLabel(event)}. Vui lòng kiểm tra.`,tag:event.id,icon:'/static/favicon.svg'});
  }
}

function render(state) {
  currentState=state;
  const cameraCount=state.rooms.reduce((n,r)=>n+r.cameras.length,0);
  $('#camera-stat').innerHTML=`${String(cameraCount).padStart(2,'0')}<small>camera</small>`;
  $('#camera-count').textContent=cameraCount;
  $('#room-stat').innerHTML=`${String(state.rooms.filter(room=>room.cameras.length>0).length).padStart(2,'0')}<small>/ ${state.rooms.length} phòng</small>`;
  $('#model-status').textContent=state.status==='ready'?'Sẵn sàng':state.status==='error'?'Cần kiểm tra':'Đang nạp';
  $('#model-dot').classList.toggle('offline',state.status!=='ready');
  const banner=$('#connection-banner');
  banner.hidden=connected && state.status==='ready';
  banner.classList.toggle('error',state.status==='error'||!connected);
  if(!banner.hidden) banner.textContent=connected?state.message:'Mất kết nối máy chủ. Đang thử kết nối lại…';
  const replayCount=state.rooms.filter(r=>r.kind==='replay').reduce((n,r)=>n+r.cameras.length,0);
  $('#play-button').disabled=!connected||state.status!=='ready'||!replayCount;$('#restart-button').disabled=!connected||state.status!=='ready'||!replayCount;
  $('#play-button').innerHTML=`${icon(state.playing?'pause':'play')}<span>${state.playing?'Tạm dừng':state.duration>0&&state.elapsed>=state.duration?'Phát lại mô phỏng':state.elapsed>0?'Tiếp tục phát':'Bắt đầu mô phỏng'}</span>`;
  $('#speed-select').value=String(state.speed);$('#loop-toggle').checked=state.loop;
  $('#timeline-progress').style.width=`${Math.min(100,state.elapsed/Math.max(state.duration,.1)*100)}%`;
  $('#timeline-time').textContent=`${fmt(state.elapsed)} / ${fmt(state.duration)}`;
  state.rooms.forEach(room=>updateRoom(room,state));
  if(!$('.legend-card')) {
    const legend=document.createElement('article');legend.className='legend-card';
    legend.innerHTML=`<div class="eyebrow">THEO DÕI TỪNG NGƯỜI</div><h3>Nhiều người.<br>Mỗi ID một lịch sử.</h3><p>Phòng 106 dùng webcam laptop. Mất dấu bên trong khung hình đủ thời gian sẽ phát cảnh báo nghi té ngã do che khuất.</p><div class="dual-icon">${icon('camera')}<span>Người → Phòng → Cảnh báo</span></div>`;
    $('#rooms-grid').append(legend);
  }
  $('.legend-card').hidden=$('#room-filter').value!=='all';
  $('#no-rooms').hidden=state.rooms.some(r=>!$(`#room-${r.id}`).hidden);
  $('#room-overview').innerHTML=state.rooms.map(r=>`<div class="overview-row"><span><i class="dot${['error','unknown','loading','empty','offline'].includes(r.state)?' offline':''}" style="${r.state==='alert'?'background:#ca7560':''}"></i>${escapeHTML(r.name)}</span><small>${r.waiting?'Chờ lượt phát':r.ended?'Đã hết video':labels[r.state]}</small></div>`).join('');
  $('#webhook-info').textContent=state.webhook==='disabled'?'Kênh cảnh báo: dashboard, âm thanh và thông báo trình duyệt khi được bật.':`Webhook: ${{configured:'đã cấu hình',delivered:'đã gửi cảnh báo',failed:'gửi lỗi; sự kiện vẫn được lưu cục bộ'}[state.webhook]}`;
  renderAlerts(state);
}

async function acknowledge(id) {
  try {await api(`/api/alerts/${id}/acknowledge`,'POST');toast('Đã tiếp nhận','Trạng thái cảnh báo đã được lưu.',true);if($('#event-dialog').open) $('#event-dialog').close();}
  catch(error){toast('Không thể xác nhận',error.message);}
}

function openEvent(id) {
  const event=currentState?.alerts.find(e=>e.id===id);if(!event)return;
  const cameras=event.available_cameras||event.cameras;
  const lost=(event.observations||[]).filter(o=>o.kind==='occlusion');
  $('#event-title').textContent=`${eventLabel(event)} · ${event.room_name}`;
  $('#event-detail').innerHTML=`<div class="evidence-pair${cameras.length===1&&!lost.length?' single-camera':''}">${cameras.map(i=>`<div><img src="/api/alerts/${event.id}/evidence/${i}" alt="Ảnh tại lúc cảnh báo, camera ${i}"><p>CAM ${i} · Tại lúc phát cảnh báo</p></div>`).join('')}${lost.map(o=>`<div><img src="/api/alerts/${event.id}/evidence/${o.camera}/person/${o.track_id}" alt="Ảnh cuối cùng thấy người ID ${o.track_id}"><p>CAM ${o.camera} · ID ${o.track_id} · Lần cuối nhìn thấy ${fmt(o.last_seen)}</p></div>`).join('')}</div><div class="event-meta"><span>${dateOf(event.created_at)} · ${timeOf(event.created_at)}</span><span>Nguồn: ${escapeHTML(event.source)} · ${fmt(event.video_time)}</span><span>${escapeHTML(peopleLabel(event))}</span></div><div class="event-notice">${lost.length?'Người đã mất dấu bên trong vùng quan sát, chưa ghi nhận đi ra. Đây là suy luận nghi té ngã do che khuất, không xác nhận được tư thế khi bị che.':'Đây là cảnh báo nghi té ngã từ mô hình chuyển động.'} Người trực cần kiểm tra tình trạng thực tế.</div>${event.acknowledged_at?`<p class="event-meta">Đã tiếp nhận lúc ${timeOf(event.acknowledged_at)}</p>`:`<button class="button primary event-ack" data-ack="${event.id}">${icon('check')}Xác nhận đã tiếp nhận</button>`}`;
  $('#event-detail').querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>{const tries=Number(img.dataset.tries||0);if(tries<3){img.dataset.tries=tries+1;setTimeout(()=>{img.src=img.src.split('?')[0]+`?retry=${tries+1}`;},700);}}));
  $('#event-dialog').showModal();
  $('.close-dialog').focus({preventScroll:true});
  $('#event-dialog').scrollTop=0;
}

async function loadDataSettings() {
  try {
    const payload=await api('/api/sources');sources=payload.sequences;
    $('#source-settings').innerHTML=[101,102,103,104,105].map(id=>`<div class="source-row"><div><b>Phòng ${id}</b><small data-source-camera-info="${id}">Chưa có video</small></div><select id="source-${id}" aria-label="Nguồn video phòng ${id}" ${sources.length?'':'disabled'}><option value="" disabled>Chọn nguồn video</option>${sources.map(s=>`<option value="${escapeHTML(s)}">${escapeHTML(s)} · ${payload.camera_indices[s].length} camera</option>`).join('')}</select><button class="button subtle" data-apply-source="${id}" ${sources.length?'':'disabled'}>Áp dụng</button></div>`).join('');
    if(currentState) currentState.rooms.forEach(r=>{const select=$(`#source-${r.id}`);if(select)select.value=r.source;});
    const report=await api('/api/training-report'), metrics=report.test;
    $('#training-info').innerHTML=`<div>Chỉ số phân loại tư thế theo cửa sổ · tập kiểm tra</div><div class="metric-row"><div>Precision<b>${(metrics.precision*100).toFixed(1)}%</b></div><div>Recall<b>${(metrics.recall*100).toFixed(1)}%</b></div><div>F1<b>${(metrics.f1*100).toFixed(1)}%</b></div></div><p>${report.splits.train.length} video huấn luyện · ${report.splits.validation.length} xác thực · ${report.splits.test.length} kiểm tra.</p><p>Hai camera của cùng bộ luôn ở cùng tập. 5 bộ trình diễn nằm trong tập kiểm tra.</p>`;
  } catch(error){$('#training-info').textContent=error.message;}
}

function connect() {
  const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
  socket.onopen=()=>{connected=true;};
  socket.onmessage=event=>{try{render(JSON.parse(event.data));}catch(error){console.error(error);}};
  socket.onclose=()=>{connected=false;videoNodes.forEach(({video,live})=>{if(!live)video.pause();});stopWebcam();if(currentState)render(currentState);setTimeout(connect,2000);};
  socket.onerror=()=>socket.close();
}

document.addEventListener('click',async event=>{
  const view=event.target.closest('[data-view]');if(view)setView(view.dataset.view);
  const ack=event.target.closest('[data-ack]');if(ack)await acknowledge(ack.dataset.ack);
  const detail=event.target.closest('[data-event]');if(detail)openEvent(detail.dataset.event);
  const expand=event.target.closest('[data-expand]');if(expand){const node=$(`#camera-${expand.dataset.expand}`);try{if(document.fullscreenElement)await document.exitFullscreen();else await node.requestFullscreen();}catch{toast('Phóng to camera','Trình duyệt không hỗ trợ chế độ toàn màn hình.',true);}}
  const source=event.target.closest('[data-source-room]');if(source){setView('data');if(source.dataset.sourceRoom==='106')$('#webcam-settings').scrollIntoView({behavior:'smooth'});else $(`#source-${source.dataset.sourceRoom}`)?.focus();}
  const apply=event.target.closest('[data-apply-source]');if(apply){apply.disabled=true;try{await api(`/api/rooms/${apply.dataset.applySource}/source`,'PUT',{sequence:$(`#source-${apply.dataset.applySource}`).value});toast('Đang đổi bộ video','Phiên phát lại được đưa về đầu theo nguồn video mới.',true);}catch(error){toast('Không thể đổi nguồn',error.message);}finally{apply.disabled=false;}}
  if(event.target.closest('#webcam-button')){if(webcamStream)await stopWebcam();else await startWebcam();}
});

$('#save-tracking').addEventListener('click',async()=>{try{await saveTracking();toast('Đã lưu cấu hình','Thời gian mất dấu và vùng ra/vào đã được cập nhật.',true);}catch(error){toast('Không lưu được cấu hình',error.message);}});
$('#draw-exit').addEventListener('click',()=>{if(!webcamStream){toast('Chưa bật webcam','Bật webcam tại phòng 106 trước khi đánh dấu cửa.',true);return;}setExitDrawing(!drawingExit);setView('monitor');$('#room-106').scrollIntoView({behavior:'smooth',block:'center'});if(drawingExit)toast('Đánh dấu cửa ra/vào','Kéo một hình chữ nhật trên ảnh webcam, bao gồm vị trí bàn chân khi đi qua cửa.',true);});
$('#clear-exits').addEventListener('click',async()=>{try{await saveTracking([]);toast('Đã xóa vùng cửa','Vẫn nhận diện đi ra qua mép khung hình.',true);}catch(error){toast('Không xóa được vùng cửa',error.message);}});
window.addEventListener('pagehide',()=>{const session=webcamSession;webcamStream?.getTracks().forEach(track=>track.stop());if(session)fetch('/api/webcam/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session}),keepalive:true}).catch(()=>{});});

$('#play-button').addEventListener('click',async()=>{initializeAudio();try{await api('/api/control','POST',{action:currentState?.playing?'pause':'play'});}catch(error){toast('Không thể phát video',error.message);}});
$('#restart-button').addEventListener('click',async()=>{initializeAudio();try{await api('/api/control','POST',{action:'restart'});}catch(error){toast('Không thể phát lại',error.message);}});
$('#speed-select').addEventListener('change',async event=>{try{await api('/api/control','POST',{action:'settings',speed:Number(event.target.value)});}catch(error){toast('Không thể đổi tốc độ',error.message);}});
$('#loop-toggle').addEventListener('change',async event=>{try{await api('/api/control','POST',{action:'settings',loop:event.target.checked});}catch(error){toast('Không thể đổi chế độ',error.message);}});
$('#room-filter').addEventListener('change',()=>{if(currentState)render(currentState);});
$('#skeleton-toggle').addEventListener('change',()=>{if(currentState)render(currentState);});
$('#sound-button').classList.toggle('enabled',sound);
$('#sound-button').addEventListener('click',()=>{initializeAudio();sound=!sound;localStorage.setItem('vinfall-sound',String(sound));$('#sound-button').classList.toggle('enabled',sound);$('#sound-button').title=sound?'Tắt âm báo':'Bật âm báo';$('#sound-button').setAttribute('aria-label',sound?'Tắt âm báo':'Bật âm báo');if(sound)beep();});
$('#notify-button').addEventListener('click',async()=>{if(!('Notification' in window)){toast('Thông báo','Trình duyệt này không hỗ trợ thông báo hệ thống.',true);return;}const permission=await Notification.requestPermission();toast('Thông báo',permission==='granted'?'Đã bật thông báo phòng khi phát hiện nghi té ngã.':'Chưa được cấp quyền. Cảnh báo vẫn hiển thị trên dashboard.',true);});
$('.close-dialog').addEventListener('click',()=>$('#event-dialog').close());
$('#event-dialog').addEventListener('click',event=>{if(event.target===$('#event-dialog'))$('#event-dialog').close();});
function tick(){const now=new Date();$('#clock').textContent=timeOf(now);$('#today').textContent=now.toLocaleDateString('vi-VN',{weekday:'long',day:'2-digit',month:'2-digit',year:'numeric',timeZone:'Asia/Ho_Chi_Minh'});}tick();setInterval(tick,1000);
connect();loadDataSettings();
