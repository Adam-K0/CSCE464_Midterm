from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import get_conn
import secrets

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # For class demo only — use env var in production


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_guest_key():
    """Get or create a guest session key (stored in cookie via Flask session)."""
    if "guest_key" not in session:
        session["guest_key"] = secrets.token_hex(16)
    return session["guest_key"]


def get_or_create_cart_id(guest_key: str) -> int:
    """Return the cart id for a guest, creating one if needed."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id FROM carts WHERE guest_key = %s", (guest_key,))
    row = cur.fetchone()
    if row:
        cart_id = row["id"]
    else:
        cur.execute("INSERT INTO carts (guest_key) VALUES (%s)", (guest_key,))
        conn.commit()
        cart_id = cur.lastrowid

    cur.close()
    conn.close()
    return cart_id


def cents_to_dollars(cents):
    """Format cents as a dollar string."""
    return f"{cents / 100:.2f}"


def get_current_user():
    """Return user dict from session, or None if not logged in."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return {"id": user_id, "name": session.get("user_name"), "email": session.get("user_email")}


def login_required(f):
    """Decorator: redirect to /login if user is not logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("page_login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_user():
    """Make current_user available in all Jinja templates."""
    return {"current_user": get_current_user()}


# ---------------------------------------------------------------------------
# Page routes (server-side rendered templates)
# ---------------------------------------------------------------------------

@app.get("/")
def page_index():
    return render_template("index.html")


@app.get("/product/<int:product_id>")
def page_product(product_id):
    return render_template("product.html", product_id=product_id)


@app.get("/cart")
def page_cart():
    return render_template("cart.html")


@app.get("/register")
def page_register():
    return render_template("register.html")


@app.get("/login")
def page_login():
    return render_template("login.html")


@app.get("/profile")
@login_required
def page_profile():
    return render_template("profile.html")


@app.get("/orders")
@login_required
def page_orders():
    return render_template("orders.html")


@app.get("/order/<int:order_id>")
@login_required
def page_order_detail(order_id):
    return render_template("order_detail.html", order_id=order_id)


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.post("/api/register")
def api_register():
    """Register a new user account."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not email or not password or not name:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Check if email already registered
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Email already registered"}), 409

    # Create user
    pw_hash = generate_password_hash(password)
    cur2 = conn.cursor()
    cur2.execute(
        "INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s)",
        (email, pw_hash, name),
    )
    conn.commit()
    user_id = cur2.lastrowid

    # Auto-login after registration
    session["user_id"] = user_id
    session["user_name"] = name
    session["user_email"] = email

    cur2.close()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "user": {"id": user_id, "name": name}}), 201


@app.post("/api/login")
def api_login():
    """Log in with email and password."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, email, name, password_hash FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    return jsonify({"ok": True, "user": {"id": user["id"], "name": user["name"]}})


@app.post("/api/logout")
def api_logout():
    """Log out the current user."""
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    return jsonify({"ok": True})


@app.post("/api/delete-account")
def api_delete_account():
    """Delete the current user's account after password confirmation."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        cur.close()
        conn.close()
        return jsonify({"error": "Invalid password"}), 401

    cur2 = conn.cursor()
    cur2.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur2.close()
    cur.close()
    conn.close()

    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Products API
# ---------------------------------------------------------------------------

