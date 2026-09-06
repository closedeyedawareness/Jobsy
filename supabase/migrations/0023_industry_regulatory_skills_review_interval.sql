-- 0023 — the table 0019 added, and forgot to schedule
--
-- Applied 2026-09-06. 0019 split industry_skills in two and gave the new table
-- no review interval, so ops_jobsy_review() reported it as an absence rather
-- than a schedule. A reference table nobody has to look at again is one that
-- goes stale quietly, which is the whole reason library_review_policy exists.
--
-- Twelve months, not the twenty-four its universal sibling keeps, and the
-- difference is the point. "Agile at scale" does not stop being true because a
-- year passed. A regulatory citation does: PC 200 reindexes every January, the
-- Metallurgie classification was rewritten for 2024, AML regimes are restated
-- by directive. These rows name laws and collective agreements BY NUMBER, and a
-- superseded number reads exactly like a current one.

insert into public.library_review_policy (table_name, review_after_months, reason)
values (
  'industry_regulatory_skills',
  12,
  'Laws and collective agreements cited by name and number. Faster than its '
  'universal sibling at 24 months because the citation is the content: PC 200 '
  'reindexes each January, the Metallurgie classification was rewritten for '
  '2024, and a superseded reference reads exactly like a current one.'
)
on conflict (table_name) do update
  set review_after_months = excluded.review_after_months,
      reason = excluded.reason;
