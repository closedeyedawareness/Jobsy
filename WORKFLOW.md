# Jobsy — werkvoorraad

Wat er staat, wat net af is, en wat er nog moet. Bijgewerkt 6 september 2026.

Zelfde vorm en zelfde maatstaf als `WORKFLOW.md` in Waterpas: de volgorde volgt
*wat de motor aantoonbaar juist en verkoopbaar maakt*, niet wat het meeste
functionaliteit oplevert. De inhoudelijke uitleg hoort in `docs/` — dit bestand
zegt wat er NU moet. Afgeronde regels verhuizen naar "Net af" en verdwijnen
daarna; dit is geen logboek. Het logboek is `docs/delivery-log.md`.

De regels hieronder staan ook in de Jobsy-sectie van `C:\PH-LiveOps\workflow.md`,
die het dashboard voedt. Die is de korte lijst voor het overzicht; deze is de
lange met de redenen erbij.

---

## Waar het nu staat

Een job-architectuurmotor: matching van titels naar rollen, functieprofielen en
-waardering, loonbanden per markt, skills-intelligentie, beloningsgelijkheid
volgens Richtlijn (EU) 2023/970, en sinds 6 september een vacatureconcept dat
alleen samenstelt en nooit publiceert.

- **1004 tests groen**, 26 overgeslagen, **5 xfailed** (gemeten 6 september).
  Die vijf zijn geen schuld maar voorraad: drie ervan leggen de landvondsten van
  vandaag vast met `xfail(strict=True)`, zodat het rood blijft staan zonder dat
  een andere sessie erover struikelt en luid faalt op de dag dat iemand het
  repareert.
- Draaien **uitsluitend uit `C:\Jobsy\.venv`** (3.12). Op de standaard 3.14
  importeert pandas niet; die "Application Control policy"-melding is
  versiegebonden en geen machinebeleid.
- Database: Supabase `qpprcmmdeqlbursogosu`. Migraties staan tot en met **0023**.
  0020 en 0021 zijn op 6 september **gereconstrueerd uit het levende schema** —
  ze waren toegepast zonder dat er ooit een `.sql` was geschreven.
- Vijf markten dragen echte data (NL, BE, DE, ES, FR). De **NL-set is de enige
  die volledig is**; de andere vier zijn afgeleid of deels onbevestigd, zie
  `docs/country-data-tiers.md`.

---

## De volgorde

### 1. De landdimensie in `Repository` — dit blokkeert al het andere landwerk

Drie vondsten uit de sweep van 6 september, alle drie vastgelegd met
`xfail(strict=True)`. Ze zien eruit als drie bugs en zijn er één: **een laag die
de landdimensie niet draagt terwijl de database hem wél heeft.**

- `title_mapping` heeft geen land in de sleutel, terwijl de database op
  `(org_id, country, existing_title)` sleutelt en de loader bewust rijen uit
  elke markt houdt. Twee rijen erin, één ingang eruit. Gemeten in de echte data:
  576 rijen, 5 markten, 48 titels in meer dan één markt, **2 waar de markten het
  oneens zijn** — `business developer` (FR=J-SAL-01, NL=J-SAL-04) en
  `data scientist` (FR=J-DAT-03 tegen BE/ES=J-DAT-04). De zichtbare helft zit in
  review: goedkeuren meldt "already mapped" en schrijft niets, dus de
  goedkeuring is weg terwijl de database hem had aangenomen.
- `plan_write_back` neemt `country` aan en leest het nooit.
- Zeven `_build_*`-methoden doen `(rij-land or "NL")`. Het commentaar legt uit
  waarom: *"missing country means the Dutch library, matching 0012's backfill"* —
  waar toen het werd geschreven, want alles was Nederlands. Nu boekt het
  werkboek van een Belgische klant zonder Country-kolom volledig als Nederlands.
  De lege helft is veilig (BE vraagt, krijgt niets); **de onveilige helft is
  onzichtbaar**: dezelfde rijen zijn zichtbaar voor een Nederlandse sessie, als
  Nederlandse banden, met Belgische bedragen.

Reparatievolgorde: `title_mapping` eerst, want de landpakketten aansluiten
bovenop een landloze sleutel maakt het erger — dan komt per markt een ander
antwoord binnen dat in dezelfde ingang wordt geschreven.

