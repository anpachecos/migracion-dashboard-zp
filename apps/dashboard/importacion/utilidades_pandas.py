"""Utilidades para transformar celdas de DataFrames de pandas."""

import pandas as pd


def texto(valor):
    if valor is None:
        return ""

    if pd.isna(valor):
        return ""

    return str(valor).strip()


def valor_entero(valor):
    if valor is None or pd.isna(valor):
        return None

    try:
        return int(float(valor))
    except (ValueError, TypeError):
        return None


def numero_igual(valor_1, valor_2):
    if valor_1 is None and valor_2 is None:
        return True

    if valor_1 is None or valor_2 is None:
        return False

    try:
        return round(float(valor_1), 7) == round(float(valor_2), 7)
    except (ValueError, TypeError):
        return False