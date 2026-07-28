"""
Первичное заполнение базы данных.

Запуск:  python -m app.seed

Прайс — реальный, снятый с прайс-листа группы ВК (не расчётный, как раньше).
Правило бонусной карты: комплексная (полная) мойка и всё, что дороже неё —
ставит ананас на карту. З/П мастера — 35% от цены услуги (применяется
автоматически при завершении записи/заказа, см. app/loyalty.py).
"""
from datetime import date
import secrets
from app.database import SessionLocal, Base, engine
from app.models import (
    Service, ServiceCategory, Employee, User, UserRole,
    GisSettings, VkSettings, BusinessSettings, ShiftSchedule, ShiftType,
)
from app.security import hash_password
from app.config import settings

Base.metadata.create_all(bind=engine)

PAYOUT_PCT = 35  # % от цены услуги — з/п мастера, по всем услугам одинаково


def seed():
    db = SessionLocal()
    try:
        if not db.query(Service).first():
            # (название, описание, price_from, price_to, минуты, ставит ли ананас)
            # price_to = None означает "от X", иначе показывается вилка "X-Y"
            wash_services = [
                ("Облив авто водой", "Быстрое ополаскивание кузова водой без химии.", 250, None, 10, False),
                ("Бесконтактная мойка", "Мойка кузова активной пеной без соприкосновения щёток с ЛКП.", 350, 500, 20, False),
                ("Экспресс мойка авто", "Двухфазная мойка кузова и протирка — когда важны минуты.", 800, None, 25, False),
                ("Сухой туман", "Устранение запахов в салоне парогенератором.", 400, None, 15, False),
                ("Покрытие кузова жидким воском", "Быстрая защита ЛКП с гидрофобным эффектом после мойки.", 300, None, 10, False),
                ("Комплексная (полная) мойка", "Кузов, диски, коврики, проёмы, пороги, пылесос и влажная уборка салона.", 1200, None, 45, True),
                ("Детейлинг экспресс мойка", "Двухфазная мойка, проёмы, диски, турбосушка, стёкла, коврики и чернение резины.", 1400, None, 40, True),
                ("Премиум мойка авто", "Комплекс плюс расширенная обработка резины, пластика и стёкол.", 1900, 2500, 60, True),
            ]
            for i, (name, desc, price_from, price_to, dur, counts) in enumerate(wash_services):
                db.add(Service(
                    category=ServiceCategory.WASH, name=name, description=desc,
                    price_from=price_from, price_to=price_to, duration_min=dur, sort_order=i,
                    counts_towards_loyalty=counts, payout_pct=PAYOUT_PCT,
                ))

            dry_services = [
                ("Комплексная детейлинг мойка", "Двухфазная мойка, гидрофобный состав, диски, педали, проёмы, турбосушка и уборка салона.", 2100, None, 90, True),
                ("Химчистка кузова авто", "Химчистка внешних пластиковых и резиновых элементов кузова.", 3000, 5000, 90, True),
                ("Полировка кузова", "Полировка кузова с удалением мелких царапин и потёртостей.", 6000, 14000, 180, True),
                ("Химчистка салона авто", "Полная химчистка сидений, ковриков, потолка и дверных карт.", 9000, None, 240, True),
                ("Керамическое покрытие", "Долговременное защитное керамическое покрытие кузова.", 20000, 40000, 360, True),
            ]
            for i, (name, desc, price_from, price_to, dur, counts) in enumerate(dry_services):
                db.add(Service(
                    category=ServiceCategory.DRY_CLEANING, name=name, description=desc,
                    price_from=price_from, price_to=price_to, duration_min=dur, sort_order=i,
                    counts_towards_loyalty=counts, payout_pct=PAYOUT_PCT,
                ))
            db.commit()

        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_password = (
                settings.admin_password
                if settings.admin_password != "change-me"
                else secrets.token_urlsafe(12)
            )
            admin_user = User(
                username="admin",
                full_name="Администратор",
                role=UserRole.ADMIN,
                password_hash=hash_password(admin_password),
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"Создан админ: логин 'admin', временный пароль: {admin_password}")

        if not db.query(Employee).first():
            employees = [
                ("Ваня", "Мойщик", "#1BE7A6", False),
                ("Лариса", "Мойщик", "#FF6B4A", False),
                ("Серёга", "Мойщик", "#3DD6FF", False),
                ("Саша", "Мойщик", "#9B6BFF", False),
                ("Даня", "Мойщик", "#7AA7E0", False),
                ("Мастер химчистки", "Химчист", "#B478E0", False),
            ]
            for name, position, color, is_admin in employees:
                db.add(Employee(full_name=name, position=position, color_tag=color, is_admin_role=is_admin))

            # отдельная запись сотрудника-администратора смены, привязанная к User admin —
            # именно по ней считается 5% с машины + 1000₽/день, когда у него стоит смена в графике
            db.add(Employee(
                full_name=admin_user.full_name or "Администратор",
                position="Администратор", color_tag="#E3B98A",
                is_admin_role=True, user_id=admin_user.id,
            ))
            db.commit()

            # смена на сегодня всем — чтобы дневной/недельный отчёт по зарплате
            # сразу показывал живые данные, а не пустоту
            for emp in db.query(Employee).all():
                db.add(ShiftSchedule(employee_id=emp.id, work_date=date.today(), shift_type=ShiftType.FULL_DAY))
            db.commit()

        if not db.query(User).filter(User.username == "manager").first():
            manager_password = (
                settings.manager_password
                if settings.manager_password != "change-me"
                else secrets.token_urlsafe(12)
            )
            db.add(User(
                username="manager",
                full_name="Руководитель",
                role=UserRole.MANAGER,
                password_hash=hash_password(manager_password),
            ))
            db.commit()
            print(f"Создан руководитель: логин 'manager', временный пароль: {manager_password}")

        if not db.query(GisSettings).first():
            # Рейтинг и количество оценок проверены по публичной карточке 2ГИС 28.07.2026.
            # До подключения API их можно обновлять вручную в админке.
            db.add(GisSettings(
                org_id="70000001054541469",
                org_url="https://go.2gis.com/Q4DrY",
                rating=4.9,
                reviews_count=153,
            ))
            db.commit()

        if not db.query(VkSettings).first():
            db.add(VkSettings(
                group_domain=settings.vk_group_domain or "carwash_one_zkm",
                access_token=settings.vk_access_token,
            ))
            db.commit()

        if not db.query(BusinessSettings).first():
            db.add(BusinessSettings(monthly_revenue_target=500000))
            db.commit()

        print("Готово: услуги (12 позиций реального прайса), сотрудники, админ, руководитель и настройки созданы.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
