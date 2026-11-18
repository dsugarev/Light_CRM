# Import format (Excel or CSV)

Owner decision (requirements open question 2): no copies of the current trackers are shared, so this is the format to prepare data in. The import wizard (**Import**, Sales Managers and Admins) also offers the same columns as an Excel template with an instructions sheet, in English or Bulgarian (`GET /api/v1/imports/templates/{type}`).

**Files.** Excel (`.xlsx`, the first sheet) or CSV (UTF-8 or Windows-1251, comma or semicolon; detected automatically), at most 10 MB and 20,000 rows. The first row holds the column names. Columns may be in any order, and missing optional columns are fine. Columns named as below, in English or Bulgarian, are matched automatically; any other column can be mapped by hand in the wizard or ignored.

**Order.** Import organizations first: contacts, leads and opportunities refer to an organization by its registration number (EIK) or its exact name.

**Samples** (fictional data, ready to import in this order): [`organizations.csv`](import-samples/organizations.csv), [`contacts.csv`](import-samples/contacts.csv), [`leads.csv`](import-samples/leads.csv), [`opportunities.csv`](import-samples/opportunities.csv). A test imports them through the real API and expects every row to be valid.

**Common rules.**
- Duplicates: organizations by registration number or normalized name (Cyrillic and Latin spellings match), contacts by email. In the wizard, choose to skip them or update the existing records. Leads and opportunities are always created.
- Owner email: an active user's email; empty means the person importing.
- Amounts in EUR, with a dot or a comma for decimals; dates as `YYYY-MM-DD` or `DD.MM.YYYY`.
- Lists (industry, lead source, stage) accept the name in either language or the code, as configured under **Lists** and **Stages**.
- The preview shows each invalid row with the reason; strict import writes nothing while any row is invalid; an Admin can roll a whole batch back.


## Organizations / Организации

| Column (English) | Колона (български) | Required | Format |
|---|---|---|---|
| Name | Име | yes |  |
| Registration number (EIK) | ЕИК |  | 9 or 13 digits |
| VAT number | ДДС номер |  | BG followed by 9 or 10 digits |
| Industry | Отрасъл |  | Name or code from the Industries list |
| Size | Размер |  | 1-9, 10-49, 50-249 or 250+ |
| Website | Уебсайт |  | http(s)://… |
| Address | Адрес |  |  |
| Postal code | Пощенски код |  |  |
| City | Град |  |  |
| Country | Държава |  | Two letters, default BG |
| Owner email | Имейл на отговорника |  | Email of an active user; empty: the person importing |
| Notes | Бележки |  |  |

## Contacts / Контакти

| Column (English) | Колона (български) | Required | Format |
|---|---|---|---|
| First name | Име | yes |  |
| Last name | Фамилия | yes |  |
| Job title | Длъжност |  |  |
| Email | Имейл |  | Duplicates are found by email |
| Phone | Телефон |  |  |
| Organization | Организация |  | Registration number (EIK) or exact name of an existing organization |
| Notes | Бележки |  |  |

## Leads / Потенциални клиенти

| Column (English) | Колона (български) | Required | Format |
|---|---|---|---|
| Title | Заглавие | yes |  |
| Company | Фирма | yes |  |
| Contact person | Лице за контакт |  |  |
| Email | Имейл |  |  |
| Phone | Телефон |  |  |
| Source | Източник |  | Name or code from the Lead sources list |
| Estimated value (EUR) | Очаквана стойност (EUR) |  | e.g. 48000 or 48000.50 |
| Description | Описание |  |  |
| Owner email | Имейл на отговорника |  | Email of an active user; empty: the person importing |
| Organization | Организация |  | Registration number (EIK) or exact name of an existing organization |

## Opportunities / Възможности

| Column (English) | Колона (български) | Required | Format |
|---|---|---|---|
| Name | Име | yes |  |
| Organization | Организация | yes | Registration number (EIK) or exact name of an existing organization |
| Stage | Етап |  | Name of an open stage; empty: the first stage |
| Amount (EUR) | Сума (EUR) |  | e.g. 48000 or 48000.50 |
| Probability (%) | Вероятност (%) |  | 0-100; empty: the stage default |
| Expected close date | Очаквана дата на приключване |  | YYYY-MM-DD or DD.MM.YYYY |
| Next step | Следваща стъпка |  |  |
| Competitor | Конкурент |  |  |
| Description | Описание |  |  |
| Owner email | Имейл на отговорника |  | Email of an active user; empty: the person importing |