**Beide reparaties verplaatsen data van bestaande klanten en zijn dus
productbeslissingen, geen stille refactors.** Ze staan in de beslissingenlijst.

### 2. De rest van de sweep

50 functies nemen een land- of marktparameter aan. Stand: 4 doen het goed met
`country or active_country()` — expliciet land wint, actieve markt is terugval —
en dat is de vorm die de andere gevallen hadden moeten hebben, dus die is als
norm opgeschreven. 2 nemen een land aan en lezen het nooit
(`vacancy_service.compose`, `market_notes._seniority_line`); vandaag onschadelijk,
maar het is de vorm die de vorige drie bugs heeft voortgebracht en `compose`
staat naast `draft`, waar het wél misging. Per geval kiezen: eerbiedigen, of de
parameter laten vervallen, met de reden erbij. De overige ~43 zijn nog niet op
subtielere vormen dan "nooit gelezen" bekeken.

**De regel die hieruit volgt en overal geldt:** elke functie die een land
aanneemt krijgt een fixture met **twee** markten met verschillende waarden. Met
één markt geladen zijn "eerbiedigt het gevraagde land" en "negeert het" niet van
elkaar te onderscheiden — daarom stonden alle vier de landbugs in een groene
suite.

### 3. Fase 3 — de pakketten per module aansluiten

In volgorde van schade als het misgaat: **beloning** eerst (`pay_elements` heeft
geen land, terwijl de pakketten al weten dat vakantiegeld 8% NL is, 92% van een
maand voor Belgische bedienden, en in Duitsland niet wettelijk) · dan
**matching** (`title_mapping` ís landgebonden, `jobs` en `job_profiles` niet) ·
dan **skills** (het EQF-anker bestaat, `bridge()` heeft nul aanroepers) · dan
**benefits** (`benefits_catalog` niet gescheiden, observaties wel). 9-box en
organigram hebben geen eigen tabellen en zijn al aangesloten via de
marktnotities.

Wat er al werkt en niet opnieuw hoeft: rapportageplicht per land in drie
registers, valutawaarschuwing bij gemengde eenheden, de poort die het
Nederlandse ISF-raster buiten NL afschermt, en de marktnotities op organigram en
9-box. `bridge()`, `capability_gaps()` en de loontabellen van de Spaanse chemie
en de Poolse gemeenten bestaan wel maar worden door niets gelezen.

**België houdt geen enkele koppeling naar EQF**, terwijl het eigen pakket het
EQF-niveau de enige betrouwbare sleutel noemt tussen de Vlaamse VKS en de
franstalige CFC. Eén werkgever met vestigingen in beide gewesten heeft twee
raamwerken, en de tool kan niet wat zijn eigen notitie de enige manier noemt.

### 4. Contrasigneren — LIVE vraagt een mens

LIVE betekent bewust dat een **mens** de bronnen heeft nagekeken; verificatie
door een agent levert hooguit DRAFT. Zie `docs/employer-determinations.md`.

- **Rond 6 oktober 2026 controleren: heeft Duitsland de richtlijn omgezet?** Dat
  is het enige wat Duitsland van 78% naar live tilt. De claim in `de.py` staat op
  ONBEVESTIGD omdat je niet kunt bewijzen dát een wet niet bestaat, alleen dat je
  hebt gezocht. Zoek op *Entgelttransparenzgesetz* en *Umsetzung Richtlinie (EU)
  2023/970*, en op het Bundesgesetzblatt. Vindt de zoektocht opnieuw niets, dan
  alleen de datum in de claim verzetten — de claim zelf klopt dan nog.
- **De Belgische UITLEG.** Twee EU-geaccordeerde referencingrapporten zeggen 1:1;
  géén Belgische wet zegt het, en het Vlaamse rapport zet er zelf *"best fit"*
  bij. Een Belgische EQF 6 en een Nederlandse NLQF 6 zijn vergelijkbaar, niet
  gelijk — en de Nederlandse kant is al een eenrichtingsfunctie (4 en 4+). Twee
  zachte randen ontmoeten elkaar nu in één route.

### 5. Twee vragen voor een jurist — geen van beide blokkerend

