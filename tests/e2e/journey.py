"""Drive Jobsy as four different people and report what each one can see."""
import sys
from playwright.sync_api import sync_playwright

import os
SHOT = os.environ.get("E2E_SHOTS", "/tmp/jobsy-e2e")
os.makedirs(SHOT, exist_ok=True)
URL = "http://localhost:8599"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
results = []


def check(label, condition, detail=""):
    mark = "ok  " if condition else "FAIL"
    results.append(condition)
    print(f"{mark}  {label}" + (f"   [{detail}]" if detail else ""))


def only_local(page):
    """Block everything off-box. Google Fonts and friends are unreachable here
    and each attempt costs seconds of wall clock for nothing the test needs."""
    page.route("**/*", lambda route: route.abort()
               if "localhost" not in route.request.url and "127.0.0.1" not in route.request.url
               else route.continue_())


def sign_in(page, email, password):
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    boxes = page.query_selector_all("input")
    text_boxes = [b for b in boxes if b.get_attribute("type") in ("text", "password", None)]
    if len(text_boxes) < 2:
        return False
    text_boxes[0].fill(email)
    text_boxes[1].fill(password)
    for b in page.query_selector_all("button"):
        if "sign in" in (b.inner_text() or "").lower():
            b.click(); break
    page.wait_for_timeout(5000)
    return True


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

    # ── 1. The gate ───────────────────────────────────────────────────
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    page.goto(URL, wait_until="domcontentloaded"); page.wait_for_timeout(4000)
    body = page.inner_text("body")
    check("signed out, the app shows a sign-in form", "Sign in" in body)
    check("  and no application content behind it",
          "Pay Equity" not in body and "Matching" not in body)
    check("  and says accounts are not self-service", "no self-registration" in body.lower())
    page.screenshot(path=f"{SHOT}/j1_gate.png", full_page=True)

    # ── 2. A wrong password ───────────────────────────────────────────
    sign_in(page, "hr@northwind.example", "not-the-password")
    body = page.inner_text("body")
    check("a wrong password is refused", "do not match an account" in body)
    check("  without revealing whether the address exists",
          "no such user" not in body.lower() and "unknown" not in body.lower())
    page.screenshot(path=f"{SHOT}/j2_wrong_password.png", full_page=True)
    page.close()

    # ── 3. Northwind's own HR ─────────────────────────────────────────
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    sign_in(page, "hr@northwind.example", "northwind-pw-2026")
    body = page.inner_text("body")
    check("a client admin gets in", "hr@northwind.example" in body)
    check("  and sees their reseller's brand, not ours",
          "Reward Insight" in body, "partner-branded")
    check("  the word Jobsy is gone from the page", "Jobsy" not in body)
    check("  their own client is named", "Northwind" in body)
    check("  a sibling client under the same partner is NOT shown", "Contoso" not in body)
    check("  another partner's client is NOT shown", "Initech" not in body)
    check("  and their own admin can read the access trail, not just us",
          "Activity trail" in body, "readable by the client, not only from a shell")
    page.screenshot(path=f"{SHOT}/j3_client_admin.png", full_page=True)

    # Try to open the other partner's roster by its code.
    for el in page.query_selector_all("input"):
        if (el.get_attribute("aria-label") or "").lower().startswith("load session"):
            el.fill("RIVAL-INITECHXX")
            el.press("Enter")          # Streamlit commits on blur/Enter, not on fill
            page.wait_for_timeout(1500)
            break
    for b in page.query_selector_all("button"):
        if (b.inner_text() or "").strip().lower().startswith("load"):
            b.click(); break
    page.wait_for_timeout(4000)
    body = page.inner_text("body")
    check("holding another client's session code gets you nothing",
          "not available to you" in body.lower() or "no session with that code" in body.lower(),
          "code alone is no longer access")
    check("  and the other client's data does not appear", "Carl Init" not in body)
    page.screenshot(path=f"{SHOT}/j4_stolen_code.png", full_page=True)
    page.close()

    # ── 4. A consultant at the reseller ───────────────────────────────
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    sign_in(page, "consultant@acme.example", "acme-pw-2026")
    body = page.inner_text("body")
    check("a partner consultant gets in", "consultant@acme.example" in body)
    sel = page.query_selector("div[data-testid='stSelectbox']")
    options = []
    if sel:
        sel.click(); page.wait_for_timeout(1500)
        options = [o.inner_text().strip() for o in page.query_selector_all("li, div[role='option']")
                   if (o.inner_text() or "").strip()]
        page.keyboard.press("Escape"); page.wait_for_timeout(500)
    check("  and can switch between BOTH their clients",
          any("Northwind" in o for o in options) and any("Contoso" in o for o in options),
          f"switcher offers {options}")
    check("  labelled with THEIR OWN role on every client, not a colleague's",
          all("partner admin" in o for o in options),
          f"{options} — each must say partner admin")
    check("  but still not the rival partner's client", "Initech" not in body)
    page.screenshot(path=f"{SHOT}/j5_consultant.png", full_page=True)
    page.close()

    # ── 4b. Money follows the CLIENT'S market ─────────────────────────
    #
    # ui/app.py wrote "€" at twenty-four call sites. That is right for the
    # Netherlands and silently wrong for Contoso, which is Polish -- and a
    # salary shown as "€90.000" when it is 90,000 zloty is a different number,
    # on a screen someone sets pay from. The unit tests cover the formatting;
    # what only a browser can show is that the chain from the signed-in user
    # through RLS to orgs.default_country to a currency actually joins up, and
    # that switching client switches market with it.
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    sign_in(page, "consultant@acme.example", "acme-pw-2026")

    def market_line(pg):
        sb = pg.query_selector("section[data-testid='stSidebar']")
        text = sb.inner_text() if sb else pg.inner_text("body")
        return next((l.strip() for l in text.split("\n") if l.strip().startswith("Market:")), "")

    check("a Polish client's market is stated as Polish",
          market_line(page) == "Market: Poland (PLN)", market_line(page) or "no market line")

    # Both clients have bands in their own country, so neither may be told its
    # data is missing. This warning fired wrongly on first run: it asked for a
    # row COUNT, which arrives in a response header, and read None as zero.
    check("  and a market that HAS data is not warned about",
          "No salary reference data" not in page.inner_text("body"))

    sel = page.query_selector("div[data-testid='stSelectbox']")
    sel.click(); page.wait_for_timeout(1200)
    for o in page.query_selector_all("li, div[role='option']"):
        if "Northwind" in (o.inner_text() or ""):
            o.click(); break
    page.wait_for_timeout(6000)
    check("  switching to the Dutch client switches the market with it",
          market_line(page) == "Market: Netherlands (EUR)", market_line(page) or "no market line")
    page.screenshot(path=f"{SHOT}/j8_market.png", full_page=True)
    page.close()

    # ── 5. A read-only viewer ─────────────────────────────────────────
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    sign_in(page, "viewer@northwind.example", "viewer-pw-2026")
    body = page.inner_text("body")
    check("a viewer gets in", "viewer@northwind.example" in body)
    for b in page.query_selector_all("button"):
        if "start new session" in (b.inner_text() or "").lower():
            b.click(); break
    page.wait_for_timeout(4000)
    body = page.inner_text("body")
    check("  and once a session exists, saving is withheld from them",
          "read-only" in body.lower(), "the save button is not offered")
    check("  no Save button is rendered at all",
          not any("save progress" in (b.inner_text() or "").lower()
                  for b in page.query_selector_all("button")))
    # The activity trail answers "who touched our data". It is for the people
    # accountable for the client's data, not for everyone who can see it.
    check("  and the activity trail is not offered to a viewer",
          "Activity trail" not in page.inner_text("body"))
    page.screenshot(path=f"{SHOT}/j6_viewer.png", full_page=True)
    page.close()

    # ── 6. A new starter on a temporary password ──────────────────────
    page = browser.new_page(viewport={"width": 1280, "height": 900}); only_local(page)
    sign_in(page, "newstarter@northwind.example", "temp-pw-2026")
    body = page.inner_text("body")
    check("a temporary password forces a change before anything else",
          "Choose a password" in body)
    check("  and no application content is reachable first",
          "Pay Equity" not in body and "Matching" not in body)
    page.screenshot(path=f"{SHOT}/j7_password_change.png", full_page=True)
    page.close()

    browser.close()

print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
