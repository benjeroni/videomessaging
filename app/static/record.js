'use strict';
(() => {
  const root = document.getElementById('recorder');
  if (!root) return;
  const el = id => document.getElementById(id);
  const preview = el('preview'), status = el('record-status');
  let stream, recorder, chunks = [], blob, objectURL, timer, started, dirty = false, saving = false;
  function state(mode) {
    root.dispatchEvent(new CustomEvent('recorderstate', {detail: mode}));
    ['enable', 'start', 'stop', 'redo', 'save'].forEach(id => { el(id).hidden = !({idle:['enable','start'], ready:['start'], recording:['stop'], review:['redo','save'], saving:[]}[mode].includes(id)); });
    el('camera').disabled = el('microphone').disabled = ['recording','saving'].includes(mode);
  }
  function release() { if (stream) stream.getTracks().forEach(track => track.stop()); }
  async function enable() {
    try {
      if (!window.isSecureContext) throw new Error('Camera access requires HTTPS (or localhost).');
      if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('Recording is unavailable. Use desktop Chrome or Edge over HTTPS.');
      release();
      stream = await navigator.mediaDevices.getUserMedia({video: el('camera').value ? {deviceId:{exact:el('camera').value},width:{ideal:1280},height:{ideal:720}} : {width:{ideal:1280},height:{ideal:720}},audio: el('microphone').value ? {deviceId:{exact:el('microphone').value}} : true});
      preview.srcObject = stream; preview.muted = true; preview.controls = false;
      if (objectURL) { URL.revokeObjectURL(objectURL); objectURL = null; }
      preview.removeAttribute('src'); await preview.play();
      const devices = await navigator.mediaDevices.enumerateDevices();
      for (const [id, kind] of [['camera','videoinput'],['microphone','audioinput']]) {
        const select = el(id), previous = select.value;
        select.replaceChildren(...devices.filter(d => d.kind === kind).map((d, i) => new Option(d.label || `${id} ${i+1}`, d.deviceId)));
        if ([...select.options].some(o => o.value === previous)) select.value = previous;
      }
      el('start').disabled = false; state('ready'); status.textContent = 'Ready when you are.';
    } catch (error) {
      release(); state('idle'); el('start').disabled = true;
      status.textContent = ({NotAllowedError:'Camera or microphone permission denied. Allow both in browser settings and retry.',NotFoundError:'Camera or microphone unavailable. Connect both devices and retry.',NotReadableError:'Camera or microphone is busy. Close other apps and retry.'})[error.name] || error.message;
    }
  }
  el('enable').onclick = enable;
  ['camera','microphone'].forEach(id => el(id).onchange = () => { if (!dirty || confirm('Discard this unsaved recording and change devices?')) {dirty=false; blob=null; enable();} });
  el('start').onclick = () => {
    try {
      chunks = []; blob = null;
      const mimeType = ['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(stream, mimeType ? {mimeType} : {});
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        clearInterval(timer); blob = new Blob(chunks, {type:recorder.mimeType}); dirty = true;
        preview.srcObject = null; release(); objectURL = URL.createObjectURL(blob); preview.src = objectURL; preview.muted = false; preview.controls = true; preview.autoplay = false; preview.load();
        state('review'); status.textContent = 'Preview your recording using Play, re-record, or Save & Next.';
      };
      recorder.onerror = () => {clearInterval(timer); status.textContent = 'Recording failed. Enable your devices and try again.'; state('idle'); release();};
      recorder.start(1000); started = Date.now(); dirty = true; state('recording'); status.textContent = 'Recording…';
      timer = setInterval(() => { const seconds = Math.floor((Date.now()-started)/1000); el('timer').textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`; if (seconds >= Number(root.dataset.limit) && recorder.state === 'recording') recorder.stop(); },250);
    } catch { status.textContent = 'Could not start recording. Re-enable your camera and microphone.'; state('idle'); }
  };
  el('stop').onclick = () => { if (recorder && recorder.state === 'recording') recorder.stop(); };
  el('redo').onclick = () => { dirty=false; blob=null; el('timer').textContent='00:00'; enable(); };
  el('save').onclick = async () => {
    if (!blob || saving) return;
    saving = true; state('saving'); status.textContent = 'Uploading and processing… Please keep this page open.';
    const data = new FormData(); data.append('video', blob, 'recording.webm');
    try {
      if (root.saveScript) await root.saveScript();
      const response = await fetch(root.dataset.upload, {method:'POST',headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:data});
      if (response.redirected) throw new Error('Your session expired. Sign in in another tab, then retry.');
      let result; try {result = await response.json();} catch {throw new Error('Upload failed. Check the server connection and upload limit, then retry.');}
      if (!response.ok) throw new Error(result.error || 'Upload failed. Retry.');
      dirty=false; window.location.assign(result.next_url);
    } catch(error) { status.textContent=error.message; saving=false; state('review'); }
  };
  window.addEventListener('beforeunload', event => { if (dirty) {event.preventDefault();event.returnValue='';} });
  window.addEventListener('pagehide', release);
})();
