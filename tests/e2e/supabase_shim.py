"""
A local stand-in for the Supabase edge, for end-to-end testing only.

WHAT IS REAL HERE, and what is not — because a test that quietly fakes the
thing under test is worse than no test.

  REAL   PostgreSQL 16 with migrations 0001-0011 applied verbatim
  REAL   PostgREST 12.2.3, the official binary — so resource embedding,
         filters and upserts behave exactly as they do against Supabase
  REAL   Row-level security. Every request arrives with a signed JWT,
         PostgREST sets role=authenticated and the claims, and the policies
         from 0008-0011 decide what comes back
  REAL   The Jobsy application code, unmodified
  REAL   Chromium driving the actual UI

  STUBBED  Token minting and password checking (GoTrue). ~60 lines below.
           This is the part NOT under test: what is being tested is whether a
           signed-in user can reach another client's data, and that decision is
           made by Postgres, not by whatever issued the token.

Nothing here is used by the application. It exists only to run tests/e2e/journey.py.
"""
import json, os, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64, hashlib, hmac  # HS256 is HMAC-SHA256; no dependency needed


class jwt:
    """HS256 encode/decode. PyJWT is broken in this image (a Debian/pip clash
    that drags in cffi), and HS256 is small enough that depending on a package
    for it is the bigger risk. PostgREST verifies these with the same secret,
    so if this were wrong nothing would authenticate at all."""

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _unb64(seg: str) -> bytes:
        return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))

    @classmethod
    def encode(cls, payload, secret, algorithm="HS256"):
        head = cls._b64(json.dumps({"alg": "HS256", "typ": "JWT"},
                                   separators=(",", ":")).encode())
        body = cls._b64(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{head}.{body}".encode()
        sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        return f"{head}.{body}.{cls._b64(sig)}"

    @classmethod
    def decode(cls, token, secret, algorithms=None, audience=None):
        head, body, sig = token.split(".")
        expected = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(cls._unb64(sig), expected):
            raise ValueError("bad signature")
        claims = json.loads(cls._unb64(body))
        if claims.get("exp", 0) < time.time():
            raise ValueError("expired")
        return claims

SECRET = "e2e-local-only-jwt-secret-at-least-32-chars-long"
REST = "http://127.0.0.1:3001"
DSN = "host=127.0.0.1 port=5433 user=postgres dbname=jobsy_e2e"


def q(sql, args=()):
    import subprocess
    out = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-p", "5433", "-U", "postgres",
         "-d", "jobsy_e2e", "-tAF|", "-c", sql % args],
        capture_output=True, text=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]


def mint(sub, email, role="authenticated", ttl=3600):
    return jwt.encode({"sub": sub, "email": email, "role": role, "aud": "authenticated",
                       "iat": int(time.time()), "exp": int(time.time()) + ttl},
                      SECRET, algorithm="HS256")


def user_obj(uid, email, meta):
    return {"id": uid, "aud": "authenticated", "role": "authenticated", "email": email,
            "email_confirmed_at": "2026-01-01T00:00:00Z", "phone": "",
            "confirmed_at": "2026-01-01T00:00:00Z", "last_sign_in_at": "2026-01-01T00:00:00Z",
            "app_metadata": {"provider": "email", "providers": ["email"]},
            "user_metadata": meta, "identities": [],
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}


# Response headers PostgREST sets that the client actually reads. Content-Range
# carries the row count; Preference-Applied tells the client which Prefer was
# honoured. Anything not listed is dropped, as before.
_PASSTHROUGH = ("content-range", "preference-applied")


def _passthrough(headers):
    return {k: v for k, v in headers.items() if k.lower() in _PASSTHROUGH}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json", extra=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        # Content-Range is where supabase-py reads .count from. Dropping it made
        # every .count come back None through this shim while the rows arrived
        # perfectly -- so a "does any row exist" check answered "no" and the app
        # told a Dutch client it had no Dutch salary data. The shim is supposed
        # to stub GoTrue and nothing else; silently altering REST responses is
        # exactly the kind of fake that makes a test worse than no test.
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _bearer(self):
        h = self.headers.get("Authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else ""
        try:
            return jwt.decode(tok, SECRET, algorithms=["HS256"], audience="authenticated")
        except Exception:
            return {}

    # ── GoTrue stand-in ───────────────────────────────────────────────
    def _auth(self, path):
        if path.startswith("/auth/v1/token"):
            b = self._body()
            rows = q("select id, email, coalesce(user_metadata::text,'{}') from auth.users "
                     "where lower(email)=lower(%s)", ("'" + b.get("email", "").replace("'", "") + "'",))
            pw = q("select password from auth.users where lower(email)=lower(%s)",
                   ("'" + b.get("email", "").replace("'", "") + "'",))
            if not rows or not pw or pw[0][0] != b.get("password"):
                # Same message for a wrong password and an unknown address, as
                # the real thing does — the app relies on not distinguishing them.
                return self._send(400, {"error": "invalid_grant",
                                        "error_description": "Invalid login credentials"})
            uid, email, meta = rows[0][0], rows[0][1], json.loads(rows[0][2])
            return self._send(200, {"access_token": mint(uid, email), "token_type": "bearer",
                                    "expires_in": 3600, "refresh_token": "e2e-refresh",
                                    "user": user_obj(uid, email, meta)})
        if path.startswith("/auth/v1/logout"):
            return self._send(204, b"", "text/plain")
        if path.startswith("/auth/v1/user"):
            claims = self._bearer()
            if not claims:
                return self._send(401, {"error": "unauthorized"})
            b = self._body()
            uid = claims["sub"]
            if "password" in b:
                q("update auth.users set password=%s where id=%s",
                  ("'" + b["password"].replace("'", "") + "'", "'" + uid + "'"))
            if "data" in b:
                q("update auth.users set user_metadata=%s::jsonb where id=%s",
                  ("'" + json.dumps(b["data"]).replace("'", "") + "'", "'" + uid + "'"))
            rows = q("select id, email, coalesce(user_metadata::text,'{}') from auth.users where id=%s",
                     ("'" + uid + "'",))
            return self._send(200, user_obj(rows[0][0], rows[0][1], json.loads(rows[0][2])))
        return self._send(404, {"error": "not found"})

    # ── everything else goes to the real PostgREST ────────────────────
    def _proxy(self, path):
        url = REST + path[len("/rest/v1"):]
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else None
        req = urllib.request.Request(url, data=data, method=self.command)
        for k, v in self.headers.items():
            if k.lower() in ("authorization", "content-type", "prefer", "accept",
                             "range", "content-profile", "accept-profile"):
                req.add_header(k, v)
        # An unauthenticated call still needs a token PostgREST will accept, so
        # the publishable key is a real anon JWT — exactly as Supabase does it.
        try:
            with urllib.request.urlopen(req) as r:
                return self._send(r.status, r.read(),
                                  r.headers.get("Content-Type", "application/json"),
                                  _passthrough(r.headers))
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read(),
                              e.headers.get("Content-Type", "application/json"),
                              _passthrough(e.headers))

    def _route(self):
        path = self.path
        if path.startswith("/auth/v1"):
            return self._auth(path)
        if path.startswith("/rest/v1"):
            return self._proxy(path)
        return self._send(404, {"error": "not found"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = lambda s: s._route()


if __name__ == "__main__":
    print("ANON_KEY=" + mint("anon", "", role="anon", ttl=86400 * 30))
    ThreadingHTTPServer(("127.0.0.1", 8001), H).serve_forever()
