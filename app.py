from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.sql import text, func, desc
from sqlalchemy.sql.expression import quoted_name
from collections import defaultdict
import re
import calendar

# Создаём Flask приложение
app = Flask(__name__)
app.config.from_pyfile("config.py")

# Подключение к базе MSSQL
db = SQLAlchemy(app)

# Настройка авторизации
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---- Модель пользователя ----
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # Хранение пароля в зашифрованном виде
    role = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(255), nullable=False)

# ---- Модель компании ----
class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

# ---- Модель налогов ----
class TaxTable(db.Model):
    __tablename__ = quoted_name('taxtable', quote=True)
    __table_args__ = (
        {'schema': quoted_name('_ext', quote=True)}
    )

    _period = db.Column(db.Date, nullable=False, primary_key=True)
    ref_id = db.Column(db.Integer, nullable=False, primary_key=True)
    org_id = db.Column(db.Integer, nullable=False, primary_key=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    users_id = db.Column(db.Integer, nullable=False)


# ---- Модель справочника налогов ----
class ReferenceTax(db.Model):
    
    __tablename__ = "_ReferenceTax"
    __table_args__ = {"schema": "dbo"}  # Указываем схему

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parent_id = db.Column(db.Integer, nullable=True)
    order_acc = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(255), nullable=False)
    group_name = db.Column(db.String(255), nullable=True)
    first_level_name = db.Column(db.String(255), nullable=True)
    table_reference = db.Column(db.String(255), nullable=True)



# Функция загрузки пользователя
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # ✅ Обновляем

@app.route("/add_reference_tax", methods=["POST"])
@login_required
def add_reference_tax():
    if current_user.role != "admin":
        return jsonify({"message": "Нет доступа!"}), 403

    data = request.json
    parent_id = data.get("parent_id")
    name = data.get("name")
    order_acc = data.get("order_acc")
    group_name = data.get("group_name")
    first_level_name = data.get("first_level_name")
    table_reference = data.get("table_reference")

    if not name or not parent_id or not order_acc or not group_name or not first_level_name or not table_reference:
        return jsonify({"message": "Все поля обязательны!"}), 400

    new_record = ReferenceTax(
        name=name,
        parent_id=parent_id,
        order_acc=order_acc,
        group_name=group_name,
        first_level_name=first_level_name,
        table_reference=table_reference
    )

    db.session.add(new_record)
    db.session.commit()

    return jsonify({"message": "Запись добавлена!"})


@app.route("/delete_reference_tax/<int:id>", methods=["DELETE"])
@login_required
def delete_reference_tax(id):
    if current_user.role != "admin":
        return jsonify({"message": "Нет доступа!"}), 403

    record = ReferenceTax.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()

    return jsonify({"message": "Запись удалена!"})


# ---- Главная страница ----
@app.route("/")
@login_required
def index():
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    current_date = datetime.now().strftime("%d-%m-%Y")

    # Если админ, получаем все компании, иначе только одну
    if current_user.role == "admin":
        companies = Organization.query.all()
    else:
        companies = Organization.query.filter_by(id=current_user.id).all()

    return render_template("index.html", user=current_user, current_time=current_time, current_date=current_date, companies=companies)

# ---- API для получения списка компаний ----
@app.route("/get_companies", methods=["GET"])
@login_required
def get_companies():
    query = text("""
        SELECT id, name FROM organizations
    """)
    organizations = db.session.execute(query).fetchall()
    if current_user.role == "admin":
        companies = Organization.query.all()
    else:
        companies = Organization.query.filter_by(id=current_user.id).all()

    return jsonify([{"id": c.id, "name": c.name} for c in companies])

# ---- API для сохранения налогов ----
@app.route("/save_taxes", methods=["POST"])
@login_required
def save_taxes():
    data = request.json
    period = data.get("period")
    ref_id = data.get("ref_id")
    amount = data.get("amount")
    org_id = data.get("org_id")

    if not period or not ref_id or not amount or not org_id:
        return jsonify({"message": "Ошибка! Все поля обязательны!"}), 400

    tax_entry = TaxTable(
        _period=period,
        ref_id=ref_id,
        amount=amount,
        created_at=datetime.utcnow(),
        org_id=org_id,
        users_id=current_user.id
    )

    db.session.add(tax_entry)
    db.session.commit()

    return jsonify({"message": "Данные успешно сохранены!"})

