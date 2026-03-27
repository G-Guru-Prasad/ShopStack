'use strict';

// Redirect to login if no token
requireAuth();

// ---------------------------------------------------------------------------
// Load profile info
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    // Load profile data
    authFetch('/api/auth/me/').then(function (resp) {
        document.getElementById('profile-preloader').style.display = 'none';

        if (!resp.ok) {
            M.toast({ html: 'Failed to load profile.', classes: 'red' });
            return;
        }

        return resp.json().then(function (data) {
            document.getElementById('profile-dl').style.display = 'block';
            document.getElementById('profile-username').textContent = data.username || '—';
            document.getElementById('profile-email').textContent = data.email || '—';
            document.getElementById('profile-first-name').textContent = data.first_name || '—';
            document.getElementById('profile-last-name').textContent = data.last_name || '—';
        });
    }).catch(function () {
        M.toast({ html: 'Connection error. Please refresh.', classes: 'red' });
    });

    // ---------------------------------------------------------------------------
    // Password visibility toggles
    // ---------------------------------------------------------------------------

    document.querySelectorAll('.pwd-toggle').forEach(function (icon) {
        icon.addEventListener('click', function () {
            var targetId = icon.getAttribute('data-target');
            var input = document.getElementById(targetId);
            if (input.type === 'password') {
                input.type = 'text';
                icon.textContent = 'visibility_off';
            } else {
                input.type = 'password';
                icon.textContent = 'visibility';
            }
        });
    });

    // ---------------------------------------------------------------------------
    // Change password form
    // ---------------------------------------------------------------------------

    var form = document.getElementById('change-password-form');
    var submitBtn = document.getElementById('change-pwd-btn');

    function clearFieldError(fieldId) {
        var el = document.getElementById(fieldId + '-error');
        if (el) { el.textContent = ''; }
    }

    function setFieldError(fieldId, msg) {
        var el = document.getElementById(fieldId + '-error');
        if (el) { el.textContent = msg; }
    }

    function clearAllErrors() {
        ['current-password', 'new-password', 'confirm-password'].forEach(clearFieldError);
    }

    function clearPasswordFields() {
        document.getElementById('current-password').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
        // Reset Materialize floating labels
        M.updateTextFields();
    }

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        clearAllErrors();

        var currentPwd = document.getElementById('current-password').value;
        var newPwd = document.getElementById('new-password').value;
        var confirmPwd = document.getElementById('confirm-password').value;

        // Client-side validation
        if (!currentPwd) {
            setFieldError('current-password', 'Current password is required.');
            document.getElementById('current-password').focus();
            return;
        }
        if (!newPwd) {
            setFieldError('new-password', 'New password is required.');
            document.getElementById('new-password').focus();
            return;
        }
        if (newPwd !== confirmPwd) {
            setFieldError('confirm-password', 'Passwords do not match.');
            document.getElementById('confirm-password').focus();
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving…';

        try {
            var resp = await authFetch('/api/auth/change-password/', {
                method: 'POST',
                body: JSON.stringify({
                    current_password: currentPwd,
                    new_password: newPwd,
                    new_password_confirm: confirmPwd,
                }),
            });

            if (resp.ok) {
                clearPasswordFields();
                M.toast({ html: 'Password changed successfully.', classes: 'green' });
                return;
            }

            if (resp.status === 401) {
                window.location.href = '/login/';
                return;
            }

            if (resp.status === 400) {
                var data = await resp.json();
                // Map API field errors to helper text spans
                var fieldMap = {
                    current_password: 'current-password',
                    new_password: 'new-password',
                };
                var handled = false;
                Object.keys(fieldMap).forEach(function (apiField) {
                    if (data[apiField]) {
                        var msgs = Array.isArray(data[apiField]) ? data[apiField] : [data[apiField]];
                        setFieldError(fieldMap[apiField], msgs[0]);
                        handled = true;
                    }
                });
                if (!handled) {
                    M.toast({ html: 'Failed to change password. Please try again.', classes: 'red' });
                }
                return;
            }

            M.toast({ html: 'Something went wrong. Please try again.', classes: 'red' });
        } catch (_) {
            M.toast({ html: 'Connection error. Please try again.', classes: 'red' });
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Change Password';
        }
    });
});
