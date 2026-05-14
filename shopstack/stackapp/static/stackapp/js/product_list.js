'use strict';

requireAuth();

var allProducts = [];
var categoriesMap = {};
var editVariantCounter = 0;
var currentEditProductId = null;

document.addEventListener('DOMContentLoaded', function () {
    M.Modal.init(document.querySelectorAll('.modal'));

    document.getElementById('search-input').addEventListener('input', filterProducts);
    document.getElementById('category-filter').addEventListener('change', filterProducts);
    document.getElementById('edit-add-variant-btn').addEventListener('click', addEditVariantRow);
    document.getElementById('edit-save-btn').addEventListener('click', saveProduct);

    loadCategories();
    loadProducts();
});

// ---------------------------------------------------------------------------
// Load data
// ---------------------------------------------------------------------------

function loadCategories() {
    authFetch('/api/categories/')
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            var items = data.results || data;
            categoriesMap = {};
            items.forEach(function (cat) { categoriesMap[cat.id] = cat.name; });
            populateCategoryFilter(items);
            populateEditCategorySelect(items);
        });
}

function populateCategoryFilter(items) {
    var sel = document.getElementById('category-filter');
    sel.innerHTML = '<option value="" selected>All Categories</option>';
    items.forEach(function (cat) {
        var opt = document.createElement('option');
        opt.value = cat.id;
        opt.textContent = cat.name;
        sel.appendChild(opt);
    });
    M.FormSelect.init(sel);
}

function populateEditCategorySelect(items) {
    var sel = document.getElementById('edit-category');
    sel.innerHTML = '<option value="">No Category</option>';
    items.forEach(function (cat) {
        var opt = document.createElement('option');
        opt.value = cat.id;
        opt.textContent = cat.name;
        sel.appendChild(opt);
    });
    M.FormSelect.init(sel);
}

function loadProducts() {
    document.getElementById('products-preloader').style.display = '';
    document.getElementById('products-table-wrap').style.display = 'none';
    document.getElementById('no-products-msg').style.display = 'none';

    authFetch('/api/products/?all=true')
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            allProducts = data.results || data;
            renderProducts(allProducts);
        })
        .catch(function () {
            M.toast({ html: 'Failed to load products', classes: 'red' });
            document.getElementById('products-preloader').style.display = 'none';
        });
}

// ---------------------------------------------------------------------------
// Render table
// ---------------------------------------------------------------------------

function renderProducts(products) {
    var tbody = document.getElementById('products-tbody');
    tbody.innerHTML = '';

    document.getElementById('products-preloader').style.display = 'none';

    if (products.length === 0) {
        document.getElementById('products-table-wrap').style.display = 'none';
        document.getElementById('no-products-msg').style.display = 'block';
        return;
    }

    document.getElementById('products-table-wrap').style.display = '';
    document.getElementById('no-products-msg').style.display = 'none';

    products.forEach(function (p) {
        var tr = document.createElement('tr');
        var categoryName = p.category ? (categoriesMap[p.category] || 'ID: ' + p.category) : '—';
        var activeChip = p.is_active
            ? '<span class="new badge green" data-badge-caption="">Active</span>'
            : '<span class="new badge grey" data-badge-caption="">Inactive</span>';

        tr.innerHTML =
            '<td>' + escapeHtml(p.name) + '</td>' +
            '<td>$' + parseFloat(p.price).toFixed(2) + '</td>' +
            '<td>' + escapeHtml(categoryName) + '</td>' +
            '<td>' + activeChip + '</td>' +
            '<td><span class="badge" data-product-id="' + p.id + '">—</span></td>' +
            '<td>' +
            '  <a class="btn-small teal darken-2 waves-effect waves-light edit-btn" data-id="' + p.id + '">' +
            '    <i class="material-icons">edit</i>' +
            '  </a>' +
            '</td>';

        tbody.appendChild(tr);
    });

    // Attach edit handlers
    document.querySelectorAll('.edit-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            openEditModal(parseInt(btn.getAttribute('data-id')));
        });
    });

    // Load variant counts
    loadVariantCounts(products);
}