# ---- API для получения данных по налогам ----
@app.route("/get_taxes", methods=["GET"])
@login_required
def get_taxes():
    org_id = request.args.get("org_id")

    if not org_id:
        return jsonify({"message": "Ошибка! Не передан org_id"}), 400

    query = db.session.query(
        TaxTable._period,
        TaxTable.ref_id,
        TaxTable.amount,
        TaxTable.created_at,
        Organization.name.label("company_name")
    ).join(Organization, TaxTable.org_id == Organization.id)

    if current_user.role != "admin":
        query = query.filter(TaxTable.org_id == org_id)

    taxes = query.all()

    return jsonify([
        {
            "period": tax._period.strftime("%Y-%m-%d"),
            "ref_id": tax.ref_id,
            "amount": str(tax.amount),
            "created_at": tax.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "company_name": tax.company_name
        }
        for tax in taxes
    ])

# ---- Страница логина ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Неверный логин или пароль", "danger")

    return render_template("login.html")

# ---- Выход из системы ----
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/fill_taxes")
@login_required
def fill_taxes():
    org_id = session.get("selected_company")  # Выбранная компания
    if not org_id and current_user.role != "admin":
        flash("Выберите компанию", "danger")
        return redirect(url_for("index"))

    # Загружаем компании, доступные пользователю
    if current_user.role == "admin":
        companies = Organization.query.all()
    else:
        companies = Organization.query.filter_by(id=org_id).all()

    # Получаем данные по налогам
    taxes = db.session.query(
        TaxTable._period,
        TaxTable.ref_id,
        TaxTable.amount,
        TaxTable.created_at,
        Organization.name.label("company_name")
    ).join(Organization, TaxTable.org_id == Organization.id).all()

    return render_template("fill_taxes.html", user=current_user, companies=companies, data=taxes)


@app.route('/get_taxes_by_year', methods=['POST'])
def get_taxes_by_year():
    year = request.json.get('year')
    taxes = db.session.query(TaxTable).filter(func.extract('year', TaxTable._period) == year).all()

    taxes_data = [
        {
            "period": tax._period.strftime('%Y-%m-%d'),
            "ref_id": tax.ref_id,
            "amount": tax.amount,
            "created_at": tax.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "org_id": tax.org_id,
            "users_id": tax.users_id
        } 
        for tax in taxes
    ]

    return jsonify({"taxes": taxes_data})


@app.route("/fill_budget")
@login_required
def fill_budget():
    return render_template("fill_budget.html")




# ---- Страница управления справочником ----
@app.route("/manage_reference_tax", methods=["GET"])
@login_required
def manage_reference_tax():
    if current_user.role != "admin":
        flash("Нет доступа!", "danger")
        return redirect(url_for("index"))

    reference_tax = ReferenceTax.query.all()
    return render_template("manage_reference_tax.html", reference_tax=reference_tax)

# Добавление новой записи в таблицу taxtable
# Добавление новой записи в таблицу taxtable
@app.route("/add_tax_entry", methods=["POST"])
@login_required
def add_tax_entry():
    data = request.json
    _period = data.get("_period")
    ref_id = data.get("ref_id")
    amount = data.get("amount")
    org_id = data.get("org_id")

    # Проверка на дублирование записей
    existing_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
    if existing_entry:
        return jsonify({"message": "Запись уже существует! Измените или удалите существующую запись."}), 400

    tax_entry = TaxTable(
        _period=_period,
        ref_id=ref_id,
        amount=amount,
        created_at=datetime.utcnow(),
        org_id=org_id,
        users_id=current_user.id
    )

    db.session.add(tax_entry)
    db.session.commit()

    return jsonify({"message": "Данные успешно сохранены!"})


# Обновление существующей записи в таблице taxtable
@app.route("/update_tax_entry/<int:id>", methods=["POST"])
@login_required
def update_tax_entry(id):
    data = request.json
    amount = data.get("amount")

    tax_entry = TaxTable.query.get_or_404(id)
    tax_entry.amount = amount
    db.session.commit()

    return jsonify({"message": "Данные успешно обновлены!"})

# Удаление записи из таблицы taxtable
@app.route("/delete_tax_entry", methods=["POST"])
@login_required
def delete_tax_entry():
    data = request.json
    entry_id = data.get("id")
    tax_entry = TaxTable.query.get(entry_id)
    if tax_entry:
        db.session.delete(tax_entry)
        db.session.commit()
        return jsonify({"message": "Запись успешно удалена!"})
    else:
        return jsonify({"message": "Запись не найдена!"}), 404

@app.route("/edit_tax_entry", methods=["POST"])
@login_required
def edit_tax_entry():
    data = request.json
    entry_id = data.get("id")
    amount = data.get("amount")
    tax_entry = TaxTable.query.get(entry_id)
    if tax_entry:
        tax_entry.amount = amount
        db.session.commit()
        return jsonify({"message": "Запись успешно обновлена!"})
    else:
        return jsonify({"message": "Запись не найдена!"}), 404

