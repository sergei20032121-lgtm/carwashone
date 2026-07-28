"""
Первичное заполнение базы данных.

Запуск:  python -m app.seed

Прайс — реальный, снятый с прайс-листа группы ВК (не расчётный, как раньше).
Правило бонусной карты: комплексная (полная) мойка и всё, что дороже неё —
ставит ананас на карту. З/П мастера — 35% от цены услуги (применяется
автоматически при завершении записи/заказа, см. app/loyalty.py).
"""
from app.database import SessionLocal, Base, engine
from app.models import (
    Service, ServiceCategory, Employee, User, UserRole,
    GisSettings, VkSettings, BusinessSettings,
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
                ("Экспресс мойка авто", "Кузов, диски, окна и сушка вручную - когда важны минуты.", 900, 1400, 25, False),
                ("Сухой туман", "Устранение запахов в салоне парогенератором.", 400, None, 15, False),
                ("Покрытие кузова жидким воском", "Быстрая защита ЛКП с гидрофобным эффектом после мойки.", 300, None, 10, False),
                ("Комплексная (полная) мойка", "Кузов и диски, химчистка ковриков, полировка стёкол, пылесос салона.", 1300, 2100, 45, True),
                ("Премиум мойка авто", "Комплекс плюс расширенная обработка резины, пластика и стёкол.", 1900, 2500, 60, True),
            ]
            for i, (name, desc, price_from, price_to, dur, counts) in enumerate(wash_services):
                db.add(Service(
                    category=ServiceCategory.WASH, name=name, description=desc,
                    price_from=price_from, price_to=price_to, duration_min=dur, sort_order=i,
                    counts_towards_loyalty=counts, payout_pct=PAYOUT_PCT,
                ))

            dry_services = [
                ("Комплексная детейлинг", "Глубокая мойка и обработка кузова и салона выше уровня комплекса.", 2300, 3000, 90, True),
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

        if not db.query(Employee).first():
            employees = [
                ("Ваня", "Мойщик", "#1BE7A6"),
                ("Лариса", "Мойщик", "#FF6B4A"),
                ("Серёга", "Мойщик", "#3DD6FF"),
                ("Саша", "Мойщик", "#9B6BFF"),
                ("Даня", "Мойщик", "#7AA7E0"),
                ("Мастер химчистки", "Химчист", "#B478E0"),
            ]
            for name, position, color in employees:
                db.add(Employee(full_name=name, position=position, color_tag=color))
            db.commit()

        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin",
                full_name="Администратор",
                role=UserRole.ADMIN,
                password_hash=hash_password("admin"),
            ))
            db.commit()
            print("Создан админ: логин 'admin', пароль 'admin' - ОБЯЗАТЕЛЬНО смени после первого входа.")

        if not db.query(User).filter(User.username == "manager").first():
            db.add(User(
                username="manager",
                full_name="Руководитель",
                role=UserRole.MANAGER,
                password_hash=hash_password("manager"),
            ))
            db.commit()
            print("Создан руководитель: логин 'manager', пароль 'manager' - тоже смени после первого входа.")

        if not db.query(GisSettings).first():
            db.add(GisSettings(org_url="https://go.2gis.com/TnzMN"))
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
