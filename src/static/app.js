// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/**
 * Fetch JSON from an API endpoint. Throws on non-OK responses.
 */
async function getJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

/**
 * Format cents as a dollar string, e.g. 6999 → "$69.99"
 */
function formatPrice(cents) {
  return "$" + (cents / 100).toFixed(2);
}

/**
 * Format an ISO date string into a readable form.
 */
function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Show a toast notification at the bottom-right of the screen.
 */
function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = "toast " + type;
  // Force reflow for re-triggering animation
  void toast.offsetWidth;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.add("hidden");
  }, 2500);
}

/**
 * Escape HTML to prevent XSS when inserting user-visible text.
 */
function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Return a stock label object { text, className } based on quantity.
 */
function stockInfo(stock) {
  if (stock <= 0) return { text: "Out of stock", cls: "out" };
  if (stock <= 5) return { text: `Only ${stock} left`, cls: "low" };
  return { text: "In stock", cls: "" };
}


// ---------------------------------------------------------------------------
// Cart badge (shown in navbar on every page)
// ---------------------------------------------------------------------------

async function refreshCartBadge() {
  try {
    const cart = await getJSON("/api/cart");
    const el = document.getElementById("cartCount");
    if (el) {
      el.textContent = cart.count;
      el.style.display = cart.count > 0 ? "" : "none";
    }
  } catch (_) {
    // Silently ignore — badge is non-critical
  }
}


// ---------------------------------------------------------------------------
// Products page  (index.html)
// ---------------------------------------------------------------------------

let currentCategory = null; // null = "All"
let currentPage = 1;
let totalProducts = 0;
const PRODUCTS_PER_PAGE = 12;

/**
 * Render an array of product cards as HTML.
 */
function renderProductCards(items) {
  return items
    .map((p) => {
      const si = stockInfo(p.stock);
      return `
      <div class="card">
        <a href="/product/${p.id}">
          <img class="card-img" src="${escapeHTML(p.image_url || "https://picsum.photos/seed/placeholder/400/300")}" alt="${escapeHTML(p.name)}" loading="lazy">
        </a>
        <div class="card-body">
          <div class="card-category">${escapeHTML(p.category || "")}</div>
          <h3 class="card-title"><a href="/product/${p.id}">${escapeHTML(p.name)}</a></h3>
          <p class="card-desc">${escapeHTML(p.description || "")}</p>
          <div class="card-footer">
            <div>
              <span class="card-price">${formatPrice(p.price_cents)}</span>
              <div class="stock-label ${si.cls}">${si.text}</div>
            </div>
            <button class="btn btn-primary btn-sm" data-add="${p.id}" ${p.stock <= 0 ? "disabled" : ""}>
              ${p.stock <= 0 ? "Sold Out" : "Add to Cart"}
            </button>
          </div>
        </div>
      </div>`;
    })
    .join("");
}

/**
 * Update the visibility of the "Load more" button.
 */
function updateLoadMoreBtn() {
  const btn = document.getElementById("loadMoreBtn");
  if (!btn) return;
  const loaded = currentPage * PRODUCTS_PER_PAGE;
  btn.style.display = loaded < totalProducts ? "" : "none";
}

/**
 * Load the first page of products (resets the grid).
 */
async function loadProducts(category) {
  const grid = document.getElementById("productGrid");
  const loading = document.getElementById("loading");
  if (!grid) return;

  currentCategory = category || null;
  currentPage = 1;

  try {
    const url = currentCategory
      ? `/api/products?category=${encodeURIComponent(currentCategory)}&page=1&limit=${PRODUCTS_PER_PAGE}`
      : `/api/products?page=1&limit=${PRODUCTS_PER_PAGE}`;
    const data = await getJSON(url);

    totalProducts = data.total;

    // Render category filter buttons
    renderCategoryFilter(data.categories);

    // Hide loading spinner
    if (loading) loading.classList.add("hidden");

    // Render product cards
    if (data.items.length === 0) {
      grid.innerHTML = `<p class="text-center" style="grid-column:1/-1;color:var(--gray-500);">No products found.</p>`;
      updateLoadMoreBtn();
      return;
    }

    grid.innerHTML = renderProductCards(data.items);
    updateLoadMoreBtn();
  } catch (err) {
    if (loading) loading.classList.add("hidden");
    grid.innerHTML = `<p class="text-center" style="grid-column:1/-1;color:var(--danger);">Failed to load products.</p>`;
  }
}

