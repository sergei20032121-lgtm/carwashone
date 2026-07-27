"""
Экспорт/импорт Excel для журналов "Учёт (автомойка)" и "Химчистка".

Формат — простой, один лист, заголовок + строки, с колонками ровно как в
ответах API (WalkInOrderOut / DryCleaningOrderOut). Экспортировал → открыл в
Excel → поправил/добавил строки → импортировал обратно — тот же формат.

Это НЕ то же самое, что app/scripts/import_uchet.py — тот скрипт разбирает
твой исходный многолистовой "Учёт.xlsx" (историческая миграция один раз).
Этот модуль — для повседневного экспорта/импорта уже нормализованных данных
через админку.
"""
import io
from datetime import date, datetime
from typing import List

import openpyxl
from openpyxl.utils import get_column_letter

WALKIN_HEADERS = [
    "Дата", "Время (текст)", "Услуга", "Доп. услуга",
    "Марка авто", "Сумма", "Контакт", "ID сотрудника",
]

DRYCLEANING_HEADERS = [
    "Дата", "Марка авто", "Работы", "Телефон",
    "Сумма", "З/п мастера", "ID сотрудника",
]


def _autofit(ws):
    for i, _ in enumerate(ws[1], start=1):
        ws.column_dimensions[get_column_letter(i)].width = 20


def export_walkin_xlsx(orders: List) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Учёт"
    ws.append(WALKIN_HEADERS)
    for o in orders:
        ws.append([
            o.order_date.isoformat() if o.order_date else "",
            o.time_note or "",
            o.service_name_raw or "",
            o.extra_service or "",
            o.car_model or "",
            o.amount or 0,
            o.contact_name or "",
            o.employee_id or "",
        ])
    _autofit(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_drycleaning_xlsx(orders: List) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Химчистка"
    ws.append(DRYCLEANING_HEADERS)
    for o in orders:
        ws.append([
            o.order_date.isoformat() if o.order_date else "",
            o.car_model or "",
            o.works_description or "",
            o.phone or "",
            o.amount or 0,
            o.employee_payout or "",
            o.employee_id or "",
        ])
    _autofit(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def parse_walkin_xlsx(file_bytes: bytes) -> List[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        order_date, time_note, service, extra, car, amount, contact, employee_id = (list(row) + [None] * 8)[:8]
        if not service or amount in (None, ""):
            continue
        rows.append({
            "order_date": _parse_date(order_date),
            "time_note": str(time_note) if time_note else None,
            "service_name_raw": str(service),
            "extra_service": str(extra) if extra else None,
            "car_model": str(car) if car else None,
            "amount": float(amount),
            "contact_name": str(contact) if contact else None,
            "employee_id": int(employee_id) if employee_id else None,
        })
    return rows


def parse_drycleaning_xlsx(file_bytes: bytes) -> List[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        order_date, car, works, phone, amount, payout, employee_id = (list(row) + [None] * 7)[:7]
        if not car or not works or amount in (None, ""):
            continue
        rows.append({
            "order_date": _parse_date(order_date),
            "car_model": str(car),
            "works_description": str(works),
            "phone": str(phone) if phone else None,
            "amount": float(amount),
            "employee_payout": float(payout) if payout not in (None, "") else None,
            "employee_id": int(employee_id) if employee_id else None,
        })
    return rows
