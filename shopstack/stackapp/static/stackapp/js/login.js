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

    // -----------------------------------------------------------------------
    // Forgot Password multi-step flow
    // -----------------------------------------------------------------------

    var fpLink      = document.getElementById('fp-link');
    var fpPanel     = document.getElementById('fp-panel');
    var fpStep1     = document.getElementById('fp-step-1');
    var fpStep2     = document.getElementById('fp-step-2');
    var fpBackLogin = document.getElementById('fp-back-login');
    var fpBackStep1 = document.getElementById('fp-back-step1');
    var fpSendBtn   = document.getElementById('fp-send-btn');
    var fpVerifyBtn = document.getElementById('fp-verify-btn');
    var step1Error  = document.getElementById('fp-step1-error');
    var step2Error  = document.getElementById('fp-step2-error');
    var fpEmailStored = '';

    function showFpStep(n) {
        form.style.display = 'none';
        fpLink.style.display = 'none';
        fpPanel.style.display = 'block';
        fpStep1.style.display = 'none';
        fpStep2.style.display = 'none';
        if (n === 1) { fpStep1.style.display = 'block'; }
        if (n === 2) { fpStep2.style.display = 'block'; }
    }

    function showLoginForm() {
        fpPanel.style.display = 'none';
        form.style.display = 'block';
        fpLink.style.display = 'inline-block';
        step1Error.style.display = 'none';
        step2Error.style.display = 'none';
        document.getElementById('fp-email').value = '';
        document.getElementById('fp-otp').value = '';
        M.updateTextFields();
    }

    fpLink.addEventListener('click', function () {
        showFpStep(1);
        M.updateTextFields();
    });

    fpBackLogin.addEventListener('click', showLoginForm);

    fpBackStep1.addEventListener('click', function () {
        showFpStep(1);
        M.updateTextFields();
    });

    fpSendBtn.addEventListener('click', async function () {
        step1Error.style.display = 'none';
        var email = document.getElementById('fp-email').value.trim();
        if (!email) {
            step1Error.textContent = 'Please enter your email address.';
            step1Error.style.display = 'block';
            return;
        }
        fpSendBtn.disabled = true;
        fpSendBtn.textContent = 'Sending\u2026';
        try {
            var resp = await fetch('/api/auth/forgot-password/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email }),
            });
            if (resp.ok) {
                fpEmailStored = email;
                showFpStep(2);
                M.updateTextFields();
            } else if (resp.status === 429) {
                step1Error.textContent = 'Too many attempts. Please wait and try again.';
                step1Error.style.display = 'block';
            } else {
                step1Error.textContent = 'Something went wrong. Please try again.';
                step1Error.style.display = 'block';
            }
        } catch (_) {
            M.toast({ html: 'Connection error. Please try again.', classes: 'red' });
        } finally {
            fpSendBtn.disabled = false;
            fpSendBtn.textContent = 'Send OTP';
        }
    });

    fpVerifyBtn.addEventListener('click', async function () {
        step2Error.style.display = 'none';
        var otp = document.getElementById('fp-otp').value.trim();
        if (!otp || otp.length !== 6) {
            step2Error.textContent = 'Please enter the 6-digit OTP.';
            step2Error.style.display = 'block';
            return;
        }
        fpVerifyBtn.disabled = true;
        fpVerifyBtn.textContent = 'Verifying\u2026';
        try {
            var resp = await fetch('/api/auth/forgot-password/verify/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: fpEmailStored, otp: otp }),
            });
            var data = await resp.json();
            if (resp.ok) {
                window.location.href = '/reset-password/?token=' + data.reset_token;
            } else if (resp.status === 429) {
                step2Error.textContent = 'Too many attempts. Please wait and try again.';
                step2Error.style.display = 'block';
            } else {
                step2Error.textContent = data.detail || 'Invalid OTP. Please try again.';
                step2Error.style.display = 'block';
            }
        } catch (_) {
            M.toast({ html: 'Connection error. Please try again.', classes: 'red' });
        } finally {
            fpVerifyBtn.disabled = false;
            fpVerifyBtn.textContent = 'Verify OTP';
        }
    });
});
