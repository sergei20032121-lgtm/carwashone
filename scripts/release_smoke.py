#!/usr/bin/env python3
"""Read-only проверка production-сайта, API и разграничения ролей."""

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base_url, path, method="GET", payload=None, token=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw and "application/json" in response.headers.get("Content-Type", "") else None
            return response.status, parsed
    except HTTPError as error:
        raw = error.read()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        return error.code, parsed


def expect(checks, label, actual, expected):
    ok = actual == expected
    checks.append(ok)
    print(f"{'OK' if ok else 'FAIL'}  {label}: {actual} (ожидалось {expected})")


def login(base_url, login_name, password):
    status, data = request(base_url, "/auth/login", "POST", {"login": login_name, "password": password})
    if status != 200 or not data:
        raise RuntimeError(f"Не удалось войти как {login_name}: HTTP {status}")
    return data["access_token"], data["role"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://carwashone.ru")
    args = parser.parse_args()
    checks = []

    for path in ("/site/", "/site/privacy.html", "/site/consent.html", "/services", "/dry-cleaning/services"):
        status, _ = request(args.base_url, path)
        expect(checks, f"GET {path}", status, 200)

    status, _ = request(args.base_url, "/auth/otp/request", "POST", {"phone": "+79990001122"})
    expect(checks, "OTP без согласия отклонён", status, 422)

    admin_password = os.getenv("ADMIN_PASSWORD")
    manager_password = os.getenv("MANAGER_PASSWORD")
    if admin_password:
        token, role = login(args.base_url, "admin", admin_password)
        expect(checks, "роль admin", role, "admin")
        status, _ = request(args.base_url, "/admin/business-settings", token=token)
        expect(checks, "admin читает настройки", status, 200)
    else:
        print("SKIP  ADMIN_PASSWORD не передан")

    if manager_password:
        token, role = login(args.base_url, "manager", manager_password)
        expect(checks, "роль manager", role, "manager")
        status, _ = request(args.base_url, "/admin/manager/dashboard", token=token)
        expect(checks, "manager читает дашборд", status, 200)
        status, _ = request(args.base_url, "/admin/business-settings", token=token)
        expect(checks, "manager не читает настройки admin", status, 403)
    else:
        print("SKIP  MANAGER_PASSWORD не передан")

    if not all(checks):
        return 1
    print("Все выполненные release-проверки пройдены.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (URLError, RuntimeError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        raise SystemExit(1)
