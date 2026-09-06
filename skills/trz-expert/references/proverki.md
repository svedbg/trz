# Чеклист от проверки

Всяка проверка има изричен резултат — един от пет:

- **преминава** — проверено и наред;
- **не преминава** — находка, по формата в `SKILL.md`;
- **недостатъчни данни** — проверката е приложима, но липсва нещо, за да се произнесеш.
  Назови какво точно: „B3 — недостатъчни данни: липсват КИД на дружеството и
  квалификационната група“;
- **непроверимо** — документът е **подаден, но не става за проверка**: сканиран PDF без
  разпознат текст, експорт само със стойности там, където проверката иска формули, слети
  клетки, които разместват редовете, повреден файл, колони без разбираемо име, формули без
  запазен резултат. Не е същото като „недостатъчни данни“ и лекът е друг: там се иска
  липсващ документ, тук — по-добър експорт на същия. Кажи кое качество пречи и какво би
  свършило работа;
- **неприложима** — материята я няма в този случай: няма дежурство, няма запор, няма
  прекратяване през периода. Назови причината, но не искай документ — такъв не се дължи.

`scripts/preflight.py` именно това съобщава, преди одитът да тръгне:
`NO_FORMULAS`, `MERGED_IN_DATA`, `NO_CACHED_VALUES`, `ERROR_CELLS` и `NUMBERS_AS_TEXT`
са „непроверимо“; липсващият КИД е „недостатъчни данни“. Пусни го и вземи състоянията
оттам, вместо да ги установяваш наново.

**`EXTERNAL_LINKS` също е „непроверимо“ за колоните, които зависят от връзката:** числото
е пресметнато във файл, който не е подаден, и стойността в клетката е последното, което
Excel е запазил. Кажи кои колони зависят от нея.

**`HIDDEN_SHEET`, `HIDDEN_ROWS` и `HIDDEN_COLUMNS` не са нито едно от петте.** Скрит лист и скрит ред в
данните не пречат на проверката — те са съдържание на файла, което читателят не вижда, а
проверяваната страна е избрала да скрие. Прегледай ги наравно с останалото и ги посочи с
тежест `бележка`: кой лист, кои редове и колони, и влизат ли в сборовете. Мълчанието по тях е
единственият начин отчетът да излезе верен и въпреки това подвеждащ.

Разликата между „неприложима“ и другите два резултата, при които проверката не се е
състояла, не е формална. „Неприложима“ казва, че няма какво да се проверява; „недостатъчни
данни“ и „непроверимо“ казват, че има какво, но нещо пречи — и точно тези редове са
списъкът, с който завършва отчетът. Проверка,
отчетена като неприложима, когато всъщност липсва документ или подаденият не става за
четене, скрива дупка зад думата „няма“ и потребителят чете отчета по-спокойно, отколкото
данните позволяват. Не пропускай проверка мълчаливо.

**Резултатът и тежестта са две различни оси.** Резултатът казва какво е станало с
проверката; тежестта — колко категорична е находката, ако има такава. Връзката между тях е
една: **недостатъчни данни** и **непроверимо** дават находка с тежест `за проверка`,
назоваваща какво липсва или какво пречи, когато то може да промени число; **неприложима**
не дава находка изобщо.

Нормативните основания са в `normativna-baza.md`. Ставките са в `stavki.md` — не ги
дублирай тук и не ги пиши по памет.

---

## Проверки по групи

Пълният текст на всяка проверка — основание, аритметика, пример — е в
`references/proverki/`, по един файл на буква (`a.md`…`k.md`). Тук стои само заглавието,
за да се решава по стъпка 3а кои групи остават „проверява се“, преди да се отваря пълният
текст само на тях.

## A. Трудов договор и допълнителни споразумения

*Employment contract and its annexes*