De licentievoorwaarden van de ILO voor ISCO-08 zelf, los van de nationale
omzettabellen. En of de Duitse §87(1) Nr. 6-lezing standhoudt: die zegt dat een
Duitse uitrol van Jobsy zélf een Betriebsvereinbarung vraagt, en dat is een
verkoopfeit, geen compliancenotitie.

### 6. De volgende drie markten: Italië, Portugal, het Verenigd Koninkrijk

Vastgelegd 6 september: **als alles goed staat gaan er drie landen bij.** De
volledige analyse staat in `docs/PLAN-country-coverage.md` §6; hier het deel dat
de volgorde bepaalt.

"Als alles goed staat" betekent niet "de suite is groen" — die was groen door
elk van de landdefecten heen. Het betekent: **punt 1 hierboven is gesloten.**
Drie markten toevoegen bovenop een laag die de landdimensie niet draagt voegt
geen drie problemen toe, het vermenigvuldigt het bestaande.

- **IT en PT** lijken structureel op ES en FR: euro, EU, richtlijn van
  toepassing. Werk is rijen importeren. Wat géén kopie is: Italië's **CCNL** en
  de Portugese sectorale akkoorden zijn andere instituten, precies zoals ERA en
  de conventions collectives dat zijn. De eerlijkheidsgrens uit
  `docs/cao-metalektro-isf-reference.md` moet per land opnieuw beargumenteerd,
  nooit overgenomen.
- **UK is de eerste markt buiten de EU**, en drie dingen in deze codebase nemen
  stilzwijgend aan dat dat niet zou gebeuren:
  1. **Richtlijn 2023/970 geldt daar niet, en `vacancy_service.draft` past art. 5
     onvoorwaardelijk toe** (nagekeken 6 september: de `requirements`-tuple wordt
     zonder landtoets opgebouwd). Een Britse vacature krijgt te horen dat hij
     loon moet noemen onder 5(1)(a) en een cao onder 5(1)(b) — met verwijzing
     naar een instrument dat die werkgever niet bindt. Dat is erger dan een
     ontbrekende functie: het is het product dat zich stellig vergist in de wet,
     in de enige module die naar BUITEN publiceert.
  2. Het VK heeft een **eigen regime** — gender pay gap reporting onder de
     Equality Act 2010 vanaf 250 werknemers — met eigen definities en
     peildata. Art. 5 daarop afbeelden is dezelfde categoriefout als ERA op de
     CAO afbeelden.
  3. **GBP en de EU-basislaag.** Valuta is al per land (`countries.currency`; de
     rapportdienst kent zloty, krona, krone en koruna) en het besluit om *niet*
     om te rekenen is hier meer waard, niet minder. Maar `_MarketRows` lost op
     als land → EU-basislaag → niets, en **een Britse rij mag nooit op een
     EU-basislaag terugvallen**: voor een niet-lidstaat is die terugval fout van
     constructie, niet slechts onnauwkeurig.

Voordat er iets van IT, PT of UK wordt gezaaid: zorg dat de tweemarkt-fixture al
een **niet-euro, niet-EU** markt bevat. Anders blijven de aannames hierboven
onzichtbaar op precies de manier waarop `(rij-land or "NL")` dat was — één keer
gemeten toen het klopte, en nooit opnieuw.

### 7. Capaciteit en koppelingen — pas hierna

- **AFAS tegen een echte tenant.** De connector is geschreven vanaf de
  gepubliceerde REST-interface en heeft nog nooit een echte omgeving gezien; de
  eerste keer is een test, geen release.
- **AI semantic matching** (`MatchType.AI` is nog een uitgecommentarieerde
  regel), elke hit door de reviewwachtrij met een motivering. De wachtrij bestaat
  nu, dus dit is niet meer geblokkeerd.
- **Effective-dated banden en "as of"-vragen** — `effective_from` wordt opgeslagen
  en door niets op datum gelezen.
- **Room-to-Grow naar HRS**: geaggregeerd, confidence-gewogen. Het
  cross-productstuk.
- **Skills vastleggen tegen de catalogus**: gecontroleerde woordenlijst → ~100%
  resolutie tegen de ~5% van vandaag (vrije tekst).
- **Later**: lees/schrijf-API zodat andere systemen de canonieke rol kunnen
  gebruiken; trendanalyse over de tijdgestempelde data; één Total Rewards-beeld
  in plaats van twee zusterpagina's.
