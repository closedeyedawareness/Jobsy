-- 0021 — a benefit observation that belongs to a market, not to a sector
--
-- RECONSTRUCTED 2026-09-06 from the live schema of qpprcmmdeqlbursogosu.
--
-- Applied to the database as `market_wide_benefit_observations`
-- (20260906155220) with no .sql ever written — the same gap as 0020, found the
-- same way, by reading the ledger against the repository. Numbered 0021 because
-- 0019 and 0020 were already committed by the time it surfaced; it was applied
-- BEFORE both. The statement is order-independent, so the numbering is a
-- filing decision and not a claim about sequence.
--
-- What it does and why: benefits_observations.industry_id was NOT NULL, which
-- said every observation belongs to a sector. Most do. Several of the ones the
-- foreign packs brought back do not:
--
--   * Belgium's CAO 90 take-up -- 8% of employers, 18% of employees -- is
--     measured across the private sector, not within one industry
--   * the FSMA sector-plan contribution of 1,54% is an average ACROSS sectors
--   * Deutschlandticket at EUR 63, the German statutory leave minimum, the
--     Spanish flexible-benefit offering rates: all national facts
--
-- Forcing those into a sector would have meant either inventing an industry
-- they do not have, or dropping the observation. The first is the failure this
-- library exists to prevent; the second throws away the measurement.
--
-- The FK survives a NULL: benefits_observations_industry_fk is MATCH SIMPLE
-- over (org_id, industry_id), so a NULL industry_id is not checked rather than
-- checked and failed. The unique key is (org_id, obs_id) — a surrogate — so it
-- is unaffected either way.

alter table public.benefits_observations
  alter column industry_id drop not null;

comment on column public.benefits_observations.industry_id is
  'NULL means the observation is market-wide rather than sectoral: a national '
  'take-up rate, a statutory ceiling, a cross-sector average. Made nullable '
  '2026-09-06 when the BE/DE/ES/FR packs arrived carrying facts that belong to '
  'a country and to no industry in it.';