# Определение списка русских названий месяцев
russian_months = [
    '',
    'Январь',
    'Февраль',
    'Март',
    'Апрель',
    'Май',
    'Июнь',
    'Июль',
    'Август',
    'Сентябрь',
    'Октябрь',
    'Ноябрь',
    'Декабрь'
]

@app.route("/view_taxes", methods=["GET", "POST"])
@login_required
def view_taxes():
    companies = Organization.query.all()  # Получение списка организаций

    # Получение доступных годов из базы данных
    available_years_query = db.session.query(func.extract('year', TaxTable._period).label('year')).distinct().order_by('year')
    available_years = [int(row.year) for row in available_years_query]

    if request.method == "POST":
        org_id = request.form.get("org_id")
        year = request.form.get("year")
        month = request.form.get("month")
    else:
        org_id = request.args.get("org_id")
        year = request.args.get("year")
        month = request.args.get("month")

    # Проверяем наличие необходимых параметров
    if not org_id or not year:
        return render_template("view_taxes.html", user=current_user, taxes_data=None, total_sum=0, org_id=None, year=None, month=None, companies=companies, available_years=available_years)

    try:
        org_id = int(org_id)
        year = int(year)
        if month:
            month = int(month)
    except ValueError:
        return "Неверные параметры", 400

    # Строим запрос в зависимости от того, указан ли месяц
    base_query = db.session.query(
        TaxTable._period,
        TaxTable.amount,
        TaxTable.org_id,
        ReferenceTax.first_level_name,
        ReferenceTax.group_name,
        ReferenceTax.name.label("ref_name")
    ).join(ReferenceTax, TaxTable.ref_id == ReferenceTax.id).filter(
        TaxTable.org_id == org_id,
        func.extract('year', TaxTable._period) == year
    )

    if month:
        base_query = base_query.filter(func.extract('month', TaxTable._period) == month)

    taxes = base_query.all()

    # Обработка данных для иерархического отображения и вычисления итогов
    taxes_data = {}
    total_sum = 0
    months_set = set()

    # Инициализируем общий итог по месяцам
    total_per_month = defaultdict(float)

    for tax in taxes:
        first_level = tax.first_level_name
        second_level = tax.group_name
        third_level = tax.ref_name
        amount = float(tax.amount or 0)
        period = tax._period
        month_num = period.month
        month_name = russian_months[month_num]
        months_set.add(month_name)
        total_sum += amount
        total_per_month[month_name] += amount  # Сумма по месяцам для общего итога

        # Уровень 1
        if first_level not in taxes_data:
            taxes_data[first_level] = {'total': 0, 'per_month': defaultdict(float), 'children': {}}
        taxes_data[first_level]['total'] += amount
        taxes_data[first_level]['per_month'][month_name] += amount

        # Уровень 2
        if second_level not in taxes_data[first_level]['children']:
            taxes_data[first_level]['children'][second_level] = {'total': 0, 'per_month': defaultdict(float), 'children': {}}
        taxes_data[first_level]['children'][second_level]['total'] += amount
        taxes_data[first_level]['children'][second_level]['per_month'][month_name] += amount

        # Уровень 3
        if third_level not in taxes_data[first_level]['children'][second_level]['children']:
            taxes_data[first_level]['children'][second_level]['children'][third_level] = {'total': 0, 'amounts': {}}
        taxes_data[first_level]['children'][second_level]['children'][third_level]['total'] += amount
        taxes_data[first_level]['children'][second_level]['children'][third_level]['amounts'][month_name] = amount

    # Определяем список месяцев для отображения в таблице
    if month:
        month_name = russian_months[month]
        months_list = [month_name]
    else:
        months_list = [russian_months[i] for i in range(1, 13) if russian_months[i] in months_set]

    return render_template(
        "view_taxes.html",
        user=current_user,
        taxes_data=taxes_data,
        total_sum=total_sum,
        total_per_month=total_per_month,
        org_id=org_id,
        year=year,
        month=month,
        companies=companies,
        months_list=months_list,
        available_years=available_years
    )


from flask import request, jsonify, render_template, redirect, url_for

