#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка I/M3/M4/G/K/D на исторических векторах. Запуск: python test_vectors.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from enigma import REFLECTORS, ROTORS, EnigmaCommercial, EnigmaG, EnigmaMachine, _c2i


def check(name, got, want_prefix=None, want_exact=None):
    ok = True
    if want_exact is not None:
        ok = got == want_exact
    if want_prefix is not None:
        ok = got.startswith(want_prefix)
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    print(f"  -> {got[:100]}")
    if not ok:
        if want_exact is not None:
            print(f"  expected: {want_exact[:100]}")
        if want_prefix is not None:
            print(f"  expected start: {want_prefix}")
    return ok


CIPHER_U264 = (
    "NCZW VUSX PNYM INHZ XMQX SFWX WLKJ AHSH NMCO CCAK UQPM KCSM "
    "HKSE INJU SBLK IOSX CKUB HMLL XCSJ USRR DVKO HULX WCCB GVLI "
    "YXEO AHXR HKKF VDRE WEZL XOBA FGYU JQUK GRTV UKAM EURB VEKS "
    "UHHV OYHA BCJW MAKL FKLM YFVN RIZR VVRT KOFD ANJM OLBG FFLE "
    "OPRG TFLV RHOW OPBE KVWM UQFM PWPA RMFH AGKX IIBG"
)

all_ok = True

# M3 sanity: AAAAA -> BDZGO
m = EnigmaMachine(rotors=("I", "II", "III"), reflector="B", rings="AAA", positions="AAA")
all_ok &= check("M3 AAAAA->BDZGO", m.encipher("AAAAA"), want_exact="BDZGO")

# Совместимость M4 с M3 (cryptomuseum.com/crypto/enigma/m4):
# Beta + Thin-B в позиции A == толстый B; Gamma + Thin-C в позиции A == толстый C
def _combo(greek, thin):
    gw = [_c2i(c) for c in ROTORS[greek][0]]
    inv = [0] * 26
    for i, w in enumerate(gw):
        inv[w] = i
    th = [_c2i(c) for c in REFLECTORS[thin]]
    return "".join(chr(inv[th[gw[c]]] + 65) for c in range(26))


all_ok &= check("Beta+Thin-B == B", _combo("BETA", "THIN-B"), want_exact=REFLECTORS["B"])
all_ok &= check("Gamma+Thin-C == C", _combo("GAMMA", "THIN-C"), want_exact=REFLECTORS["C"])

# M4: реальное сообщение U-264 (Looks), 25.11.1942, перехват HMS Hurricane.
# Исторический ключ (M4 Project, взлом 2006, Erskine 1995):
# Thin-B, Beta II IV I, кольца AAAV, старт VJNA, штекеры AT BL DF GJ HM NW OP QY RZ VX
m1 = EnigmaMachine(
    rotors=("Beta", "II", "IV", "I"),
    reflector="Thin-B",
    rings="AAAV",
    positions="VJNA",
    plugs="AT BL DF GJ HM NW OP QY RZ VX",
)
plain1 = m1.decipher(CIPHER_U264)
all_ok &= check("M4 U-264 (1942) VONVONJLOOKS", plain1, want_prefix="VONVONJLOOKS")

# M4 roundtrip тем же ключом
m3 = EnigmaMachine(
    rotors=("Beta", "II", "IV", "I"), reflector="Thin-B",
    rings="AAAV", positions="VJNA", plugs="AT BL DF GJ HM NW OP QY RZ VX",
)
c = m3.encipher("VONKPTLTLOOKS")
m4 = EnigmaMachine(
    rotors=("Beta", "II", "IV", "I"), reflector="Thin-B",
    rings="AAAV", positions="VJNA", plugs="AT BL DF GJ HM NW OP QY RZ VX",
)
all_ok &= check("M4 roundtrip", m4.decipher(c), want_exact="VONKPTLTLOOKS")

# Тест 2: приказ Дёница (P1030681), найден на U-534, отправлен 01.05.1945.
# Thin-C + Beta V VI VIII, кольца EPEL, ключ сообщения CDSZ
# (индикатор DUHF TETO -> QEOB -> CDSZ при Grundstellung NAEM),
# штекеры AE BF CM DQ HU JN LX PR SZ VW. Первые 2 и последние 2 группы
# исходного перехвата — индикатор, в шифротекст ниже не входят.
CIPHER_DOENITZ = (
    "LANO TCTO UARB BFPM HPHG CZXT DYGA HGUF XGEW KBLK GJWL QXXT "
    "GPJJ AVTO CKZF SLPP QIHZ FXOE BWII EKFZ LCLO AQJU LJOY HSSM "
    "BBGW HZAN VOII PYRB RTDJ QDJJ OQKC XWDN BBTY VXLY TAPG VEAT "
    "XSON PNYN QFUD BBHH VWEP YEYD OHNL XKZD NWRH DUWU JUMW WVII "
    "WZXI VIUQ DRHY MNCY EFUA PNHO TKHK GDNP SAKN UAGH JZSM JBMH "
    "VTRE QEDG XHLZ WIFU SKDQ VELN MIMI THBH DBWV HDFY HJOQ IHOR "
    "TDJD BWXE MEAY XGYQ XOHF DMYU XXNO JAZR SGHP LWML RECW WUTL "
    "RTTV LBHY OORG LGOW UXNX HMHY FAAC QEKT HSJW"
)
m5 = EnigmaMachine(
    rotors=("Beta", "V", "VI", "VIII"),
    reflector="Thin-C",
    rings="EPEL",
    positions="CDSZ",
    plugs="AE BF CM DQ HU JN LX PR SZ VW",
)
plain2 = m5.decipher(CIPHER_DOENITZ)
all_ok &= check("M4 Doenitz P1030681", plain2,
                want_prefix="KRKRALLEXXFOLGENDESISTSOFORTBEKANNTZUGEBEN")

