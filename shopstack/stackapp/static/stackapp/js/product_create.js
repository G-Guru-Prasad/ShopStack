'use strict';

requireAuth();

var variantCounter = 0;
var categories = [];

document.addEventListener('DOMContentLoaded', function () {
    loadCategories();

    document.getElementById('category-select').addEventListener('change', toggleNewCategoryFields);
    document.getElementById('add-variant-btn').addEventListener('click', addVariantRow);
    document.getElementById('product-form').addEventListener('submit', handleSubmit);
});

// ---------------------------------------------------------------------------
// Load categories
// ---------------------------------------------------------------------------

function loadCategories() {
    authFetch('/api/categories/')
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            var items = data.results || data;
            categories = items;
            populateCategorySelects(items);
        })
        .catch(function () {
            M.toast({ html: 'Failed to load categories', classes: 'red' });
        });
}

function populateCategorySelects(items) {
    var mainSelect = document.getElementById('category-select');
    var parentSelect = document.getElementById('new-cat-parent');

    // Clear existing options except defaults
    mainSelect.innerHTML = '<option value="" disabled selected>Select category</option>' +
        '<option value="__new__">+ Create New Category</option>';
    parentSelect.innerHTML = '<option value="" selected>None (top-level)</option>';

    items.forEach(function (cat) {
        var opt1 = document.createElement('option');
        opt1.value = cat.id;
        opt1.textContent = cat.name;
        mainSelect.appendChild(opt1);

        var opt2 = document.createElement('option');
        opt2.value = cat.id;
        opt2.textContent = cat.name;
        parentSelect.appendChild(opt2);
    });

    M.FormSelect.init(mainSelect);
    M.FormSelect.init(parentSelect);
}

// ---------------------------------------------------------------------------
// Toggle new category fields
// ---------------------------------------------------------------------------

function toggleNewCategoryFields() {
    var val = document.getElementById('category-select').value;
    var fields = document.getElementById('new-category-fields');
    fields.style.display = val === '__new__' ? 'block' : 'none';
}

// ---------------------------------------------------------------------------
// Variant rows
// ---------------------------------------------------------------------------

function addVariantRow() {
    variantCounter++;
    var id = variantCounter;

    var row = document.createElement('div');
    row.className = 'row variant-row';
    row.id = 'variant-row-' + id;
    row.innerHTML =
        '<div class="input-field col s3">' +
        '  <input id="var-name-' + id + '" type="text" placeholder="Variant name">' +
        '  <label for="var-name-' + id + '" class="active">Name *</label>' +
        '</div>' +
        '<div class="input-field col s3">' +
        '  <input id="var-sku-' + id + '" type="text" placeholder="SKU code">' +
        '  <label for="var-sku-' + id + '" class="active">SKU *</label>' +
        '</div>' +
        '<div class="input-field col s2">' +
        '  <input id="var-price-' + id + '" type="number" step="0.01" value="0" placeholder="0.00">' +
        '  <label for="var-price-' + id + '" class="active">Price Modifier</label>' +
        '</div>' +
        '<div class="input-field col s2">' +
        '  <input id="var-stock-' + id + '" type="number" min="0" value="0" placeholder="0">' +
        '  <label for="var-stock-' + id + '" class="active">Stock Qty</label>' +
        '</div>' +
        '<div class="col s2" style="padding-top:20px;">' +
        '  <a class="btn-flat red-text waves-effect remove-variant-btn" data-id="' + id + '">' +
        '    <i class="material-icons">delete</i>' +
        '  </a>' +
        '</div>';

    document.getElementById('variants-container').appendChild(row);

    row.querySelector('.remove-variant-btn').addEventListener('click', function () {
        row.remove();
    });
}

// ---------------------------------------------------------------------------
// Collect variant data
// ---------------------------------------------------------------------------

