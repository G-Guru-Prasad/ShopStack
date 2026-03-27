'use strict';

// Redirect to dashboard if already authenticated
if (getAccessToken()) {
    window.location.href = '/dashboard/';
}

document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('login-form');
    var submitBtn = document.getElementById('submit-btn');
    var errorMsg = document.getElementById('error-msg');
    var pwdInput = document.getElementById('password');
    var pwdToggle = document.getElementById('pwd-toggle');

    // Password visibility toggle
    pwdToggle.addEventListener('click', function () {
        if (pwdInput.type === 'password') {
            pwdInput.type = 'text';
            pwdToggle.textContent = 'visibility_off';
        } else {
            pwdInput.type = 'password';
            pwdToggle.textContent = 'visibility';
        }
    });

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.style.display = 'block';
    }

    function hideError() {
        errorMsg.textContent = '';
        errorMsg.style.display = 'none';
    }

    function setLoading(loading) {
        submitBtn.disabled = loading;
        submitBtn.textContent = loading ? 'Signing in…' : 'Sign In';
    }

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        hideError();

        var username = document.getElementById('username').value.trim();
        var password = pwdInput.value;

        if (!username || !password) {
            showError('Please enter your username and password.');
            return;
        }

        setLoading(true);
        try {
            var resp = await fetch('/api/auth/login/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username, password: password }),
            });

            if (resp.ok) {
                var data = await resp.json();
                setTokens(data.access, data.refresh);
                window.location.href = '/dashboard/';
                return;
            }

            if (resp.status === 401 || resp.status === 400) {
                showError('Invalid username or password.');
            } else if (resp.status === 429) {
                showError('Too many attempts. Please wait a minute and try again.');
            } else {
                showError('Something went wrong. Please try again.');
            }
        } catch (_) {
            M.toast({ html: 'Connection error. Please try again.', classes: 'red' });
        } finally {
            setLoading(false);
        }
    });
});