@app.route("/add_taxes", methods=["GET", "POST"])
@login_required
def add_taxes():
    if request.method == "POST":
        data = request.json
        action = data.get("action")
        if action == "add":
            _period = data.get("_period")
            ref_id = data.get("ref_id")
            amount = data.get("amount")
            org_id = data.get("org_id")

            # Проверка на дублирование записей
            existing_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
            if existing_entry:
                return jsonify({"message": "Запись уже существует! Измените или удалите существующую запись."}), 400

            tax_entry = TaxTable(
                _period=_period,
                ref_id=ref_id,
                amount=amount,
                created_at=datetime.utcnow(),
                org_id=org_id,
                users_id=current_user.id
            )

            db.session.add(tax_entry)
            db.session.commit()

            # Извлечение года и месяца из _period
            year, month, _ = _period.split('-')
            month = int(month)

            return jsonify({"message": "Данные успешно сохранены!", "org_id": org_id, "month": month, "year": year})
        elif action == "delete":
            entry_id = data.get("entry_id")
            tax_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
            if tax_entry:
                db.session.delete(tax_entry)
                db.session.commit()
                return jsonify({"message": "Запись успешно удалена!"})
            else:
                return jsonify({"message": "Запись не найдена!"}), 404
        elif action == "edit":
            entry_id = data.get("entry_id")
            amount = data.get("amount")
            tax_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
            if tax_entry:
                tax_entry.amount = amount
                db.session.commit()
                return jsonify({"message": "Запись успешно обновлена!"})
            else:
                return jsonify({"message": "Запись не найдена!"}), 404
    else:
        org_id = request.args.get("org_id")
        month = request.args.get("month")
        year = request.args.get("year")
        companies = Organization.query.all()

        # Получение доступных годов из базы данных
        available_years_query = db.session.query(func.extract('year', TaxTable._period).label('year')).distinct().order_by('year')
        available_years = [int(row.year) for row in available_years_query]

        # Получение данных для отображения существующих записей
        tax_entries = []
        if org_id and year and month:
            query = db.session.query(
                TaxTable._period,
                TaxTable.ref_id,
                TaxTable.amount,
                TaxTable.org_id,
                ReferenceTax.name.label("ref_name")
            ).join(ReferenceTax, TaxTable.ref_id == ReferenceTax.id).filter(
                TaxTable.org_id == org_id,
                func.extract('year', TaxTable._period) == int(year),
                func.extract('month', TaxTable._period) == int(month)
            ).all()

            for entry in query:
                tax_entries.append({
                    "_period": entry._period.strftime('%Y-%m-%d'),
                    "ref_id": entry.ref_id,
                    "org_id": entry.org_id,
                    "ref_name": entry.ref_name,
                    "amount": float(entry.amount or 0)
                })

        return render_template("add_taxes.html", user=current_user, companies=companies, org_id=org_id, month=month, year=year, available_years=available_years, tax_entries=tax_entries)



@app.route("/get_reference_tax", methods=["GET"])
@login_required
def get_reference_tax():
    reference_tax = ReferenceTax.query.all()
    return jsonify([{"id": r.id, "name": r.name, "order_acc": r.order_acc} for r in reference_tax])

@app.route("/edit_taxes", methods=["GET", "POST"])
@login_required
def edit_taxes():
    if request.method == "POST":
        data = request.json
        action = data.get("action")
        _period = data.get("_period")
        ref_id = data.get("ref_id")
        org_id = data.get("org_id")
        if action == "delete":
            tax_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
            if tax_entry:
                db.session.delete(tax_entry)
                db.session.commit()
                return jsonify({"message": "Запись успешно удалена!"})
            else:
                return jsonify({"message": "Запись не найдена!"}), 404
        elif action == "edit":
            amount = data.get("amount")
            tax_entry = TaxTable.query.filter_by(_period=_period, ref_id=ref_id, org_id=org_id).first()
            if tax_entry:
                tax_entry.amount = amount
                db.session.commit()
                return jsonify({"message": "Запись успешно обновлена!"})
            else:
                return jsonify({"message": "Запись не найдена!"}), 404
    else:
        org_id = request.args.get("org_id")
        month = request.args.get("month")
        year = request.args.get("year")
        companies = Organization.query.all()

        # Получение доступных годов из базы данных
        available_years_query = db.session.query(func.extract('year', TaxTable._period).label('year')).distinct().order_by('year')
        available_years = [int(row.year) for row in available_years_query]

        # Получение данных для отображения существующих записей
        tax_entries = []
        if org_id and year and month:
            query = db.session.query(
                TaxTable._period,
                TaxTable.ref_id,
                TaxTable.amount,
                TaxTable.org_id,
                ReferenceTax.name.label("ref_name")
            ).join(ReferenceTax, TaxTable.ref_id == ReferenceTax.id).filter(
                TaxTable.org_id == org_id,
                func.extract('year', TaxTable._period) == int(year),
                func.extract('month', TaxTable._period) == int(month)
            ).all()

            for entry in query:
                tax_entries.append({
                    "_period": entry._period.strftime('%Y-%m-%d'),
                    "ref_id": entry.ref_id,
                    "org_id": entry.org_id,
                    "ref_name": entry.ref_name,
                    "amount": float(entry.amount or 0)
                })

        return render_template("edit_taxes.html", user=current_user, companies=companies, org_id=org_id, month=month, year=year, available_years=available_years, tax_entries=tax_entries)


# ---- Запуск сервера ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
