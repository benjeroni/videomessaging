'use strict';
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(button.dataset.copy); button.textContent = 'Copied'; }
  catch { window.prompt('Copy this private recipient URL:', button.dataset.copy); }
}));
const selectAllRecipients = document.getElementById('select-all-recipients');
if (selectAllRecipients) {
  const boxes = [...document.querySelectorAll('input[name="recipients"]')];
  selectAllRecipients.addEventListener('change', () => boxes.forEach(box => {box.checked = selectAllRecipients.checked;}));
  boxes.forEach(box => box.addEventListener('change', () => {
    selectAllRecipients.checked = boxes.every(item => item.checked);
    selectAllRecipients.indeterminate = boxes.some(item => item.checked) && !selectAllRecipients.checked;
  }));
}