# Процедура индикатора: QEOB на Grundstellung NAEM открывает ключ CDSZ
m6 = EnigmaMachine(
    rotors=("Beta", "V", "VI", "VIII"),
    reflector="Thin-C",
    rings="EPEL",
    positions="NAEM",
    plugs="AE BF CM DQ HU JN LX PR SZ VW",
)
all_ok &= check("M4 indicator QEOB->CDSZ", m6.decipher("QEOB"), want_exact="CDSZ")

# --- Enigma I: тестовое сообщение 1930 г. (Schlüsselanleitung Enigma I),
# UKW-A, колёса II I III, кольца XMV, старт FOL, 6 штекеров.
# Индикатор PKPJXI -> ABLABL (удвоенный ключ ABL).
mi = EnigmaMachine(rotors=("II", "I", "III"), reflector="A", rings="XMV",
                   positions="FOL", plugs="AM FI NV PS TU WZ", model="I")
all_ok &= check("I indicator PKPJXI->ABLABL", mi.decipher("PKPJXI"), want_exact="ABLABL")
mi2 = EnigmaMachine(rotors=("II", "I", "III"), reflector="A", rings="XMV",
                    positions="ABL", plugs="AM FI NV PS TU WZ", model="I")
all_ok &= check("I 1930 FEINDLIQE...", mi2.decipher(
    "GCDSEAHUGWTQGRKVLFGXUCALXVYMIGMMNMFDXTGNVHVRMMEVOUYFZSLRHDRRXFJWCFHUHMUNZEF"
    "RDISIKBGPMYVXUZ"), want_exact="FEINDLIQEINFANTERIEKOLONNEBEOBAQTETXANFANGSUED"
    "AUSGANGBAERWALDEXENDEDREIKMOSTWAERTSNEUSTADT")

# --- Enigma I: валидация (роторы VI–VIII запрещены, UKW-A разрешён)
try:
    EnigmaMachine(rotors=("VI", "II", "III"), reflector="B", rings="AAA",
                  positions="AAA", model="I")
    all_ok &= check("I rejects VI", "no-error", want_exact="error")
except ValueError:
    all_ok &= check("I rejects VI", "error", want_exact="error")

# --- Enigma G: таблица шага из Examples/Notches (G312, III II I, NZAM),
# включая Lobster (все 4 ротора) на шаге 5: NACQ -> OBDR.
g = EnigmaG("G312", ("III", "II", "I"), "AAAA", "NZAM")
gseq = [g.positions]
for _ in range(10):
    g.press("A")
    gseq.append(g.positions)
all_ok &= check("G312 step table", " ".join(gseq), want_exact="NZAM NZAN NZAO NABP NACQ "
              "OBDR OBDS OCET OCEU OCFV ODGW")

# --- Enigma G: roundtrip всех 3 вариантов проводок
for variant in ("G", "G312", "G260"):
    ga = EnigmaG(variant, ("II", "III", "I"), "BCDA", "WXYZ")
    gc = ga.encipher("ANGRIFFBEIXUHROST")
    gb = EnigmaG(variant, ("II", "III", "I"), "BCDA", "WXYZ")
    all_ok &= check(f"G {variant} roundtrip", gb.decipher(gc),
                    want_exact="ANGRIFFBEIXUHROST")

# --- Commercial K/D: roundtrip; K отличается от M3 (другие ETW/проводка)
for model in ("K", "D"):
    ka = EnigmaCommercial(model, ("I", "II", "III"), "AAA", "AAA", "A", "A")
    kc = ka.encipher("WETTERMELDUNGXGEHEIMX")
    kb = EnigmaCommercial(model, ("I", "II", "III"), "AAA", "AAA", "A", "A")
    all_ok &= check(f"Commercial {model} roundtrip", kb.decipher(kc),
                    want_exact="WETTERMELDUNGXGEHEIMX")
all_ok &= check("K AAAAA != M3", EnigmaCommercial(
    "K", ("I", "II", "III"), "AAA", "AAA").encipher("AAAAA"), want_exact="JTOUN")

print("ALL OK" if all_ok else "SOME TESTS FAILED")
sys.exit(0 if all_ok else 1)
