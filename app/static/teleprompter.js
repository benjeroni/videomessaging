'use strict';
(() => {
  const root = document.getElementById('recorder');
  if (!root) return;
  const el = id => document.getElementById(id);
  const editor = el('script-text'), display = el('script-display'), content = el('script-content');
  const speed = el('script-speed'), size = el('script-size'), toggle = el('script-toggle');
  let running = false, frame, lastTime = null, position = 0, debounce;
  let savedText = editor.value, saving = null;
  function pause(message = 'Paused') {
    running = false;
    cancelAnimationFrame(frame);
    lastTime = null;
    toggle.textContent = 'Start scrolling';
    el('script-scroll-status').textContent = message;
  }
  function reset() {
    pause('Ready');
    position = 0;
    display.scrollTop = 0;
  }
  function tick(time) {
    if (!running) return;
    if (lastTime !== null) {
      // Cap the delta so switching browser tabs never skips a large block.
      position += Math.min(time - lastTime, 100) / 1000 * Number(speed.value);
      display.scrollTop = position;
      if (position >= display.scrollHeight - display.clientHeight) {
        pause('End of script');
        return;
      }
    }
    lastTime = time;
    frame = requestAnimationFrame(tick);
  }
  function start() {
    if (!editor.value.trim()) return;
    if (display.scrollTop >= display.scrollHeight - display.clientHeight - 1) reset();
    position = display.scrollTop;
    running = true;
    lastTime = null;
    toggle.textContent = 'Pause scrolling';
    el('script-scroll-status').textContent = 'Scrolling';
    frame = requestAnimationFrame(tick);
  }
  function render() {
    content.textContent = editor.value || 'Your script will appear here.';
    toggle.disabled = !editor.value.trim();
    reset();
  }
  function preferences() {
    content.style.fontSize = `${size.value}px`;
    el('script-size-value').textContent = `${size.value} px`;
    el('script-speed-value').textContent = `${speed.value} px/s`;
    try { localStorage.setItem('teleprompter-preferences', JSON.stringify({speed:speed.value, size:size.value, auto:el('script-auto').checked})); } catch {}
  }
  try {
    const stored = JSON.parse(localStorage.getItem('teleprompter-preferences'));
    if (stored) {
      if (Number.isFinite(Number(stored.speed))) speed.value = stored.speed;
      if (Number.isFinite(Number(stored.size))) size.value = stored.size;
      if (typeof stored.auto === 'boolean') el('script-auto').checked = stored.auto;
    }
  } catch {}
  async function save() {
    clearTimeout(debounce);
    if (saving) await saving;
    if (savedText === editor.value) return;
    const text = editor.value;
    el('script-save-status').textContent = 'Saving script…';
    saving = (async () => {
      const response = await fetch(root.dataset.scriptUrl, {
        method:'POST', headers:{'X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},
        body:new URLSearchParams({script:text})
      });
      if (!response.ok || response.redirected) throw new Error('Script could not be saved. Check your connection and sign-in, then retry.');
      savedText = text;
      el('script-save-status').textContent = savedText === editor.value ? 'Script saved' : 'Unsaved changes';
    })();
    try { await saving; } finally { saving = null; }
    if (savedText !== editor.value) await save();
  }
  function saveWithFeedback() {
    return save().catch(error => {el('script-save-status').textContent = error.message;});
  }
  root.saveScript = save;
  editor.addEventListener('input', () => {
    render();
    el('script-save-status').textContent = 'Unsaved changes';
    clearTimeout(debounce);
    debounce = setTimeout(saveWithFeedback, 700);
  });
  el('save-script').addEventListener('click', saveWithFeedback);
  if (el('script-file')) el('script-file').addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 80000) throw new Error('Keep your script under 20,000 characters.');
      const text = await file.text();
      if (text.length > 20000) throw new Error('Keep your script under 20,000 characters.');
      editor.value = text;
      editor.dispatchEvent(new Event('input'));
    } catch (error) { el('script-save-status').textContent = error.message; }
    event.target.value = '';
  });
  toggle.addEventListener('click', () => running ? pause() : start());
  el('script-reset').addEventListener('click', reset);
  speed.addEventListener('input', preferences);
  size.addEventListener('input', () => {preferences(); position = display.scrollTop;});
  el('script-auto').addEventListener('change', preferences);
  // Manual scrolling pauses the motor, so readers can find their place.
  display.addEventListener('wheel', () => pause(), {passive:true});
  display.addEventListener('touchstart', () => pause(), {passive:true});
  display.addEventListener('keydown', event => {
    if (['ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(event.key)) pause();
  });
  root.addEventListener('recorderstate', event => {
    const mode = event.detail;
    editor.disabled = el('save-script').disabled = ['recording','saving'].includes(mode);
    if (el('script-file')) el('script-file').disabled = editor.disabled;
    if (mode === 'recording') {
      if (el('script-editor')) el('script-editor').open = false;
      reset();
      if (el('script-auto').checked) start();
    } else pause('Ready');
  });
  document.addEventListener('visibilitychange', () => {if (document.hidden) pause();});
  window.addEventListener('pagehide', () => pause());
  window.addEventListener('beforeunload', event => {
    if (editor.value !== savedText) {event.preventDefault(); event.returnValue = '';}
  });
  preferences();
  render();
})();
