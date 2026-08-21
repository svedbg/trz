# -*- coding: utf-8 -*-
"""Общ модел за тестовите ведомости от втория комплект (structura).

Един източник на истина за:
  * ставките по двата режима на 2026 г. (references/stavki.md),
  * работните дни по месеци (чл. 154 КТ),
  * закръгляването,
  * „чистата" ведомост — как трябва да изглежда всеки ред, ако всичко е вярно.

Генераторът строи по този модел и после нарочно го чупи.
Тестът пресмята по същия модел и трябва да намери точно счупеното.

ВАЖНО за спорните места. Третирането на социалните разходи и на доходите в
натура има повече от едно защитимо четене (виж proverki.md, F10). Затова моделът
не фиксира кое е вярното: избира се `politika` за целия файл и се прилага
последователно. Тестът проверява **последователността**, не доктрината — точно
както е редно да се държи и скилът.
"""
from decimal import Decimal, ROUND_HALF_UP
import datetime

# ---------------------------------------------------------------- закръгляване

def r2(x):
    """Пари: до два знака, половинката нагоре. Не banker's rounding."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------- ставки
# references/stavki.md, сверка 21.08.2026. 2026 г. е разделена на два режима,
# защото бюджетът е приет късно: праговете се сменят от 01.08.2026.

REZHIMI = {
    "H1": dict(period="01.01–31.07.2026", max_osig=2111.64, mod_samoosig=550.66, mrz=620.20),
    "H2": dict(period="01.08–31.12.2026", max_osig=2300.00, mod_samoosig=620.20, mrz=620.20),
}

LICHNI = {                    # чл. 6, ал. 1 и ал. 3 КСО; ЗЗО — трета категория
    "pensii": 6.58,           # фонд „Пенсии", родени след 31.12.1959
    "ozm": 1.40,              # общо заболяване и майчинство
    "bezrab": 0.40,           # безработица
    "zo": 3.20,               # здравно осигуряване
    "upf": 2.20,              # ДЗПО — универсален пенсионен фонд
}
LICHNI_OBSHTO = 13.78         # контролната сума, която важи винаги

RABOTODATEL_DOO = 8.22 + 2.10 + 0.60      # 10.92 без ТЗПБ
RABOTODATEL_UPF = 2.80
RABOTODATEL_ZO = 4.80
TZPB_DIAPAZON = (0.40, 1.10)              # чл. 6, ал. 1, т. 5 КСО; % по КИД

DDFL = 0.10                               # ЗДДФЛ
KLAS_STAPKA = 0.6                         # ПМС № 147 — % за всяка година стаж
BOLN_DNI_RABOTODATEL = 2                  # чл. 40, ал. 5 КСО, от 01.01.2024
BOLN_PROCENT = 0.70                       # чл. 40, ал. 5 КСО
ZO_PRI_NERABOTOSPOSOBNOST = 4.80          # чл. 40, ал. 1, т. 5 ЗЗО — за сметка на работодателя
OBLEKCHENIE_LIMIT = 0.10                  # чл. 42, ал. 3 във вр. с чл. 19 ЗДДФЛ

# 60 лв. в евро. СТАТУС: за потвърждение — точното превалутиране е 30.6773,
# но не е сверено дали законодателят е закръглил прага. Виж stavki.md.
PRAG_SOTSIALNI_RAZHODI = 30.68

TOL = 0.02          # допустимо разминаване при пари
TOL_STROG = 0.005   # за сборове и контролни колони


def rezhim_za(godina, mesec):
    return "H1" if (godina, mesec) <= (2026, 7) else "H2"


# -------------------------------------------------------------- работни дни
# Официални празници 2026 г. Правилото на чл. 154, ал. 2 КТ: когато празникът
# е събота или неделя, първият следващ работен ден е неприсъствен.
PRAZNICI_2026_FIKSIRANI = [
    (1, 1), (3, 3), (5, 1), (5, 6), (5, 24), (9, 6), (9, 22), (12, 24), (12, 25), (12, 26),
]
PRAZNICI_2026_VELIKDEN = [(4, 10), (4, 12), (4, 13)]   # Разпети петък, Великден, Велики понеделник


def _nerabotni_2026():
    dni = set()
    for m, d in PRAZNICI_2026_FIKSIRANI:
        dt = datetime.date(2026, m, d)
        if dt.weekday() >= 5:                 # падне ли в събота/неделя
            while dt.weekday() >= 5 or dt in dni:
                dt += datetime.timedelta(days=1)
        dni.add(dt)
    for m, d in PRAZNICI_2026_VELIKDEN:
        dni.add(datetime.date(2026, m, d))
    return dni


NERABOTNI_2026 = _nerabotni_2026()


def rabotni_dni(godina, mesec):
    """Работни дни в месеца: делнични минус официалните празници."""
    d = datetime.date(godina, mesec, 1)
    n = 0
    while d.month == mesec:
        if d.weekday() < 5 and d not in NERABOTNI_2026:
            n += 1
        d += datetime.timedelta(days=1)
    return n


# ------------------------------------------------------------------- колони
# Широк западен layout — какъвто се среща при ведомости, водени в Excel от
# счетоводна къща. Заглавията са на български, но подредбата и наличието на
# помощни/контролни колони повтарят типичната конструкция.
KOLONI = [
    "№", "Име", "Отдел",
    "Отраб. дни", "Дни платен отпуск", "Дни болничен", "Дни майчинство",
    "Основна за отработеното", "Клас %", "Клас сума", "Бонус",
    "Платен отпуск", "Обезщетение чл. 224", "Болнични (работодател)",
    "БРУТО",
    "ДОО пенсии", "ДОО ОЗМ", "ДОО безработица", "ЗО лична", "ДЗПО-УПФ лична",
    "Лични вноски общо",
    "Осигурителен доход", "Данъчна основа", "ДДФЛ",
    "Удръжка доброволно осиг. (лична)", "Удръжка карта (лична част)",
    "НЕТО преди удръжки", "НЕТО за изплащане", "Изплатено", "Разлика",
    "Вноски работодател ДОО+ТЗПБ", "ДЗПО-УПФ работодател", "ЗО работодател",
    "ЗО при болничен/майчинство", "Вноски работодател общо",
    "Карта (за сметка на работодателя)", "Доброволно здравно осигуряване (премия)",
    "Общ разход за труд",
]
K = {ime: i + 1 for i, ime in enumerate(KOLONI)}          # име -> номер на колона (1-based)

NACHISLENIYA = ["Основна за отработеното", "Клас сума", "Бонус",
                "Платен отпуск", "Обезщетение чл. 224", "Болнични (работодател)"]
KOLONI_DNI = ["Отраб. дни", "Дни платен отпуск", "Дни болничен", "Дни майчинство"]
KOLONI_SBOR = [k for k in KOLONI if k not in ("№", "Име", "Отдел", "Клас %")]


# --------------------------------------------------------- чистата ведомост

def chist_red(vhod, rezhim, tzpb, politika, norma_dni):
    """Пресмята един коректен ред от входните данни.

    vhod: dict с mesechna_zaplata, klas_pr, dni_* , bonus, obezsht_224,
          karta_er, karta_ee, premia, lichna_vnoska
    politika: dict natura_v_bazite / previshenie_v_bazite (bool) — виж модула
    Връща dict: име на колона -> стойност.
    """
    ms = vhod["mesechna_zaplata"]
    kp = vhod["klas_pr"]
    wd, pl, sd, md = vhod["dni_rabota"], vhod["dni_otpusk"], vhod["dni_bolnichen"], vhod["dni_maychinstvo"]
    dneven = ms / norma_dni
    s_klas = 1 + kp / 100.0

    osnovna = r2(dneven * wd)
    klas = r2(osnovna * kp / 100.0)
    otpusk = r2(dneven * s_klas * pl)
    boln_dni_er = min(sd, BOLN_DNI_RABOTODATEL)
    bolnichni = r2(dneven * s_klas * boln_dni_er * BOLN_PROCENT)
    bonus = r2(vhod["bonus"])
    ob224 = r2(vhod["obezsht_224"])

    bruto = r2(osnovna + klas + bonus + otpusk + ob224 + bolnichni)

    # --- осигурителен доход -------------------------------------------------
    # Обезщетението по чл. 40, ал. 5 КСО не е осигурителен доход (НЕВДПОВ);
    # обезщетението по чл. 224 КТ също не е. И двете обаче са облагаеми.
    natura = r2(vhod["karta_er"]) if vhod["karta_er"] else 0.0
    premia = r2(vhod["premia"]) if vhod["premia"] else 0.0
    previshenie = r2(max(0.0, premia - PRAG_SOTSIALNI_RAZHODI)) if premia else 0.0

    baza_trud = r2(osnovna + klas + bonus + otpusk)
    if baza_trud <= 0:
        # лице без начисления за труд през месеца (цял месец в майчинство):
        # няма върху какво да се начисли осигурителен доход, придобивките не
        # създават осигурителен доход сами по себе си
        dobavki_v_osig = 0.0
    else:
        dobavki_v_osig = (natura if politika["natura_v_bazite"] else 0.0) \
                       + (previshenie if politika["previshenie_v_bazite"] else 0.0)
    osig = r2(min(rezhim["max_osig"], r2(baza_trud + dobavki_v_osig)))

    vnoski = {k: r2(osig * p / 100.0) for k, p in LICHNI.items()}
    lichni = r2(sum(vnoski.values()))

    # --- данъчна основа ----------------------------------------------------
    # Каквото влиза в осигурителния доход като доход в натура / превишение,
    # влиза и в данъчната основа. Обезщетенията и болничните са облагаеми.
    dan_baza_predi = r2(bruto + dobavki_v_osig - lichni)
    limit = r2(dan_baza_predi * OBLEKCHENIE_LIMIT)
    oblekchenie = r2(min(vhod["lichna_vnoska"], limit)) if vhod["lichna_vnoska"] else 0.0
    dan_osnova = r2(dan_baza_predi - oblekchenie)
    danak = r2(dan_osnova * DDFL)

    neto_predi = r2(bruto - lichni - danak)
    neto = r2(neto_predi - vhod["lichna_vnoska"] - vhod["karta_ee"])

    # --- вноски на работодателя -------------------------------------------
    er_doo = r2(osig * (RABOTODATEL_DOO + tzpb) / 100.0)
    er_upf = r2(osig * RABOTODATEL_UPF / 100.0)
    er_zo = r2(osig * RABOTODATEL_ZO / 100.0)
    zo_boln = r2(rezhim["mod_samoosig"] * ZO_PRI_NERABOTOSPOSOBNOST / 100.0
                 * (sd + md) / norma_dni) if (sd + md) else 0.0
    er_obshto = r2(er_doo + er_upf + er_zo + zo_boln)

    razhod = r2(bruto + er_obshto + natura + premia)

    return {
        "Отраб. дни": wd, "Дни платен отпуск": pl,
        "Дни болничен": sd, "Дни майчинство": md,
        "Основна за отработеното": osnovna, "Клас %": kp, "Клас сума": klas,
        "Бонус": bonus, "Платен отпуск": otpusk, "Обезщетение чл. 224": ob224,
        "Болнични (работодател)": bolnichni, "БРУТО": bruto,
        "ДОО пенсии": vnoski["pensii"], "ДОО ОЗМ": vnoski["ozm"],
        "ДОО безработица": vnoski["bezrab"], "ЗО лична": vnoski["zo"],
        "ДЗПО-УПФ лична": vnoski["upf"], "Лични вноски общо": lichni,
        "Осигурителен доход": osig, "Данъчна основа": dan_osnova, "ДДФЛ": danak,
        "Удръжка доброволно осиг. (лична)": r2(vhod["lichna_vnoska"]),
        "Удръжка карта (лична част)": r2(vhod["karta_ee"]),
        "НЕТО преди удръжки": neto_predi, "НЕТО за изплащане": neto,
        "Изплатено": neto, "Разлика": 0.0,
        "Вноски работодател ДОО+ТЗПБ": er_doo, "ДЗПО-УПФ работодател": er_upf,
        "ЗО работодател": er_zo, "ЗО при болничен/майчинство": zo_boln,
        "Вноски работодател общо": er_obshto,
        "Карта (за сметка на работодателя)": natura,
        "Доброволно здравно осигуряване (премия)": premia,
        "Общ разход за труд": razhod,
    }


# --------------------------------------------------------------- сценарии
# id -> (група, кратко описание). Групата съответства на proverki.md.
SCENARII = {
    "K1_sbor_izpuska_kolona":  ("K1", "брутото не включва всички колони за начисления"),
    "K2_suma_v_kolona_dni":    ("K2", "сума, въведена в колона за дни"),
    "K3_tvardi_stoynosti":     ("K3", "вноски като твърди стойности, изостанали от осигурителния доход"),
    "K4_kontrola_ne_hvashta":  ("K4", "контролна колона показва нула при налична разлика"),
    "K5_sbor_ne_e_sum":        ("K5", "сбор в реда ОБЩО, различен от сумата на клетките"),
    "K6_nezakraglen":          ("K6", "начисление с повече от два знака след десетичния знак"),
    "K7_razhod_ot_neto":       ("K7", "общият разход е изчислен от нетото след удръжките"),
    "F9_bolnichen_v_osig":     ("F9", "обезщетението по чл. 40, ал. 5 КСО е в осигурителния доход"),
    "F9_bolnichen_bez_danak":  ("F9", "обезщетението по чл. 40, ал. 5 КСО е извън данъчната основа"),
    "F9_bez_zo_bolnichen":     ("F9", "липсва ЗО по чл. 40, ал. 1, т. 5 ЗЗО за дните неработоспособност"),
    "F10_natura_asimetria":    ("F10", "доходът в натура е в едната база, но не в другата"),
    "F10_previshenie_asim":    ("F10", "превишението над необлагаемия праг е в едната база, но не в другата"),
    "F7_oblekchenie_nad_limit": ("F7", "данъчно облекчение над 10% от месечната данъчна основа"),
    "F5_tzpb_pod_dalzhimiya":  ("F5", "вноските на работодателя са с ТЗПБ под приложимия"),
    "B4_taван_ot_drug_period": ("B4", "приложен е максимален осигурителен доход от друг период"),
    "C2_klas_varhu_bruto":     ("C2", "класът е начислен върху брутото, не върху основната заплата"),
    "E3_otpusk_bez_klas":      ("E3", "платеният отпуск е без включен клас"),
    "I5_dni_ne_se_vrazvat":    ("I5", "сборът на дните не отговаря на нормата за месеца"),
}
