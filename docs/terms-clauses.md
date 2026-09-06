# Terms & Conditions — product-derived clauses

**Status: DRAFT LANGUAGE. Not legal advice, and not binding on anyone.**
Started 6 September 2026.

This file exists because some product decisions only work if the customer has
agreed to them. A technical rule the client never accepted is not consent,
however well the code behaves. So when a design settles something that needs the
customer's agreement, the clause is written here, next to the reason for it, and
carried into the Terms when a lawyer has been over it.

**Nothing here has been reviewed by a lawyer.** These are drafted by the person
who knows what the product actually does, so that a lawyer is editing a correct
description rather than inventing one. That is the useful division of labour —
it is not a substitute for the review.

There is no Jobsy Terms & Conditions document yet. This is the input to the
first one.

---

## Clause 1 — Improvement of the reference library from customer use

**Origin:** `docs/employer-determinations.md` §6, decided 6 September 2026.
**Why it is needed:** the product learns from how customers correct it. That
learning is the only asset here that compounds and cannot be reproduced from
public sources. It is also derived from customer material, so it needs saying
out loud rather than assuming.

### Draft text

> **Improvement of the Reference Library.**
>
> **(a) What we learn.** When you or your users confirm, correct or reject a
> proposed interpretation of your data — for example confirming that a job title
> in your organisation corresponds to a particular standard role — we may use
> that correction to improve the Reference Library used across our service.
>
> **(b) What we never use.** We do not use, publish or make available to any
> other customer: your employee data; your pay data; your organisational
> structure; or any determination you record in the service about how your own
> job levels, grades or cross-country equivalences should be treated. Records of
> your determinations remain yours and are never shared, in any form, with any
> other customer.
>
> **(c) How your identity is handled.** Where a correction is carried into the
> Reference Library, your organisation is not named. The only attribute retained
> is your industry classification.
>
> **(d) The threshold.** Corrections that carry structural or pay information —
> including a job title together with a grade or level, salary band information,
> and benefit values — are not made available to any other customer unless the
> same information has been contributed independently by at least **five** other
> organisations. Below that number the information remains available only to
> you. We apply this because removing an organisation's name does not, by
> itself, prevent it from being recognised.
>
> **(e) Corrections that carry no such information** — for example that a
> particular job title means a particular standard role, without any grade,
> level or pay attached — may be carried into the Reference Library without that
> threshold, as they do not identify your organisation.
>
> **(f) Your right to object.** You may tell us at any time that your
> corrections must not be used under paragraph (a). We will honour that from the
> date you tell us. Corrections already incorporated before that date cannot be
> withdrawn from the Reference Library, because they are by then combined with
> those of other organisations and are no longer separable — which is why this
> clause is set out before you begin rather than afterwards.
>
> **(g) Your own data is unaffected.** Your Reference Library remains available
> to you in full, and your export rights are unchanged, whether or not you
> object under paragraph (f).

### Notes for the lawyer

1. **The five in (d) is not arbitrary and should not be softened without
   thought.** It is the same threshold the product already applies internally
   when it suppresses pay-equity figures for small groups, on the stated ground
   that they are "unreliable and re-identifying". Using two different numbers
   for the same idea would be worse than using one imperfect one.
2. **(f) admits something uncomfortable and does so deliberately.** Learning
   already merged cannot be pulled back out. Saying so plainly before signature
   is more defensible than an unqualified right to withdraw that we could not
   actually perform.
3. **(b) is the clause that matters commercially.** It is what allows a customer
   to record a cross-country equivalence — a genuine business judgement about
   their own people — without fearing that it becomes market intelligence.
4. **Check whether (a) needs a lawful-basis statement under GDPR** where
   corrections are made by named users, and whether industry classification plus
   correction volume can be re-identifying for a customer that is the only one
   of its kind in a market. The threshold in (d) is designed for that risk but
   has not been tested against a real customer distribution, because there is
   only one organisation in the database today.

---

## Clause 2 — Generated vacancy text

**Origin:** Elmar's decision, 6 September 2026. The product will DRAFT vacancy
text from a standard role's values, rather than only reporting what a source
says.
**Why it is needed:** this is the first thing this product writes for an
EXTERNAL audience. Everything else it produces is an internal analysis a
professional reads; a vacancy is published, and what it says can be unlawful.

### What makes the position defensible

The write-back. The employer edits the draft and what they publish is what they
wrote — the tool proposes and a person disposes. That is not a disclaimer
dressed up; it is the actual shape of the feature, and the clause below only
describes it. A generator that published directly could not be defended by any
wording.

### Draft text

> **Generated vacancy text.**
>
> **(a) What we provide.** Where you ask us to, the service drafts vacancy text
> from the role information in your reference library. That draft is a starting
> point prepared by software.
>
> **(b) You decide what is published.** The draft is presented for you to edit
> and approve. Nothing is published by us and nothing leaves the service on your
> behalf. The text you publish is your text, whether or not you changed our
> draft.
>
> **(c) What we do not warrant.** We do not warrant that generated text complies
> with recruitment, equal-treatment, non-discrimination or advertising law in
> any jurisdiction, nor that it is accurate, complete or suitable for the role
> you intend to fill. Those obligations rest on the employer who publishes, and
> the service does not assume them.
>
> **(d) What we do provide instead of a warranty.** Every generated draft is
> recorded with the role and version it was generated from, the text as
> generated, and the text as you approved it — so the difference between the two
> is always visible to you and to anyone you have to show it to.
>
> **(e) Nothing here limits liability that cannot be limited by law**, including
> for our own intent or gross negligence.

### Notes for the lawyer

1. **(c) is a warranty exclusion, not an indemnity, and it is deliberately not
   phrased as "we accept no responsibility for anything".** A blanket clause is
   the kind courts read down. What is actually true — we cannot know the market,
   the role or the audience, and the employer publishes — is narrower and holds
   better.
2. **(d) is the substance and should not be trimmed as boilerplate.** Keeping
   the generated text beside the approved text is what makes (b) verifiable
   rather than asserted, and it is the same evidence the AI Act point below
   turns on.
3. Check whether Dutch law (WAADI, the Algemene wet gelijke behandeling) or the
   equivalent in BE, DE, FR or ES places any duty on a party that PREPARES an
   advertisement rather than places it. The clause assumes it does not.

---

## Still to draft

Listed so they are not forgotten, and deliberately not attempted here:

- **Data processing agreement**, retention and deletion. Migration 0010 already
  implements retention and minimisation; the DPA has to describe what the code
  actually does, so it should be written against 0010 rather than from a
  template.
- **Determination retention.** A recorded determination has to outlive the
  roster it was made about or it cannot be defended later, which is in tension
  with the deletion rules above. Open in `employer-determinations.md` §8.
- **What the service does not do.** The product refuses to state a legal
  conclusion; the Terms should say the same thing in the same words, so that the
  screen and the contract cannot drift apart.
- **AI Act intended-use statement**, once the classification question in
  `employer-determinations.md` §8 has been answered by counsel.
