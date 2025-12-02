from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import os
import time 
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# =======================
#   CONFIGURACIÓN
# =======================

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret")   # Sesiones

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_FILE_SIZE_MB", 16)) * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =======================
#   FUNCIONES BASE
# =======================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
    except Exception as e:
        print("❌ Error de conexión a BD:", e)
        return None


# =======================
#   MIDDLEWARE
# =======================

def login_required(func):
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Debes iniciar sesión.")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# =======================
#   AUTH CONTROLLER
# =======================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email = request.form.get("Correo")
        password = request.form.get("Contra")

        if not email or not password:
            return "Faltan datos"

        conn = get_connection()
        if not conn:
            return "Error conectando a base de datos"

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and check_password_hash(user["pass"], password):
            session["user"] = user["email"]
            return redirect(url_for("ver"))

        return "Correo o contraseña incorrectos"

    return render_template("login.html")


@app.route('/reg', methods=['GET', 'POST'])
def registro():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return "Completa todos los campos"

        conn = get_connection()
        cursor = conn.cursor()

        hashed = generate_password_hash(password)

        cursor.execute("INSERT INTO users (email, pass) VALUES (%s, %s)", (email, hashed))
        conn.commit()

        cursor.close()
        conn.close()

        return redirect(url_for('login'))

    return render_template("registro.html")


@app.route('/logout')
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# =======================
#   FOOD CONTROLLER
# =======================

@app.route('/ver')
@login_required
def ver():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    editar_id = request.args.get("editar")
    food_editar = None

    if editar_id:
        cursor.execute("""
            SELECT f.*, c.type AS category_name
            FROM food f
            LEFT JOIN category c ON f.id_category = c.id
            WHERE f.id = %s
        """, (editar_id,))
        food_editar = cursor.fetchone()
        if food_editar:
            food_editar["price"] /= 100

    cursor.execute("""
        SELECT f.*, c.type AS category_name
        FROM food f
        LEFT JOIN category c ON f.id_category = c.id
        ORDER BY c.type, f.name
    """)
    foods = cursor.fetchall()

    for food in foods:
        food["price"] /= 100

    foods_by_category = {}
    for f in foods:
        cat = f["category_name"] or "Sin Categoría"
        foods_by_category.setdefault(cat, []).append(f)

    cursor.execute("SELECT * FROM category")
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("ingresodb.html",
        foods_by_category=foods_by_category,
        food_editar=food_editar,
        categories=categories
    )


@app.route('/guardar', methods=['POST'])
@login_required
def guardar():
    try:
        nombre = request.form["nombre"]
        ing = request.form["ing1"]
        precio = float(request.form["precio"])
        cat = request.form["id_category"]

        precio_centavos = int(precio * 100)

        imagen_path = None
        file = request.files.get("imagen")

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"{int(time.time())}_{filename}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            imagen_path = f"uploads/{filename}"

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO food (name, ingredients, image, price, id_category)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, ing, imagen_path, precio_centavos, cat))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("ver"))

    except Exception as e:
        return f"Error: {str(e)}"


@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT image FROM food WHERE id = %s", (id,))
    food = cursor.fetchone()

    cursor.execute("DELETE FROM food WHERE id = %s", (id,))
    conn.commit()

    cursor.close()
    conn.close()

    if food and food["image"]:
        path = os.path.join("static", food["image"])
        if os.path.exists(path):
            os.remove(path)

    return redirect(url_for('ver'))


@app.route('/editar/<int:id>', methods=['POST'])
@login_required
def editar(id):
    try:
        nombre = request.form["nombre"]
        ing = request.form["ing1"]
        precio = float(request.form["precio"])
        cat = request.form["id_category"]

        precio_centavos = int(precio * 100)

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT image FROM food WHERE id = %s", (id,))
        actual = cursor.fetchone()

        imagen_path = actual["image"]

        file = request.files.get("imagen")

        if file and allowed_file(file.filename):
            if imagen_path:
                old = os.path.join("static", imagen_path)
                if os.path.exists(old):
                    os.remove(old)

            filename = secure_filename(file.filename)
            filename = f"{int(time.time())}_{filename}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            imagen_path = f"uploads/{filename}"

        cursor.execute("""
            UPDATE food SET name=%s, ingredients=%s, image=%s, price=%s, id_category=%s
            WHERE id=%s
        """, (nombre, ing, imagen_path, precio_centavos, cat, id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("ver"))

    except Exception as e:
        return f"Error: {str(e)}"


# =======================
#   CATEGORY CONTROLLER
# =======================

@app.route('/tipoingresar', methods=['POST'])
@login_required
def tipo():
    nombre = request.form.get("type")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO category (type) VALUES (%s)", (nombre,))
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for("ver"))


# =======================
#   MENU PÚBLICO
# =======================

@app.route('/menu')
def menu():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT f.*, c.type AS category_name
        FROM food f
        LEFT JOIN category c ON f.id_category = c.id
        ORDER BY c.type, f.name
    """)
    foods = cursor.fetchall()

    for f in foods:
        f["price"] /= 100

    foods_by_category = {}
    for f in foods:
        cat = f["category_name"] or "Sin Categoría"
        foods_by_category.setdefault(cat, []).append(f)

    cursor.close()
    conn.close()

    return render_template("menu.html", foods_by_category=foods_by_category)