/**
 * Load the next page and append products to the grid.
 */
async function loadMoreProducts() {
  const grid = document.getElementById("productGrid");
  const btn = document.getElementById("loadMoreBtn");
  if (!grid || !btn) return;

  currentPage++;
  btn.disabled = true;
  btn.textContent = "Loading...";

  try {
    let url = `/api/products?page=${currentPage}&limit=${PRODUCTS_PER_PAGE}`;
    if (currentCategory) {
      url += `&category=${encodeURIComponent(currentCategory)}`;
    }
    const data = await getJSON(url);
    totalProducts = data.total;

    // Append new cards to the grid
    grid.insertAdjacentHTML("beforeend", renderProductCards(data.items));
    updateLoadMoreBtn();
  } catch (err) {
    showToast("Failed to load more products", "error");
    currentPage--; // revert so user can retry
  } finally {
    btn.disabled = false;
    btn.textContent = "Load more...";
  }
}

function renderCategoryFilter(categories) {
  const container = document.getElementById("categoryFilter");
  if (!container || !categories) return;

  const allActive = !currentCategory ? "active" : "";
  let html = `<button class="filter-btn ${allActive}" data-category="">All</button>`;
  categories.forEach((cat) => {
    const active = currentCategory === cat ? "active" : "";
    html += `<button class="filter-btn ${active}" data-category="${escapeHTML(cat)}">${escapeHTML(cat)}</button>`;
  });
  container.innerHTML = html;
}

function setupProductGrid() {
  const grid = document.getElementById("productGrid");
  if (!grid) return;

  // Add-to-cart click (event delegation)
  grid.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-add]");
    if (!btn || btn.disabled) return;

    const productId = parseInt(btn.getAttribute("data-add"), 10);
    btn.disabled = true;
    btn.textContent = "Adding...";

    try {
      await getJSON("/api/cart/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: productId, quantity: 1 }),
      });
      showToast("Added to cart!");
      await refreshCartBadge();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Add to Cart";
    }
  });

  // Category filter click
  const filterContainer = document.getElementById("categoryFilter");
  if (filterContainer) {
    filterContainer.addEventListener("click", (e) => {
      const btn = e.target.closest(".filter-btn");
      if (!btn) return;
      const category = btn.getAttribute("data-category");
      loadProducts(category || null);
    });
  }

  // Load more button click
  const loadMoreBtn = document.getElementById("loadMoreBtn");
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", loadMoreProducts);
  }
}


// ---------------------------------------------------------------------------
// Product Detail page  (product.html)
// ---------------------------------------------------------------------------

async function loadProductDetail() {
  const container = document.getElementById("productDetail");
  if (!container) return;

  const productId = container.getAttribute("data-product-id");
  if (!productId) return;

  try {
    const p = await getJSON(`/api/products/${productId}`);
    const si = stockInfo(p.stock);

    let stockClass = "in-stock";
    if (p.stock <= 0) stockClass = "out-of-stock";
    else if (p.stock <= 5) stockClass = "low-stock";

    container.innerHTML = `
      <img class="product-detail-img" src="${escapeHTML(p.image_url || "https://picsum.photos/seed/placeholder/400/300")}" alt="${escapeHTML(p.name)}">
      <div class="product-detail-info">
        <div class="product-detail-category">${escapeHTML(p.category || "")}</div>
        <h2>${escapeHTML(p.name)}</h2>
        <div class="product-detail-price">${formatPrice(p.price_cents)}</div>
        <p class="product-detail-desc">${escapeHTML(p.description || "")}</p>
        <div class="product-detail-stock ${stockClass}">${si.text}</div>
        ${p.stock > 0 ? `
        <div class="qty-selector">
          <label for="detailQty">Quantity:</label>
          <input id="detailQty" class="qty-input" type="number" min="1" max="${p.stock}" value="1">
        </div>
        <button id="detailAddBtn" class="btn btn-primary btn-lg">Add to Cart</button>
        ` : `<button class="btn btn-primary btn-lg" disabled>Out of Stock</button>`}
        <p id="detailMsg" class="mt-1" style="font-size:0.9rem;"></p>
      </div>
    `;

    // Wire up add-to-cart on detail page
    const addBtn = document.getElementById("detailAddBtn");
    if (addBtn) {
      addBtn.addEventListener("click", async () => {
        const qty = parseInt(document.getElementById("detailQty").value, 10) || 1;
        addBtn.disabled = true;
        addBtn.textContent = "Adding...";
        try {
          await getJSON("/api/cart/items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_id: parseInt(productId, 10), quantity: qty }),
          });
          showToast(`Added ${qty} item(s) to cart!`);
          await refreshCartBadge();
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          addBtn.disabled = false;
          addBtn.textContent = "Add to Cart";
        }
      });
    }
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger);">Product not found.</p>`;
  }
}


