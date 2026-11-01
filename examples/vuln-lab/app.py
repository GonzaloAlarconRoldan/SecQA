#!/usr/bin/env python3
"""SecQA Vuln Lab — a deliberately vulnerable web app for trying SecQA end to end without Docker.

    python examples/vuln-lab/app.py            # http://127.0.0.1:5055

!! INTENTIONALLY INSECURE. It only binds to 127.0.0.1. Never expose it or reuse its code. !!

Planted issues (and how SecQA should find them):
  1. SQL injection in login            POST /login       email = ' OR 1=1--   → logged in as admin   (SAST + API)
  2. IDOR on baskets                   GET /basket?id=2  another user's basket, no ownership check (API)
  3. Excessive data exposure           GET /api/users    password hashes and roles               (API)
  4. Reflected XSS                     GET /search?q=<b>x</b>  rendered unescaped                 (SAST + DAST)
  5. Weak hashing                      MD5 password hashes                                       (SAST)
"""
from __future__ import annotations

import hashlib
import html
import json
import sqlite3
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST, PORT = "127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 5055

db = sqlite3.connect(":memory:", check_same_thread=False)
db.executescript("""
CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password TEXT, role TEXT, address TEXT);
CREATE TABLE baskets (id INTEGER PRIMARY KEY, user_id INTEGER, item TEXT, qty INTEGER, price REAL);
""")
USERS = [
    ("admin@lab.test", "Sup3r-Secret!", "admin", "1 Admin Street, Springfield"),
    ("alice@lab.test", "alice-pass-2026", "customer", "742 Evergreen Terrace, Springfield"),
    ("bob@lab.test", "bob-pass-2026", "customer", "31 Spooner Street, Quahog"),
]
for i, (email, pw, role, addr) in enumerate(USERS, 1):
    db.execute("INSERT INTO users VALUES (?,?,?,?,?)",
               (i, email, hashlib.md5(pw.encode()).hexdigest(), role, addr))  # noqa: S324 - planted weakness
for uid, item, qty, price in [(1, "Admin badge", 1, 0.0), (2, "Apple juice", 3, 1.99), (2, "Lemon juice", 1, 2.49),
                              (3, "Banana smoothie", 2, 3.5), (3, "Gift card", 1, 50.0)]:
    db.execute("INSERT INTO baskets (user_id, item, qty, price) VALUES (?,?,?,?)", (uid, item, qty, price))

CSS = """body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}
header{background:#7c2d12;color:#fff;padding:12px 24px;display:flex;justify-content:space-between}
header a{color:#fed7aa;margin-left:16px;text-decoration:none}main{max-width:820px;margin:24px auto;padding:0 16px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin-bottom:16px}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left}
.warn{background:#fef3c7;border:1px solid #f59e0b;padding:8px 12px;border-radius:8px;font-size:13px}
input{padding:8px;border:1px solid #cbd5e1;border-radius:6px;width:100%;margin:4px 0 12px}
button{background:#7c2d12;color:#fff;border:0;padding:9px 16px;border-radius:6px}"""


def page(title: str, body: str, user: dict | None = None) -> bytes:
    who = f"{html.escape(user['email'])} ({user['role']})" if user else "not logged in"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title} · Vuln Lab</title>
<style>{CSS}</style></head><body><header><b>🍹 Vuln Lab shop</b><span>{who}
<a href="/">Home</a><a href="/login">Login</a><a href="/basket?id=2">My basket</a><a href="/search?q=juice">Search</a></span>
</header><main><p class="warn">Deliberately vulnerable training app — local use only.</p>{body}</main></body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _user(self) -> dict | None:
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "session" not in c:
            return None
        row = db.execute("SELECT id, email, role FROM users WHERE id = ?", (c["session"].value,)).fetchone()
        return {"id": row[0], "email": row[1], "role": row[2]} if row else None

    def _send(self, body: bytes, status=200, ctype="text/html; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        user = self._user()
        if u.path == "/":
            return self._send(page("Home", '<div class="card"><h1>Welcome to the juice shop</h1>'
                                   "<p>Log in to see your basket.</p></div>", user))
        if u.path == "/login":
            return self._send(page("Login", """<div class="card"><h2>Login</h2><form method="post" action="/login">
<label>Email<input name="email" id="email"></label><label>Password<input name="password" type="password"></label>
<button>Log in</button></form></div>""", user))
        if u.path == "/account":
            if not user:
                return self._send(b"", 302, headers={"Location": "/login"})
            return self._send(page("Account", f'<div class="card" id="account"><h2>My account</h2>'
                                   f'<p>Signed in as <b id="who">{html.escape(user["email"])}</b></p>'
                                   f'<p>Role: <b id="role">{user["role"]}</b></p></div>', user))
        if u.path == "/basket":
            basket_id = (qs.get("id") or ["2"])[0]
            # PLANTED: no check that the basket belongs to the logged-in user (IDOR)
            owner = db.execute("SELECT email, address FROM users WHERE id = ?", (basket_id,)).fetchone()
            rows = db.execute("SELECT item, qty, price FROM baskets WHERE user_id = ?", (basket_id,)).fetchall()
            if not owner:
                return self._send(page("Basket", "<p>Basket not found</p>", user), 404)
            items = "".join(f"<tr><td>{html.escape(i)}</td><td>{q}</td><td>${p:.2f}</td></tr>" for i, q, p in rows)
            return self._send(page("Basket", f"""<div class="card" id="basket"><h2>Basket #{basket_id}</h2>
<p>Owner: <b id="owner">{html.escape(owner[0])}</b><br>Ship to: <span id="address">{html.escape(owner[1])}</span></p>
<table><tr><th>Item</th><th>Qty</th><th>Price</th></tr>{items}</table></div>""", user))
        if u.path == "/api/users":
            # PLANTED: returns password hashes and roles to anyone
            rows = db.execute("SELECT id, email, password, role FROM users").fetchall()
            data = [{"id": r[0], "email": r[1], "password": r[2], "role": r[3]} for r in rows]
            return self._send(json.dumps(data, indent=2).encode(), ctype="application/json")
        if u.path == "/search":
            q = (qs.get("q") or [""])[0]
            # PLANTED: reflected XSS — q is not escaped
            return self._send(page("Search", f'<div class="card"><h2>Results for <span id="term">{q}</span></h2>'
                                   "<p>No products found.</p></div>", user))
        self._send(page("Not found", "<p>404</p>", user), 404)

    def do_POST(self):
        if urlparse(self.path).path != "/login":
            return self._send(b"", 404)
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode())
        email = (form.get("email") or [""])[0]
        pw = hashlib.md5((form.get("password") or [""])[0].encode()).hexdigest()  # noqa: S324
        # PLANTED: SQL injection — user input concatenated into the query
        query = "SELECT id FROM users WHERE email = '" + email + "' AND password = '" + pw + "'"
        try:
            row = db.execute(query).fetchone()  # noqa: S608
        except sqlite3.Error as exc:
            return self._send(page("Login", f'<div class="card"><h2>Database error</h2><pre>{html.escape(str(exc))}'
                                   f"\n{html.escape(query)}</pre></div>"), 500)
        if not row:
            return self._send(page("Login", '<div class="card"><p>Invalid credentials</p></div>'), 401)
        self._send(b"", 302, headers={"Location": "/account", "Set-Cookie": f"session={row[0]}; Path=/; HttpOnly"})


if __name__ == "__main__":
    print(f"[vuln-lab] DELIBERATELY VULNERABLE app on http://{HOST}:{PORT} (Ctrl+C to stop)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
