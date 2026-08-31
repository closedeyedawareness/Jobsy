-- 0011_partner_branding.sql
--
-- Stage 6 of docs/PLAN-whitelabel-tenancy.md: F-1 and F-2. The product stops
-- being called Jobsy by anyone who has not bought Jobsy.
--
-- ── WHAT "WHITE LABEL" REACHES, AND WHAT IT DOES NOT ──────────────────────
--
-- Branding lives on the PARTNER, because that is who resells. Everything a
-- signed-in user sees can follow it: the product name, the logo, the accent
-- colours, and the prefix on session codes.
--
-- Two things it cannot reach, and both are worth knowing before somebody
-- promises otherwise in a sales meeting:
--
-- 1. THE SIGN-IN PAGE. Before sign-in there is no identity, so there is no
--    partner to look up. Resolving one from the URL would mean letting an
--    unauthenticated caller read the partners table, which hands anyone a list
--    of who the resellers are and who their clients might be. Not worth it. A
--    dedicated deployment brands its own front door from Streamlit secrets
--    instead -- see services/branding_service.py -- and a shared instance shows
--    a neutral one.
--
-- 2. STREAMLIT'S OWN WIDGET CHROME. .streamlit/config.toml already says why:
--    "Streamlit paints widget internals from this block itself, and injected
--    CSS can only partly reach them". That block is read once at server start
--    and cannot vary per request, so sliders and select boxes keep one base
--    palette however many partners share the instance.
--
-- Both point the same way: a partner who wants the whole surface gets their own
-- deployment, which is the normal white-label arrangement anyway. This
-- migration makes a shared instance work properly, and makes a dedicated one a
-- configuration rather than a fork.

alter table partners
  add column if not exists product_name   text not null default 'Jobsy',
  add column if not exists code_prefix    text not null default 'JOBSY-',
  add column if not exists logo_url       text,
  add column if not exists primary_color  text not null default '#8850EF',
  add column if not exists accent_color   text not null default '#67E8F9',
  add column if not exists support_email  text;

-- A product name that is blank or whitespace would render as a gap where the
-- title goes, which reads as a bug rather than as branding.
alter table partners drop constraint if exists partners_product_name_present;
alter table partners add constraint partners_product_name_present
  check (length(btrim(product_name)) between 1 and 40);

-- The prefix is typed by hand and read down a phone, like the code body it sits
-- in front of. Upper case, no separator characters of its own, and it ends in
-- the hyphen so the stored value is the whole prefix rather than something the
-- application has to remember to append.
alter table partners drop constraint if exists partners_code_prefix_shape;
alter table partners add constraint partners_code_prefix_shape
  check (code_prefix ~ '^[A-Z][A-Z0-9]{1,9}-$');

-- Not unique, deliberately. Two partners could both pick 'REWARD-' and nothing
-- breaks: session codes are globally unique on the body, which carries 31^10 of
-- entropy, and the prefix is a human-facing label rather than an identifier. A
-- unique constraint here would only produce a confusing failure at the moment
-- an operator is trying to onboard a customer.

alter table partners drop constraint if exists partners_colors_are_hex;
alter table partners add constraint partners_colors_are_hex
  check (primary_color ~ '^#[0-9A-Fa-f]{6}$' and accent_color ~ '^#[0-9A-Fa-f]{6}$');

-- A logo is fetched by the browser, so it has to be somewhere a browser can
-- reach over TLS. Rejecting http:// here avoids a mixed-content warning on a
-- page that is otherwise entirely about looking trustworthy.
alter table partners drop constraint if exists partners_logo_is_https;
alter table partners add constraint partners_logo_is_https
  check (logo_url is null or logo_url ~ '^https://');

comment on column partners.code_prefix is
  'Prefix on session codes for this partner''s clients, e.g. ACME-. Human-facing '
  'label only: uniqueness lives in the code body, not here.';
comment on column partners.product_name is
  'What the product calls itself for this partner. Replaces every user-visible '
  '"Jobsy" once set.';

-- The partners_read policy from 0008 already lets a signed-in user see their own
-- partner and their client's partner, which is exactly the reach branding needs:
-- a client's HR staff must be able to read the name and logo of the reseller
-- whose product they are using. No new policy, and no new exposure -- the
-- columns added here ride on a rule that was already argued through.
--
-- Nothing grants anon a read. That is what keeps the partner list off the
-- sign-in page, and is the reason point 1 in the header is a limitation rather
-- than an oversight.