function loadVariantCounts(products) {
    products.forEach(function (p) {
        authFetch('/api/products/' + p.id + '/?all=true')
            .then(function (resp) { return resp.json(); })
            .then(function (detail) {
                var badge = document.querySelector('[data-product-id="' + p.id + '"]');
                if (badge) {
                    var count = detail.variants ? detail.variants.length : 0;
                    badge.textContent = count;
                }
            });
    });
}

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------

function filterProducts() {
    var search = document.getElementById('search-input').value.toLowerCase();
    var catFilter = document.getElementById('category-filter').value;

    var filtered = allProducts.filter(function (p) {
        var matchName = !search || p.name.toLowerCase().indexOf(search) !== -1;
        var matchCat = !catFilter || String(p.category) === catFilter;
        return matchName && matchCat;
    });

    renderProducts(filtered);
}

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

function openEditModal(productId) {
    currentEditProductId = productId;
    editVariantCounter = 0;

    authFetch('/api/products/' + productId + '/')
        .then(function (resp) { return resp.json(); })
        .then(function (product) {
            document.getElementById('edit-product-id').value = product.id;
            document.getElementById('edit-name').value = product.name;
            document.getElementById('edit-description').value = product.description || '';
            document.getElementById('edit-price').value = product.price;
            document.getElementById('edit-active').checked = product.is_active;

            // Set category
            var catSel = document.getElementById('edit-category');
            catSel.value = product.category || '';
            M.FormSelect.init(catSel);

            // Update labels
            M.updateTextFields();

            // Populate existing variants
            var container = document.getElementById('edit-variants-container');
            container.innerHTML = '';
            if (product.variants) {
                product.variants.forEach(function (v) {
                    addEditVariantRow(null, v);
                });
            }

            var modal = M.Modal.getInstance(document.getElementById('edit-product-modal'));
            modal.open();
        })
        .catch(function () {
            M.toast({ html: 'Failed to load product details', classes: 'red' });
        });
}

function addEditVariantRow(e, existing) {
    editVariantCounter++;
    var id = editVariantCounter;
    var variantId = existing ? existing.id : '';
    var name = existing ? existing.name : '';
    var sku = existing ? existing.sku : '';
    var priceMod = existing ? existing.price_modifier : '0';
    var stock = existing ? existing.stock_qty : 0;

    var row = document.createElement('div');
    row.className = 'row edit-variant-row';
    row.id = 'edit-variant-row-' + id;
    row.setAttribute('data-variant-id', variantId);

    row.innerHTML =
        '<div class="input-field col s3">' +
        '  <input id="ev-name-' + id + '" type="text" value="' + escapeAttr(name) + '">' +
        '  <label for="ev-name-' + id + '" class="active">Name</label>' +
        '</div>' +
        '<div class="input-field col s3">' +
        '  <input id="ev-sku-' + id + '" type="text" value="' + escapeAttr(sku) + '">' +
        '  <label for="ev-sku-' + id + '" class="active">SKU</label>' +
        '</div>' +
        '<div class="input-field col s2">' +
        '  <input id="ev-price-' + id + '" type="number" step="0.01" value="' + priceMod + '">' +
        '  <label for="ev-price-' + id + '" class="active">Price Mod</label>' +
        '</div>' +
        '<div class="input-field col s2">' +
        '  <input id="ev-stock-' + id + '" type="number" min="0" value="' + stock + '">' +
        '  <label for="ev-stock-' + id + '" class="active">Stock</label>' +
        '</div>' +
        '<div class="col s2" style="padding-top:20px;">' +
        '  <a class="btn-flat red-text waves-effect ev-remove-btn" data-row-id="' + id + '" data-variant-id="' + variantId + '">' +
        '    <i class="material-icons">delete</i>' +
        '  </a>' +
        '</div>';

    document.getElementById('edit-variants-container').appendChild(row);

    row.querySelector('.ev-remove-btn').addEventListener('click', function () {
        var vid = this.getAttribute('data-variant-id');
        if (vid) {
            // Delete existing variant via API
            authFetch('/api/products/' + currentEditProductId + '/variants/' + vid + '/', {
                method: 'DELETE',
            }).then(function (resp) {
                if (resp.ok || resp.status === 204) {
                    row.remove();
                    M.toast({ html: 'Variant deleted', classes: 'green' });
                } else {
                    M.toast({ html: 'Failed to delete variant', classes: 'red' });
                }
            });
        } else {
            row.remove();
        }
    });
}

