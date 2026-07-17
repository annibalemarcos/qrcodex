document.addEventListener('click', async (event) => {
  const btn = event.target.closest('[data-copy]');
  if (!btn) return;
  const original = btn.textContent;
  try {
    await navigator.clipboard.writeText(btn.dataset.copy);
    btn.textContent = 'Copiado!';
  } catch (err) {
    const input = document.createElement('input');
    input.value = btn.dataset.copy;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
    btn.textContent = 'Copiado!';
  }
  setTimeout(() => btn.textContent = original, 1300);
});