// ---------------------------------------------------------------------------
// Cart page  (cart.html)
// ---------------------------------------------------------------------------

async function loadCart() {
  const box = document.getElementById("cartBox");
  const summary = document.getElementById("cartSummary");
  if (!box) return;

  try {
    const cart = await getJSON("/api/cart");

    if (cart.items.length === 0) {
      box.innerHTML = `
        <div class="cart-empty">
          <div class="cart-empty-icon">&#128722;</div>
          <p>Your cart is empty.</p>
          <a href="/" class="btn btn-primary mt-2">Continue Shopping</a>
        </div>`;
      if (summary) summary.classList.add("hidden");
      return;
    }

    // Render cart items
    box.innerHTML = cart.items
      .map((i) => {
        const subtotal = i.quantity * i.price_cents;
        return `
        <div class="cart-item">
          <img class="cart-item-img" src="${escapeHTML(i.image_url || "https://picsum.photos/seed/placeholder/400/300")}" alt="${escapeHTML(i.name)}">
          <div class="cart-item-info">
            <div class="cart-item-name">${escapeHTML(i.name)}</div>
            <div class="cart-item-price">${formatPrice(i.price_cents)} each</div>
          </div>
          <div class="cart-item-actions">
            <div class="cart-qty-group">
              <button class="cart-qty-btn" data-dec="${i.product_id}">&minus;</button>
              <span class="cart-qty-value">${i.quantity}</span>
              <button class="cart-qty-btn" data-inc="${i.product_id}" ${i.quantity >= i.stock ? "disabled" : ""}>&plus;</button>
            </div>
            <span class="cart-item-subtotal">${formatPrice(subtotal)}</span>
            <button class="btn btn-danger btn-sm" data-remove="${i.product_id}">Remove</button>
          </div>
        </div>`;
      })
      .join("");

    // Show summary
    if (summary) {
      summary.classList.remove("hidden");
      document.getElementById("cartSubtotal").textContent = formatPrice(cart.total_cents);
      document.getElementById("cartTotal").textContent = formatPrice(cart.total_cents);
    }
  } catch (err) {
    box.innerHTML = `<p style="color:var(--danger);">Failed to load cart.</p>`;
  }
}