- **A1. Съществени елементи** · *Required contract elements.*
- **A2. Липсващ елемент, който се появява във ведомостта** · *An element absent from the contract but paid in the payroll.*
- **A3. Изпитателен срок** · *Probation period.*
- **A4. Срочност** · *Fixed-term contracts.*
- **A5. Вписване в регистъра на заетостта** · *Registration in the employment register.*
- **A6. Съответствие договор ↔ ведомост** · *Contract against payroll.*
- **A7. НКПД и категория труд** · *Occupation code and labour category.*
- **A8. Гражданско вместо трудово правоотношение** · *A civil contract in place of employment.*
- **A9. Основни данни на лицето** · *Employee master data.*
- **A10. Споразумение, влизащо в сила в средата на месеца** · *An annex effective mid-month.*

→ пълен текст с основание, аритметика и пример: `references/proverki/a.md`

## B. Минимални прагове

*Minimum thresholds*

- **B1. МРЗ** · *Minimum wage.*
- **B2. Часова ставка** · *Hourly rate.*
- **B3. МОД** · *Minimum insurable income by economic activity.*
- **B4. Максимален осигурителен доход** · *Maximum insurable income.*
- **B5. МРЗ срещу МОД** · *Minimum wage against the insurable minimum.*
- **B6. Няколко правоотношения на едно лице** · *One person, several relationships.*

→ пълен текст с основание, аритметика и пример: `references/proverki/b.md`

## C. Структура на възнаграждението

*Structure of the remuneration*

- **C1. Клас прослужено време** · *Length-of-service supplement.*
- **C2. База за класа** · *Base the supplement is computed on.*
- **C3. Актуализация при годишнина** · *Increase on each anniversary.*
- **C4. Постоянни допълнителни възнаграждения** · *Permanent supplements and the bases they enter.*
- **C5. Възнаграждение, маскирано като бонус** · *Remuneration disguised as a bonus.*
- **C6. Вътрешни правила за работната заплата** · *Internal wage rules.*

→ пълен текст с основание, аритметика и пример: `references/proverki/c.md`

## D. Работно време, извънреден и нощен труд

*Working time, overtime and night work*

- **D1. Отчетност** · *Time records.*
- **D2. Наличие на извънреден труд** · *Unrecorded overtime.*
- **D3. Лимити** · *Statutory overtime limits.*
- **D4. Заплащане на извънредния труд** · *Overtime premium.*
- **D5. СИРВ** · *Aggregated calculation of working time.*
- **D6. Нощен труд** · *Night work.*
- **D7. Официални празници** · *Work on public holidays.*
- **D8. Междудневна и седмична почивка** · *Daily and weekly rest.*
- **D9. Дежурство и разположение** · *On-call duty and standby.*
- **D10. Непълно работно време** · *Part-time work.*
- **D11. Почивният ден по календар не е почивният ден на лицето** · *A calendar rest day is not necessarily the person's rest day.*

→ пълен текст с основание, аритметика и пример: `references/proverki/d.md`

## E. Отпуски

*Leave*

- **E1. Размер на платения годишен отпуск** · *Annual leave entitlement.*
- **E2. Пропорционалност** · *Pro-rating on joining or leaving.*
- **E3. Възнаграждение по време на отпуск** · *Pay during leave.*
- **E4. Ползване и погасяване** · *Taking leave and time-barring.*
- **E5. Неплатен отпуск** · *Unpaid leave.*
- **E6. Отпуск при СИРВ** · *Leave under aggregated working time.*

→ пълен текст с основание, аритметика и пример: `references/proverki/e.md`

## F. Осигуряване и данък

*Contributions and tax*

- **F1. Осигурителен доход** · *Insurable income.*
- **F2. Разпределение на вноските** · *Employer/employee split of the contributions.*
- **F3. Осигурителен режим по възраст** · *Contribution regime by date of birth.*
- **F4. Категория труд** · *Labour category.*
- **F5. ТЗПБ** · *Accident and occupational disease rate.*
- **F6. Данъчна основа** · *Taxable base.*
- **F7. Данъчни облекчения** · *Tax reliefs.*
- **F8. Годишно изравняване** · *Annual reconciliation.*
- **F9. Болнични** · *Sick pay.*
- **F10. Социални разходи и доходи в натура** · *Social expenses and income in kind.*

