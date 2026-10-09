"""Gregorian -> Jalali (Persian solar) date conversion, no dependencies."""

MONTHS = ["Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
          "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand"]


def to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_string(dt, fmt="text") -> str:
    """fmt: text = 16 Mehr 1405, numeric = 1405/07/16, both = 16 Mehr 1405 · 1405/07/16"""
    jy, jm, jd = to_jalali(dt.year, dt.month, dt.day)
    text, num = f"{jd} {MONTHS[jm - 1]} {jy}", f"{jy}/{jm:02d}/{jd:02d}"
    return num if fmt == "numeric" else f"{text} · {num}" if fmt == "both" else text


def gregorian_string(dt, fmt="text") -> str:
    """fmt: text = 8 October 2026, numeric = 2026/10/08, both = 8 October 2026 · 2026/10/08"""
    text, num = f"{dt.day} {dt.strftime('%B')} {dt.year}", dt.strftime("%Y/%m/%d")
    return num if fmt == "numeric" else f"{text} · {num}" if fmt == "both" else text