function setupCartEvents() {
  const box = document.getElementById("cartBox");
  if (!box) return;

  box.addEventListener("click", async (e) => {
    // Increment
    const incBtn = e.target.closest("button[data-inc]");
    if (incBtn && !incBtn.disabled) {
      const pid = parseInt(incBtn.getAttribute("data-inc"), 10);
      const qtyEl = incBtn.parentElement.querySelector(".cart-qty-value");
      const newQty = parseInt(qtyEl.textContent, 10) + 1;
      try {
        await getJSON(`/api/cart/items/${pid}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ quantity: newQty }),
        });
        await loadCart();
        await refreshCartBadge();
      } catch (err) {
        showToast(err.message, "error");
      }
      return;
    }

    // Decrement
    const decBtn = e.target.closest("button[data-dec]");
    if (decBtn) {
      const pid = parseInt(decBtn.getAttribute("data-dec"), 10);
      const qtyEl = decBtn.parentElement.querySelector(".cart-qty-value");
      const currentQty = parseInt(qtyEl.textContent, 10);
      if (currentQty <= 1) {
        // Remove item if quantity would go below 1
        try {
          await getJSON(`/api/cart/items/${pid}`, { method: "DELETE" });
          showToast("Item removed");
          await loadCart();
          await refreshCartBadge();
        } catch (err) {
          showToast(err.message, "error");
        }
      } else {
        try {
          await getJSON(`/api/cart/items/${pid}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: currentQty - 1 }),
          });
          await loadCart();
          await refreshCartBadge();
        } catch (err) {
          showToast(err.message, "error");
        }
      }
      return;
    }

    // Remove
    const removeBtn = e.target.closest("button[data-remove]");
    if (removeBtn) {
      const pid = parseInt(removeBtn.getAttribute("data-remove"), 10);
      try {
        await getJSON(`/api/cart/items/${pid}`, { method: "DELETE" });
        showToast("Item removed");
        await loadCart();
        await refreshCartBadge();
      } catch (err) {
        showToast(err.message, "error");
      }
    }
  });
}

function setupCheckout() {
  const btn = document.getElementById("checkoutBtn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const msg = document.getElementById("checkoutMsg");
    btn.disabled = true;
    btn.textContent = "Processing...";

    try {
      const data = await getJSON("/api/checkout", { method: "POST" });
      msg.className = "checkout-msg success";
      msg.innerHTML = `Order placed successfully! <a href="/order/${data.order_id}">View Order #${data.order_id}</a>`;
      showToast("Order placed!");
      await loadCart();
      await refreshCartBadge();
    } catch (err) {
      if (err.message.includes("log in")) {
        msg.className = "checkout-msg error";
        msg.innerHTML = 'Please <a href="/login">log in</a> to checkout.';
      } else {
        msg.className = "checkout-msg error";
        msg.textContent = err.message;
      }
      btn.disabled = false;
      btn.textContent = "Proceed to Checkout";
    }
  });
}


// ---------------------------------------------------------------------------
// Orders page  (orders.html)
// ---------------------------------------------------------------------------

async function loadOrders() {
  const container = document.getElementById("ordersList");
  if (!container) return;

  try {
    const data = await getJSON("/api/orders");

    if (data.orders.length === 0) {
      container.innerHTML = `
        <div class="orders-empty">
          <p>You have no orders yet.</p>
          <a href="/" class="btn btn-primary mt-2">Start Shopping</a>
        </div>`;
      return;
    }

    container.innerHTML = data.orders
      .map((o) => {
        return `
        <div class="order-card">
          <div class="order-card-header">
            <span class="order-id">Order #${o.id}</span>
            <span class="order-status ${o.status}">${escapeHTML(o.status)}</span>
            ${o.return_status ? `<span class="return-badge ${o.return_status}">${escapeHTML(o.return_status.replace("_", " "))}</span>` : ""}
          </div>
          <div class="order-card-meta">
            <span>${formatDate(o.created_at)}</span>
            <span>${o.total_items} item(s)</span>
          </div>
          <div class="order-card-footer">
            <span class="order-total">${formatPrice(o.total_cents)}</span>
            <a href="/order/${o.id}" class="btn btn-sm">View Details</a>
          </div>
        </div>`;
      })
      .join("");
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger);">Failed to load orders.</p>`;
  }
}


// ---------------------------------------------------------------------------
// Order Detail page  (order_detail.html)
// ---------------------------------------------------------------------------

