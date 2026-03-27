'use strict';

// Redirect to login if no token
requireAuth();

// Decode JWT payload (base64url → JSON) and display username
(function () {
    var token = getAccessToken();
    if (!token) { return; }
    try {
        var payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        var el = document.getElementById('username-display');
        if (el && payload.username) {
            el.textContent = payload.username;
        }
    } catch (_) {}
}());

// Status chip colour map
var STATUS_COLOURS = {
    PENDING: 'orange',
    CONFIRMED: 'blue',
    SHIPPED: 'cyan',
    DELIVERED: 'green',
    CANCELLED: 'red',
};

function renderOrders(orders) {
    var preloader = document.getElementById('orders-preloader');
    var tableWrap = document.getElementById('orders-table-wrap');
    var tbody = document.getElementById('orders-tbody');

    preloader.style.display = 'none';
    tableWrap.style.display = 'block';

    if (!orders || orders.length === 0) {
        var emptyRow = document.createElement('tr');
        var emptyCell = document.createElement('td');
        emptyCell.setAttribute('colspan', '4');
        emptyCell.className = 'center-align grey-text';
        emptyCell.textContent = 'No orders yet.';
        emptyRow.appendChild(emptyCell);
        tbody.appendChild(emptyRow);
        return;
    }

    // Most recent first (orders API returns oldest first by default)
    var sorted = orders.slice().sort(function (a, b) {
        return new Date(b.created_at) - new Date(a.created_at);
    });

    sorted.forEach(function (order) {
        var tr = document.createElement('tr');

        // # (id)
        var tdId = document.createElement('td');
        tdId.textContent = order.id;
        tr.appendChild(tdId);

        // Status chip
        var tdStatus = document.createElement('td');
        var chip = document.createElement('span');
        chip.className = 'chip white-text ' + (STATUS_COLOURS[order.status] || 'grey');
        chip.textContent = order.status;
        tdStatus.appendChild(chip);
        tr.appendChild(tdStatus);

        // Total
        var tdTotal = document.createElement('td');
        tdTotal.textContent = '$' + parseFloat(order.total_amount).toFixed(2);
        tr.appendChild(tdTotal);

        // Date
        var tdDate = document.createElement('td');
        tdDate.textContent = new Date(order.created_at).toLocaleDateString();
        tr.appendChild(tdDate);

        tbody.appendChild(tr);
    });
}

function renderCart(cart) {
    var preloader = document.getElementById('cart-preloader');
    var cartContent = document.getElementById('cart-content');
    var summary = document.getElementById('cart-summary');

    preloader.style.display = 'none';
    cartContent.style.display = 'block';

    if (!cart || !cart.items || cart.items.length === 0) {
        summary.className = 'grey-text';
        summary.textContent = 'Your cart is empty.';
    } else {
        summary.textContent = cart.items.length + ' item(s) in your cart.';
    }
}

// Parallel fetch of orders + cart
document.addEventListener('DOMContentLoaded', function () {
    Promise.all([
        authFetch('/api/orders/'),
        authFetch('/api/cart/'),
    ]).then(function (responses) {
        var ordersResp = responses[0];
        var cartResp = responses[1];

        var promises = [];

        if (ordersResp.ok) {
            promises.push(ordersResp.json().then(function (data) {
                renderOrders(data.results !== undefined ? data.results : data);
            }));
        } else {
            document.getElementById('orders-preloader').style.display = 'none';
            document.getElementById('orders-table-wrap').style.display = 'block';
            M.toast({ html: 'Failed to load orders.', classes: 'red' });
        }

        if (cartResp.ok) {
            promises.push(cartResp.json().then(function (data) {
                renderCart(data);
            }));
        } else {
            document.getElementById('cart-preloader').style.display = 'none';
            document.getElementById('cart-content').style.display = 'block';
            M.toast({ html: 'Failed to load cart.', classes: 'red' });
        }

        return Promise.all(promises);
    }).catch(function () {
        M.toast({ html: 'Failed to load data. Please refresh.', classes: 'red' });
    });
});
