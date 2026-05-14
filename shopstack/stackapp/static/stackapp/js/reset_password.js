'use strict';

document.addEventListener('DOMContentLoaded', function () {
    var params = new URLSearchParams(window.location.search);
    var resetToken = params.get('token');

    var formPanel   = document.getElementById('form-panel');
    var successPanel = document.getElementById('success-panel');
    var submitBtn   = document.getElementById('submit-btn');
    var errorMsg    = document.getElementById('error-msg');
    var pwdInput    = document.getElementById('new-password');
    var pwdToggle   = document.getElementById('pwd-toggle');

    if (!resetToken) {
        errorMsg.textContent = 'Invalid or expired reset link. Please start the forgot password process again.';
        errorMsg.style.display = 'block';
        submitBtn.disabled = true;
        return;
    }

    pwdToggle.addEventListener('click', function () {
        if (pwdInput.type === 'password') {
            pwdInput.type = 'text';
            pwdToggle.textContent = 'visibility_off';
        } else {
            pwdInput.type = 'password';
            pwdToggle.textContent = 'visibility';
        }
    });

    submitBtn.addEventListener('click', async function () {
        errorMsg.style.display = 'none';

        var newPassword     = pwdInput.value;
        var confirmPassword = document.getElementById('confirm-password').value;

        if (!newPassword || !confirmPassword) {
            errorMsg.textContent = 'Please fill in both password fields.';
            errorMsg.style.display = 'block';
            return;
        }

        if (newPassword !== confirmPassword) {
            errorMsg.textContent = 'Passwords do not match.';
            errorMsg.style.display = 'block';
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving\u2026';

        try {
            var resp = await fetch('/api/auth/forgot-password/confirm/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    reset_token: resetToken,
                    new_password: newPassword,
                    new_password_confirm: confirmPassword,
                }),
            });

            if (resp.ok) {
                formPanel.style.display = 'none';
                successPanel.style.display = 'block';
                return;
            }

            var data = await resp.json();
            if (resp.status === 429) {
                errorMsg.textContent = 'Too many attempts. Please wait and try again.';
            } else {
                errorMsg.textContent = data.detail || 'Something went wrong. Please try again.';
            }
            errorMsg.style.display = 'block';
        } catch (_) {
            M.toast({ html: 'Connection error. Please try again.', classes: 'red' });
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Set Password';
        }
    });
});
