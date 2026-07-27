"""
Первичное заполнение базы данных.

Запуск:  python -m app.seed

Услуги химчистки и их ориентировочные цены посчитаны по факту из твоего
файла "Химчистка.xlsx" (среднее по 269 заказам за 2022–2023). Сотрудники —
из листа "График.xlsx". Поправь цифры и имена под актуальные, когда будет
время — это только стартовые данные, чтобы сайт и админка не были пустыми.
"""
from app.database import SessionLocal, Base, engine
from app.models import Service, ServiceCategory, Employee, User, UserRole, GisSettings, VkSettings
from app.security import hash_password
from app.config import settings

Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        if not db.query(Service).first():
            # (название, описание, цена, минуты, считается ли "полной мойкой" для карты)
            wash_services = [
                ("Экспресс", "Кузов, диски, окна и сушка вручную — когда важны минуты.", 350, 15, False),
                ("Комплекс", "Кузов и диски, химчистка ковриков, полировка стёкол, пылесос салона.", 900, 40, True),
                ("Детейлинг", "Глубокая чистка салона, полировка кузова, чернение резины и пластика.", 3500, 120, True),
                ("Защита (керамика/воск)", "Защитное покрытие с гидрофобным эффектом.", 2500, 90, True),
            ]
            for i, (name, desc, price, dur, counts) in enumerate(wash_services):
                db.add(Service(
                    category=ServiceCategory.WASH, name=name, description=desc,
                    price_from=price, duration_min=dur, sort_order=i,
                    counts_towards_loyalty=counts,
                ))

            # Прайс химчистки — временная заглушка (среднее по историческим заказам),
            # актуальный прайс пришлёшь отдельно и подставим вместо этого
            dry_services = [
                ("Химчистка сидений", "Чистка одного или нескольких сидений.", 2000, 40),
                ("Химчистка салона (полная)", "Полная химчистка сидений, ковриков, потолка и дверных карт.", 6500, 150),
                ("Химчистка ковров/коврика", "Отдельная чистка ковролина или ковриков.", 2500, 30),
                ("Химчистка чехлов", "Чистка чехлов сидений.", 5000, 60),
                ("Полировка кузова", "Полировка кузова с удалением мелких царапин.", 7500, 120),
                ("Полировка + керамика", "Полировка кузова с нанесением керамического покрытия.", 11500, 180),
                ("Предпродажная подготовка", "Комплексная подготовка авто к продаже: мойка, химчистка, полировка.", 7000, 180),
            ]
            for i, (name, desc, price, dur) in enumerate(dry_services):
                db.add(Service(
                    category=ServiceCategory.DRY_CLEANING, name=name, description=desc,
                    price_from=price, duration_min=dur, sort_order=i,
                    counts_towards_loyalty=False,
                ))
            db.commit()

        if not db.query(Employee).first():
            # Имена — с листа "График.xlsx"; должность и цвет можно поправить в админке
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
            print("Создан админ: логин 'admin', пароль 'admin' — ОБЯЗАТЕЛЬНО смени после первого входа.")

        if not db.query(GisSettings).first():
            db.add(GisSettings(org_url="https://go.2gis.com/TnzMN"))
            db.commit()

        if not db.query(VkSettings).first():
            db.add(VkSettings(
                group_domain=settings.vk_group_domain or "carwash_one_zkm",
                access_token=settings.vk_access_token,
            ))
            db.commit()

        print("Готово: услуги, сотрудники, админ и настройки 2ГИС созданы (если их ещё не было).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