- **Vacature-export met huisstijl.** De bouwstenen liggen er: `job_profiles`
  heeft omschrijving, verantwoordelijkheden, vereiste skills en specialismen,
  `role_skill_map` de skills per rol, en `branding_service` draagt sinds PR #32
  logo, kleuren en productnaam per partner. Twee dingen vooraf beslissen: dit is
  de eerste keer dat het product tekst voor EXTERN gebruik maakt in plaats van
  interne analyse, en een vacaturetekst raakt wervingsregels die per markt
  verschillen — dus dezelfde vraag als overal: rapporteren we wat de bron zegt,
  of gaan we formuleren?

---

## Net af (6 september 2026)

- **`industry_skills` deed twee dingen** — migratie `0019` splitst het in
  universele praktijk en `industry_regulatory_skills`. De snede toetst zichzelf:
  vóór de splitsing had NL 14 rijen tegen 9 per buitenlandse markt, erna heeft
  elke markt er precies 9. Die asymmetrie wás de vermenging.
- **`SHEET_MAP` kende de nieuwe tabel niet** terwijl `library_review_policy` hem
  sinds `0023` wél had — de versheidskaart noemde een tabel op die de export niet
  kon schrijven (`e500ba3`). Er zat een rijfilter onder: een oud klantwerkboek
  draagt beide helften op één blad, en alleen voorkeur zou alle vijftig rijen in
  béide tabellen hebben geschreven.
- **De motor vulde in wat hij niet wist** (`246b2be`). De migratie las het land
  uit het id, de import niet, dus SK-IND-DE-01 (GwG) en SK-IND-ES-01 (Ley
  10/2010) stonden vier uur lang geboekt als Nederlands recht — en de bijbehorende
  toets beweerde dat dat klopte. Een toets die een defect als beperking beschrijft
  is de duurste soort groen.
- **De terugval wás de bug** (`b465afe`). `vacancy_service` viel terug op
  `repo.salary`, dat op de sessiemarkt oplost, dus een Spaanse advertentie droeg
  de Nederlandse band 58.000–82.000 in plaats van de Spaanse 33.100–46.700. Het
  verwijderen ervan maakte 24 toetsen rood en legde bloot dat élke vacaturetoets
  de foute terugval had gedraaid.
- **Poolse deeltijd** (`1844976`). Zonder pro-ratering stond rauw deeltijdloon
  naast andermans voltijdcijfer; op een set waar deeltijders exact de helft
  verdienen ging de gemeten kloof van 25,0% naar 0,0%. Omdat deeltijd vrouwelijk
  skewt landde die overdrijving op vrouwen, in de richting die een
  rapportageplicht uitlokt. De set is verzonnen; die 25 punten zijn geen
  voorspelling.
- **De eerlijke beperking klopte niet meer** (`f7e5419`). De alinea in
  `library_export_service` die zegt wat de export NIET bevat noemde `pay_mix` en
  `pay_elements` als niet-geladen terwijl beide in SHEET_MAP staan, en telde vier
  bladen te weinig. Dat is erger dan verouderd commentaar elders: een lezer
  gelooft die alinea juist omdat hij iets toegeeft. Er staat nu een toets op die
  faalt op elk hardgecodeerd aantal.
- **0022** zette RLS aan op `library_review_policy` — de reviewtabel die iedereen
  kon ontwapenen. Leesbeleid voor `authenticated`, bewust geen schrijfbeleid.

---

## Wat bij Elmar ligt, niet bij de motor

Bijgehouden in de beslissingenlijst
(`https://claude.ai/code/artifact/5cb68ddb-1213-47e9-b434-eaab7f47d311`), met de
verdicts leesbaar via `read_db` op collectie `decisions`.

- De twee reparaties uit punt 1: beide verplaatsen data van bestaande klanten.
- Het contrasigneren uit punt 4: LIVE vraagt haar handtekening, niet die van een
  agent.
- De begrippenkaart tussen nationale instrumenten — de Waterpas-tegenhanger laat
  zien waarom dit onderzoek is en geen opzoeking: dat een Belgische
  `bbib_percentage` het juiste antwoord is op een Nederlandse `expat_percentage`
  is een gelijkwaardigheidsclaim tussen twee nationale instrumenten.