function collectVariants() {
    var rows = document.querySelectorAll('.variant-row');
    var variants = [];
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var id = row.id.replace('variant-row-', '');
        var name = document.getElementById('var-name-' + id).value.trim();
        var sku = document.getElementById('var-sku-' + id).value.trim();
        var priceMod = document.getElementById('var-price-' + id).value;
        var stock = document.getElementById('var-stock-' + id).value;

        if (!name || !sku) {
            M.toast({ html: 'Variant name and SKU are required', classes: 'red' });
            return null;
        }
        variants.push({
            name: name,
            sku: sku,
            price_modifier: priceMod || '0',
            stock_qty: parseInt(stock) || 0,
        });
    }
    return variants;
}

// ---------------------------------------------------------------------------
// Form submission
// ---------------------------------------------------------------------------

async function handleSubmit(e) {
    e.preventDefault();
    clearErrors();

    var productName = document.getElementById('product-name').value.trim();
    var productPrice = document.getElementById('product-price').value;
    var productDesc = document.getElementById('product-description').value.trim();
    var isActive = document.getElementById('product-active').checked;
    var categoryVal = document.getElementById('category-select').value;

    // Client-side validation
    var hasError = false;
    if (!productName) {
        document.getElementById('product-name-error').textContent = 'Product name is required';
        hasError = true;
    }
    if (!productPrice || parseFloat(productPrice) < 0) {
        document.getElementById('product-price-error').textContent = 'Valid price is required';
        hasError = true;
    }
    if (hasError) return;

    var variants = collectVariants();
    if (variants === null) return;

    var submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="material-icons left">hourglass_empty</i>Creating...';

    try {
        // Step 1: Create category if new
        var categoryId = null;
        if (categoryVal === '__new__') {
            var catName = document.getElementById('new-cat-name').value.trim();
            if (!catName) {
                document.getElementById('new-cat-name-error').textContent = 'Category name is required';
                resetSubmitBtn();
                return;
            }
            var catPayload = { name: catName };
            var catDesc = document.getElementById('new-cat-description').value.trim();
            if (catDesc) catPayload.description = catDesc;
            var catParent = document.getElementById('new-cat-parent').value;
            if (catParent) catPayload.parent = parseInt(catParent);

            var catResp = await authFetch('/api/categories/', {
                method: 'POST',
                body: JSON.stringify(catPayload),
            });
            if (!catResp.ok) {
                var catErr = await catResp.json();
                M.toast({ html: 'Category error: ' + formatErrors(catErr), classes: 'red' });
                resetSubmitBtn();
                return;
            }
            var catData = await catResp.json();
            categoryId = catData.id;
        } else if (categoryVal) {
            categoryId = parseInt(categoryVal);
        }

        // Step 2: Create product
        var productPayload = {
            name: productName,
            description: productDesc,
            price: productPrice,
            is_active: isActive,
        };
        if (categoryId) productPayload.category = categoryId;

        var prodResp = await authFetch('/api/products/', {
            method: 'POST',
            body: JSON.stringify(productPayload),
        });
        if (!prodResp.ok) {
            var prodErr = await prodResp.json();
            M.toast({ html: 'Product error: ' + formatErrors(prodErr), classes: 'red' });
            resetSubmitBtn();
            return;
        }
        var prodData = await prodResp.json();
        var productId = prodData.id;

        // Step 3: Create variants
        for (var i = 0; i < variants.length; i++) {
            var varResp = await authFetch('/api/products/' + productId + '/variants/', {
                method: 'POST',
                body: JSON.stringify(variants[i]),
            });
            if (!varResp.ok) {
                var varErr = await varResp.json();
                M.toast({ html: 'Variant error: ' + formatErrors(varErr), classes: 'red' });
                resetSubmitBtn();
                return;
            }
        }

        M.toast({ html: 'Product created successfully!', classes: 'green' });
        setTimeout(function () {
            window.location.href = '/products/';
        }, 800);

    } catch (err) {
        M.toast({ html: 'An unexpected error occurred', classes: 'red' });
        resetSubmitBtn();
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clearErrors() {
    var errors = document.querySelectorAll('.helper-text.red-text');
    for (var i = 0; i < errors.length; i++) {
        errors[i].textContent = '';
    }
}

function resetSubmitBtn() {
    var btn = document.getElementById('submit-btn');
    btn.disabled = false;
    btn.innerHTML = '<i class="material-icons left">save</i>Create Product';
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