→ пълен текст с основание, аритметика и пример: `references/proverki/f.md`

## G. Удръжки и запори

*Deductions and attachments*

- **G1. Основание** · *Legal basis for each deduction.*
- **G2. Несеквестируем доход** · *Protected minimum income.*
- **G3. Ред на удовлетворяване** · *Order of competing attachments.*
- **G4. Удръжки за липси и щети** · *Deductions for shortages and damage.*
- **G5. Прихващане** · *Unilateral set-off.*

→ пълен текст с основание, аритметика и пример: `references/proverki/g.md`

## H. Прекратяване и обезщетения

*Termination and severance*

- **H1. Основание за прекратяване** · *Ground for termination.*
- **H2. Обезщетение за неспазено предизвестие** · *Payment in lieu of notice.*
- **H3. Обезщетение при уволнение на определени основания** · *Severance on specified grounds.*
- **H4. Обезщетение за неползван платен отпуск** · *Compensation for untaken leave.*
- **H5. База за обезщетенията** · *Base the severance is computed on.*
- **H6. Срок за изплащане** · *Deadline for paying severance.*
- **H7. Трудова книжка и удостоверения** · *Employment record book and certificates.*

→ пълен текст с основание, аритметика и пример: `references/proverki/h.md`

## I. Аритметична и междудокументна консистентност

*Arithmetic and cross-document consistency*

- **I1. Вертикална сверка на фиша** · *Vertical reconciliation of the payslip.*
- **I2. Хоризонтална сверка** · *Horizontal reconciliation.*
- **I3. Рекапитулация** · *Payroll against the recapitulation.*
- **I4. Ведомост ↔ фиш** · *Payroll against the payslip.*
- **I5. Ведомост ↔ график ↔ присъствена форма** · *Payroll against the schedule and the time sheet.*
- **I6. Ведомост ↔ декларации** · *Payroll against the filed declarations.*
- **I7. Месец към месец** · *Month against month.*
- **I8. Дублирани лица** · *Duplicated people.*
- **I9. Ведомост ↔ обр. 1 ↔ обр. 6 ↔ внесено ↔ счетоводство** · *Payroll through the declarations to the payment and the ledger.*
- **I10. Дублирани договори и плащания** · *Duplicated contracts and payments.*
- **I11. Хронология на лицето през месеците** · *One person's timeline across months.*

→ пълен текст с основание, аритметика и пример: `references/proverki/i.md`

## J. Срокове и формалности

*Deadlines and formalities*

- **J1. Срок за изплащане на заплатата** · *Wage payment deadline.*
- **J2. Форма на плащане** · *Form of payment.*
- **J3. Фиш за заплата** · *Payslip issuance.*
- **J4. Досие на работника** · *Personnel file.*

→ пълен текст с основание, аритметика и пример: `references/proverki/j.md`

## K. Конструкция на файла

*Construction of the file*

- **K1. Обхват на сумите** · *Scope of every sum.*
- **K2. Сума в колона за дни и обратно** · *An amount in a day column, and the reverse.*
- **K3. Твърди стойности вместо формули** · *Hardcoded values instead of formulas.*
- **K4. Работят ли контролите** · *Whether the controls control anything.*
- **K5. Сборове, вписани на ръка** · *Hand-typed totals.*
- **K6. Закръгляване** · *Rounding.*
- **K7. Разход за труд** · *Cost of labour.*
- **K8. Няколко листа в един файл** · *Several sheets in one file.*
- **K9. Няколко редакции на един и същи файл** · *Several revisions of the same file.*
- **K10. Наименования на колоните** · *Column names.*

→ пълен текст, плюс „Как се чете електронна таблица“ (техниката на четене — два пъти, веднъж за стойностите и веднъж за формулите) и „Формули“ (контролните изрази): `references/proverki/k.md`
