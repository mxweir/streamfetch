'use strict';
(async () => {
  const token = location.hash.slice(1);
  history.replaceState(null, '', '/pair');
  const status = document.getElementById('status');
  if (!token) {
    status.textContent = 'Generate a new QR code in StreamFetch on your computer.';
    return;
  }
  try {
    const response = await fetch('/pair', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: new URLSearchParams({token})
    });
    if (!response.ok) throw new Error('Pairing unavailable');
    location.replace('/');
  } catch {
    status.textContent = 'This QR code expired, was already used, or could not connect. Generate a new code on your computer.';
  }
})();