@app.get("/api/products")
def api_products():
    """Return a paginated list of products.

    Query params:
        category — filter by category (optional)
        page     — 1-based page number   (default 1)
        limit    — items per page         (default 12)
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    category = request.args.get("category")
    page = max(1, request.args.get("page", 1, type=int))
    limit = max(1, min(request.args.get("limit", 12, type=int), 50))
    offset = (page - 1) * limit

    if category:
        cur.execute(
            "SELECT COUNT(*) AS total FROM products WHERE category = %s",
            (category,),
        )
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT id, name, description, price_cents, image_url, stock, category "
            "FROM products WHERE category = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (category, limit, offset),
        )
    else:
        cur.execute("SELECT COUNT(*) AS total FROM products")
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT id, name, description, price_cents, image_url, stock, category "
            "FROM products ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
    rows = cur.fetchall()

    # Also fetch distinct categories for filter UI
    cur.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = [r["category"] for r in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify({
        "items": rows,
        "categories": categories,
        "page": page,
        "limit": limit,
        "total": total,
    })


@app.get("/api/products/<int:product_id>")
def api_product_detail(product_id):
    """Get a single product by id."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, name, description, price_cents, image_url, stock, category "
        "FROM products WHERE id = %s",
        (product_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(row)


# ---------------------------------------------------------------------------
# Cart API
# ---------------------------------------------------------------------------

@app.get("/api/cart")
def api_cart():
    """Return current cart items, total, and item count."""
    guest_key = get_guest_key()
    cart_id = get_or_create_cart_id(guest_key)

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT ci.product_id, ci.quantity, p.name, p.price_cents, p.image_url, p.stock
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.cart_id = %s
        ORDER BY p.name
    """, (cart_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()

    total_cents = sum(i["quantity"] * i["price_cents"] for i in items)
    count = sum(i["quantity"] for i in items)
    return jsonify({"items": items, "total_cents": total_cents, "count": count})


@app.post("/api/cart/items")
def api_cart_add():
    """Add a product to cart (or increase quantity if already present)."""
    guest_key = get_guest_key()
    cart_id = get_or_create_cart_id(guest_key)
    data = request.get_json(silent=True) or {}

    product_id = int(data.get("product_id", 0))
    qty = int(data.get("quantity", 1))

    if product_id <= 0 or qty <= 0:
        return jsonify({"error": "Invalid input"}), 400

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Check stock
    cur.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    if not product:
        cur.close()
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    # Check current cart quantity
    cur.execute(
        "SELECT quantity FROM cart_items WHERE cart_id = %s AND product_id = %s",
        (cart_id, product_id),
    )
    existing = cur.fetchone()
    current_qty = existing["quantity"] if existing else 0

    if current_qty + qty > product["stock"]:
        cur.close()
        conn.close()
        return jsonify({"error": "Not enough stock"}), 400

    # Upsert: add qty if exists, else insert
    cur2 = conn.cursor()
    cur2.execute("""
        INSERT INTO cart_items (cart_id, product_id, quantity)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
    """, (cart_id, product_id, qty))
    conn.commit()

    cur2.close()
    cur.close()
    conn.close()
    return jsonify({"ok": True}), 201


@app.patch("/api/cart/items/<int:product_id>")
def api_cart_set_qty(product_id: int):
    """Set the quantity of a cart item."""
    guest_key = get_guest_key()
    cart_id = get_or_create_cart_id(guest_key)
    data = request.get_json(silent=True) or {}
    qty = int(data.get("quantity", 1))

    if qty < 1:
        return jsonify({"error": "Quantity must be >= 1"}), 400

    # Check stock
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    if product and qty > product["stock"]:
        cur.close()
        conn.close()
        return jsonify({"error": "Not enough stock"}), 400

    cur2 = conn.cursor()
    cur2.execute("""
        UPDATE cart_items SET quantity = %s
        WHERE cart_id = %s AND product_id = %s
    """, (qty, cart_id, product_id))
    conn.commit()

    cur2.close()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.delete("/api/cart/items/<int:product_id>")
def api_cart_remove(product_id: int):
    """Remove an item from the cart."""
    guest_key = get_guest_key()
    cart_id = get_or_create_cart_id(guest_key)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cart_items WHERE cart_id = %s AND product_id = %s",
        (cart_id, product_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Checkout & Orders API
# ---------------------------------------------------------------------------

@app.post("/api/checkout")
def api_checkout():
    """Convert the current cart into an order. Requires login."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Please log in to checkout"}), 401

    guest_key = get_guest_key()
    cart_id = get_or_create_cart_id(guest_key)

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Read cart items
    cur.execute("""
        SELECT ci.product_id, ci.quantity, p.name, p.price_cents, p.stock
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.cart_id = %s
    """, (cart_id,))
    items = cur.fetchall()

    if not items:
        cur.close()
        conn.close()
        return jsonify({"error": "Cart is empty"}), 400

    # Verify stock for each item
    for item in items:
        if item["quantity"] > item["stock"]:
            cur.close()
            conn.close()
            return jsonify({
                "error": f"Not enough stock for {item['name']} "
                         f"(requested {item['quantity']}, available {item['stock']})"
            }), 400

    total_cents = sum(i["quantity"] * i["price_cents"] for i in items)

    cur2 = conn.cursor()

    # Create order (linked to user_id)
    cur2.execute(
        "INSERT INTO orders (user_id, total_cents) VALUES (%s, %s)",
        (user_id, total_cents),
    )
    order_id = cur2.lastrowid

    # Snapshot items into order_items
    for i in items:
        cur2.execute("""
            INSERT INTO order_items (order_id, product_id, product_name, unit_price_cents, quantity)
            VALUES (%s, %s, %s, %s, %s)
        """, (order_id, i["product_id"], i["name"], i["price_cents"], i["quantity"]))

    # Deduct stock
    for i in items:
        cur2.execute(
            "UPDATE products SET stock = stock - %s WHERE id = %s",
            (i["quantity"], i["product_id"]),
        )

    # Clear cart
    cur2.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart_id,))
    conn.commit()

    cur2.close()
    cur.close()
    conn.close()
    return jsonify({"order_id": order_id}), 201


@app.get("/api/orders")
def api_orders():
    """List all orders for the current logged-in user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"orders": []})

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT o.id, o.total_cents, o.status, o.return_status, o.created_at,
               COUNT(oi.product_id) AS item_count,
               SUM(oi.quantity) AS total_items
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE o.user_id = %s
        GROUP BY o.id
        ORDER BY o.created_at DESC
    """, (user_id,))
    rows = cur.fetchall()

    # Convert datetime to string for JSON serialization
    for row in rows:
        row["created_at"] = row["created_at"].isoformat() if row["created_at"] else None

    cur.close()
    conn.close()
    return jsonify({"orders": rows})


@app.get("/api/orders/<int:order_id>")
def api_order_detail(order_id):
    """Get details for a specific order."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Fetch order (verify it belongs to this user)
    cur.execute(
        "SELECT id, total_cents, status, return_status, created_at "
        "FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user_id),
    )
    order = cur.fetchone()
    if not order:
        cur.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    order["created_at"] = order["created_at"].isoformat() if order["created_at"] else None

    # Fetch order items
    cur.execute("""
        SELECT oi.product_id, oi.product_name, oi.unit_price_cents, oi.quantity,
               p.image_url
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cur.fetchall()

    cur.close()
    conn.close()
    return jsonify({"order": order, "items": items})


@app.post("/api/orders/<int:order_id>/return")
def api_order_return(order_id):
    """Request a return for a confirmed order."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, status, return_status FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user_id),
    )
    order = cur.fetchone()

    if not order:
        cur.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "confirmed":
        cur.close()
        conn.close()
        return jsonify({"error": "Only confirmed orders can be returned"}), 400
    if order["return_status"]:
        cur.close()
        conn.close()
        return jsonify({"error": "Return already requested"}), 400

    cur2 = conn.cursor()
    cur2.execute("UPDATE orders SET return_status = 'return_requested' WHERE id = %s", (order_id,))
    conn.commit()
    cur2.close()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
