'use strict';
(() => {
  const root = document.getElementById('landing'); if (!root) return;
  function sessionUUID() {
    if (crypto.randomUUID) return crypto.randomUUID();
    // getRandomValues also works on LAN HTTP; randomUUID requires HTTPS.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  let session;
  try {session=sessionStorage.getItem('video-session'); if (!session) {session=sessionUUID();sessionStorage.setItem('video-session',session);}}
  catch {session=sessionUUID();}
  const sent = new Set(), pending = new Set();
  async function track(event) {
    if (sent.has(event) || pending.has(event)) return;
    pending.add(event);
    try {
      const response = await fetch('/api/event', {method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({token:root.dataset.token,event,session})});
      if (response.ok) sent.add(event);
    } catch {} finally {pending.delete(event);}
  }
  track('page_view');
  const video = document.getElementById('message-video');
  if (video) {
    video.addEventListener('play', () => track('video_play'));
    video.addEventListener('timeupdate', () => {if (Number.isFinite(video.duration) && video.duration > 0) for (const n of [25,50,75]) if (video.currentTime/video.duration >= n/100) track(`video_${n}`);});
    video.addEventListener('ended', () => track('video_complete'));
    video.addEventListener('error', () => {document.getElementById('playback-error').hidden=false;});
  }
  document.getElementById('cta').addEventListener('click', () => track('cta_click'));
})();
