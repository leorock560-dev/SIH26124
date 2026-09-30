const authApiBase = window.URBANEYE_API_BASE || '/api';
fetch(`${authApiBase}/auth/me`, { credentials: 'include' }).then(async response => {
	if (!response.ok) {
		location.replace('/');
		return null;
	}
	return response.json();
}).then(officer => {
	if (!officer) return;
	const area = document.getElementById('officerArea');
	if (!area) return;
	const label = document.createElement('span');
	label.className = 'officer-name';
	label.textContent = `Officer: ${officer.name}`;
	const button = document.createElement('button');
	button.className = 'logout-btn';
	button.textContent = 'Sign out';
	button.addEventListener('click', async () => {
		await fetch(`${authApiBase}/auth/logout`, { method: 'POST', credentials: 'include' });
		location.href = '/';
	});
	area.replaceChildren(label, button);
}).catch(() => location.replace('/'));