// ---------------------------------------------------------------------------
// Save product
// ---------------------------------------------------------------------------

async function saveProduct() {
    var productId = currentEditProductId;
    var name = document.getElementById('edit-name').value.trim();
    var description = document.getElementById('edit-description').value.trim();
    var price = document.getElementById('edit-price').value;
    var isActive = document.getElementById('edit-active').checked;
    var category = document.getElementById('edit-category').value;

    if (!name) {
        M.toast({ html: 'Product name is required', classes: 'red' });
        return;
    }
    if (!price || parseFloat(price) < 0) {
        M.toast({ html: 'Valid price is required', classes: 'red' });
        return;
    }

    var saveBtn = document.getElementById('edit-save-btn');
    saveBtn.classList.add('disabled');

    try {
        // Update product
        var payload = {
            name: name,
            description: description,
            price: price,
            is_active: isActive,
            category: category ? parseInt(category) : null,
        };

        var resp = await authFetch('/api/products/' + productId + '/', {
            method: 'PATCH',
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            var err = await resp.json();
            M.toast({ html: 'Save error: ' + formatErrors(err), classes: 'red' });
            saveBtn.classList.remove('disabled');
            return;
        }

        // Save new variants (those without data-variant-id)
        var rows = document.querySelectorAll('.edit-variant-row');
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var variantId = row.getAttribute('data-variant-id');
            var rowId = row.id.replace('edit-variant-row-', '');
            var vName = document.getElementById('ev-name-' + rowId).value.trim();
            var vSku = document.getElementById('ev-sku-' + rowId).value.trim();
            var vPrice = document.getElementById('ev-price-' + rowId).value;
            var vStock = document.getElementById('ev-stock-' + rowId).value;

            if (!vName || !vSku) {
                M.toast({ html: 'Variant name and SKU are required', classes: 'red' });
                saveBtn.classList.remove('disabled');
                return;
            }

            var varPayload = {
                name: vName,
                sku: vSku,
                price_modifier: vPrice || '0',
                stock_qty: parseInt(vStock) || 0,
            };

            if (variantId) {
                // Update existing variant
                var vResp = await authFetch('/api/products/' + productId + '/variants/' + variantId + '/', {
                    method: 'PATCH',
                    body: JSON.stringify(varPayload),
                });
                if (!vResp.ok) {
                    var vErr = await vResp.json();
                    M.toast({ html: 'Variant error: ' + formatErrors(vErr), classes: 'red' });
                    saveBtn.classList.remove('disabled');
                    return;
                }
            } else {
                // Create new variant
                var cResp = await authFetch('/api/products/' + productId + '/variants/', {
                    method: 'POST',
                    body: JSON.stringify(varPayload),
                });
                if (!cResp.ok) {
                    var cErr = await cResp.json();
                    M.toast({ html: 'Variant error: ' + formatErrors(cErr), classes: 'red' });
                    saveBtn.classList.remove('disabled');
                    return;
                }
            }
        }

        M.toast({ html: 'Product updated successfully!', classes: 'green' });
        var modal = M.Modal.getInstance(document.getElementById('edit-product-modal'));
        modal.close();
        loadProducts();

    } catch (err) {
        M.toast({ html: 'An unexpected error occurred', classes: 'red' });
    }

    saveBtn.classList.remove('disabled');
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatErrors(errObj) {
    if (typeof errObj === 'string') return errObj;
    if (errObj.detail) return errObj.detail;
    var messages = [];
    for (var key in errObj) {
        if (errObj.hasOwnProperty(key)) {
            var val = Array.isArray(errObj[key]) ? errObj[key].join(', ') : errObj[key];
            messages.push(key + ': ' + val);
        }
    }
    return messages.join('; ') || 'Unknown error';
}