async function loadOrderDetail() {
  const container = document.getElementById("orderDetail");
  if (!container) return;

  const orderId = container.getAttribute("data-order-id");
  if (!orderId) return;

  try {
    const data = await getJSON(`/api/orders/${orderId}`);
    const order = data.order;
    const items = data.items;

    container.innerHTML = `
      <div class="order-detail-header">
        <div>
          <span class="order-status ${order.status}">${escapeHTML(order.status)}</span>
        </div>
        <div class="order-detail-date">${formatDate(order.created_at)}</div>
      </div>
      <div class="order-detail-items">
        ${items
          .map((i) => {
            const subtotal = i.quantity * i.unit_price_cents;
            return `
            <div class="order-detail-item">
              <img class="order-detail-item-img" src="${escapeHTML(i.image_url || "https://picsum.photos/seed/placeholder/400/300")}" alt="${escapeHTML(i.product_name)}">
              <div class="order-detail-item-info">
                <div class="order-detail-item-name">${escapeHTML(i.product_name)}</div>
                <div class="order-detail-item-meta">${formatPrice(i.unit_price_cents)} x ${i.quantity}</div>
              </div>
              <div class="order-detail-item-subtotal">${formatPrice(subtotal)}</div>
            </div>`;
          })
          .join("")}
      </div>
      <div class="order-detail-total">
        Total: <span>${formatPrice(order.total_cents)}</span>
      </div>
      ${order.return_status
        ? `<div class="return-badge ${order.return_status}" style="margin-top:1rem;">Return status: ${escapeHTML(order.return_status.replace("_", " "))}</div>`
        : ""}
      ${order.status === "confirmed" && !order.return_status
        ? `<button id="returnBtn" class="btn btn-danger" style="margin-top:1rem;">Request Return</button>`
        : ""}
    `;

    // Wire up return button
    const returnBtn = document.getElementById("returnBtn");
    if (returnBtn) {
      returnBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to request a return for this order?")) return;
        returnBtn.disabled = true;
        returnBtn.textContent = "Requesting...";
        try {
          await getJSON(`/api/orders/${orderId}/return`, { method: "POST" });
          showToast("Return requested!");
          await loadOrderDetail();
        } catch (err) {
          showToast(err.message, "error");
          returnBtn.disabled = false;
          returnBtn.textContent = "Request Return";
        }
      });
    }
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger);">Order not found.</p>`;
  }
}


// ---------------------------------------------------------------------------
// Register page  (register.html)
// ---------------------------------------------------------------------------

function setupRegister() {
  const form = document.getElementById("registerForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("authMsg");
    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    try {
      await getJSON("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      window.location.href = "/";
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "auth-msg error";
    }
  });
}


// ---------------------------------------------------------------------------
// Login page  (login.html)
// ---------------------------------------------------------------------------

function setupLogin() {
  const form = document.getElementById("loginForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("authMsg");
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    try {
      await getJSON("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      window.location.href = "/";
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "auth-msg error";
    }
  });
}


// ---------------------------------------------------------------------------
// Profile page  (profile.html)
// ---------------------------------------------------------------------------

function setupProfile() {
  const btn = document.getElementById("deleteAccountBtn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const msg = document.getElementById("deleteMsg");
    const password = prompt("To confirm, please enter your password:");
    if (!password) return;

    if (!confirm("Are you absolutely sure? This cannot be undone.")) return;

    btn.disabled = true;
    btn.textContent = "Deleting...";

    try {
      await getJSON("/api/delete-account", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      showToast("Account deleted");
      window.location.href = "/";
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "auth-msg error";
      btn.disabled = false;
      btn.textContent = "Delete My Account";
    }
  });
}


// ---------------------------------------------------------------------------
// Initialization — runs on every page
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  // Always update the cart badge in the navbar
  await refreshCartBadge();

  // Products page
  if (document.getElementById("productGrid")) {
    await loadProducts();
    setupProductGrid();
  }

  // Product detail page
  if (document.getElementById("productDetail")) {
    await loadProductDetail();
  }

  // Cart page
  if (document.getElementById("cartBox")) {
    await loadCart();
    setupCartEvents();
    setupCheckout();
  }

  // Orders page
  if (document.getElementById("ordersList")) {
    await loadOrders();
  }

  // Order detail page
  if (document.getElementById("orderDetail")) {
    await loadOrderDetail();
  }

  // Register page
  if (document.getElementById("registerForm")) {
    setupRegister();
  }

  // Login page
  if (document.getElementById("loginForm")) {
    setupLogin();
  }

  // Profile page
  if (document.getElementById("deleteAccountBtn")) {
    setupProfile();
  }
});
