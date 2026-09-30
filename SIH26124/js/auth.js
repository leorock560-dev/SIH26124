(() => {
	const modal = document.getElementById('authModal');
	const message = document.getElementById('authMessage');
	const show = view => {
		document.getElementById('loginForm').hidden = view !== 'login';
		document.getElementById('signupForm').hidden = view !== 'signup';
		message.className = 'form-message';
	};
	const notice = (text, isError = false) => {
		message.textContent = text;
		message.className = `form-message show${isError ? ' error' : ''}`;
	};
	const goToDashboard = () => {
		const apiBase = new URL(window.URBANEYE_API_BASE || '/api', window.location.href);
		location.assign(new URL('/dashboard.html', apiBase.origin));
	};
	const submit = async (path, values) => {
		let response;
		try {
			response = await fetch(`${window.URBANEYE_API_BASE || '/api'}/auth/${path}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify(values),
			});
		} catch (error) {
			throw new Error(`Could not reach the authentication server at ${window.URBANEYE_API_BASE || '/api'}. Start FastAPI on port 8000. ${error.message}`);
		}
		const body = await response.text();
		let result = {};
		if (body.trim()) {
			try {
				result = JSON.parse(body);
			} catch {
				throw new Error(response.ok ? 'The server returned an invalid response.' : `Request failed (${response.status}).`);
			}
		}
		if (!response.ok) {
			if (response.status === 405) {
				throw new Error('The authentication request reached a static file server. Open the app from FastAPI at http://127.0.0.1:8000, or use Live Server on port 5500/5501 with FastAPI running.');
			}
			throw new Error(result.detail || result.message || `Request failed (${response.status}).`);
		}
		return result;
	};

	document.querySelectorAll('[data-open-auth]').forEach(button => button.addEventListener('click', () => {
		modal.classList.add('open');
		show(button.dataset.openAuth);
	}));
	document.querySelector('.close').addEventListener('click', () => modal.classList.remove('open'));
	modal.addEventListener('click', event => {
		if (event.target === modal) modal.classList.remove('open');
	});
	document.querySelectorAll('[data-switch]').forEach(button => button.addEventListener('click', () => show(button.dataset.switch)));
	document.querySelectorAll('[data-password-toggle]').forEach(button => {
		const input = document.getElementById(button.dataset.passwordToggle);
		button.addEventListener('click', () => {
			const reveal = input.type === 'password';
			input.type = reveal ? 'text' : 'password';
			button.setAttribute('aria-pressed', String(reveal));
			button.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
			button.title = reveal ? 'Hide password' : 'Show password';
		});
	});

	document.getElementById('signup').addEventListener('submit', async event => {
		event.preventDefault();
		const values = Object.fromEntries(new FormData(event.currentTarget));
		try {
			await submit('signup', values);
			await submit('login', values);
			goToDashboard();
		} catch (error) {
			notice(error.message, true);
		}
	});
	document.getElementById('login').addEventListener('submit', async event => {
		event.preventDefault();
		const values = Object.fromEntries(new FormData(event.currentTarget));
		try {
			await submit('login', values);
			goToDashboard();
		} catch (error) {
			notice(error.message, true);
		}
	});
})();
