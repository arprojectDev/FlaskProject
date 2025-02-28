from app import app, db, User  # Импортируем Flask-приложение
from werkzeug.security import generate_password_hash

# Открываем контекст приложения
with app.app_context():
    # Удаляем всех пользователей (если нужно)
   # User.query.delete()
   # db.session.commit()

    # Создаём нового пользователя
    admin = User(username="admin", password=generate_password_hash("pass"), role = "admin", name = "Администратор")
    db.session.add(admin)
    db.session.commit()
    print("Пользователь создан!")
