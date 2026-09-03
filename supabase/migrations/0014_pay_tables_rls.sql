-- 0014 — pay_mix and pay_elements join the RLS policies
--
-- NUMBERING: 0012 (country_dimension) and 0013 (anon_reaches_nothing) are
-- applied to the database but live on the unmerged multi-country branch, not in
-- this folder. This file takes 0014 rather than reusing a number that branch
-- already spent. The database is the record of what is applied; the gap here is
-- the honest shape of that.
--
-- WHY: migration 0008 gave every reference table a read and a write policy and
-- skipped these two, because at the time nothing loaded them — they sat in the
-- database and were read past SHEET_MAP by whoever needed a pay figure. That
-- ended on 2026-09-03: they are ordinary library sheets now, loaded by Catalog,
-- typed by Repository, inside the parity gate. So they take the same two
-- policies as every sibling table.
--
-- Until the app stops reading the library with the secret key this changes
-- nothing at runtime — service_role bypasses RLS. It is exactly at that moment
-- that it would have mattered, and silently: two tables returning zero rows,
-- and every variable-pay figure disappearing from the product with no error
-- anywhere to say why.

drop policy if exists pay_mix_read  on public.pay_mix;
drop policy if exists pay_mix_write on public.pay_mix;

create policy pay_mix_read on public.pay_mix
  for select to authenticated using (app.can_read_org(org_id));
create policy pay_mix_write on public.pay_mix
  for all to authenticated using (app.can_write_org(org_id))
  with check (app.can_write_org(org_id));

drop policy if exists pay_elements_read  on public.pay_elements;
drop policy if exists pay_elements_write on public.pay_elements;

create policy pay_elements_read on public.pay_elements
  for select to authenticated using (app.can_read_org(org_id));
create policy pay_elements_write on public.pay_elements
  for all to authenticated using (app.can_write_org(org_id))
  with check (app.can_write_org(org_id));
