from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bhishmak_ka_secret_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trello_board_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 🚀 तुम्हारी असली Google Keys (मैंने यहाँ सेट कर दी हैं)
app.config['GOOGLE_CLIENT_ID'] = '126513598147-gqe13705587dm1gbvhg6en6h4q32t1p0.apps.googleusercontent.com'
app.config['GOOGLE_CLIENT_SECRET'] = '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'

db = SQLAlchemy(app)
oauth = OAuth(app)

# Google OAuth Setup
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), default='Personal')
    priority = db.Column(db.String(20), default='Medium')
    due_date = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='Backlog')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))

with app.app_context():
    db.create_all()

# --- Google Login Routes 🚀 ---
@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/authorize')
def google_authorize():
    token = google.authorize_access_token()
    user_info = google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
    email = user_info.get('email')
    
    user = User.query.filter_by(username=email).first()
    if not user:
        random_safe_password = secrets.token_urlsafe(20)
        hashed_pw = generate_password_hash(random_safe_password, method='pbkdf2:sha256')
        user = User(username=email, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    flash(f"Welcome back! Logged in as {email} 🚀", "success")
    return redirect(url_for('home'))

# --- App Routes ---
@app.route("/")
@login_required
def home():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    return render_template("index.html", tasks=tasks, user_name=current_user.username)

@app.route("/add", methods=["POST"])
@login_required
def add_task():
    name = request.form.get("task_name")
    category = request.form.get("category")
    priority = request.form.get("priority", "Medium")

    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    auto_date = ist_now.strftime('%d %b %Y')

    if name:
        new_task = Task(name=name, user_id=current_user.id, category=category, priority=priority, due_date=auto_date)
        db.session.add(new_task)
        db.session.commit()
        flash("Task added with today's date! 🚀", "success")
    return redirect(url_for('home'))

@app.route("/edit/<int:tid>", methods=['GET', 'POST'])
@login_required
def edit_task(tid):
    task = Task.query.get(tid)
    if not task or task.user_id != current_user.id:
        flash("Task not found! ⚠️", "danger")
        return redirect(url_for('home'))

    if request.method == 'POST':
        task.name = request.form.get("task_name")
        task.category = request.form.get("category")
        task.priority = request.form.get("priority")
        task.status = request.form.get("status")

        new_date = request.form.get("due_date")
        if new_date:
            try:
                date_obj = datetime.strptime(new_date, '%Y-%m-%d')
                task.due_date = date_obj.strftime('%d %b %Y')
            except ValueError:
                task.due_date = new_date
        else:
            task.due_date = None

        db.session.commit()
        flash("Task updated! ✨", "success")
        return redirect(url_for('home'))

    return render_template("edit.html", task=task)

@app.route("/update/<int:tid>/<string:next_status>")
@login_required
def update_task(tid, next_status):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        task.status = next_status
        db.session.commit()
    return redirect(url_for('home'))

@app.route("/delete/<int:tid>")
@login_required
def delete_task(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
        flash("Task removed! 🗑️", "danger")
    return redirect(url_for('home'))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        un, pw = request.form.get('username'), request.form.get('password')
        if not User.query.filter_by(username=un).first():
            db.session.add(User(username=un, password=generate_password_hash(pw, method='pbkdf2:sha256')))
            db.session.commit()
            flash("Account created! 😊", "success")
            return redirect(url_for('login'))
        flash("Username exists! ⚠️", "danger")
    return render_template("register.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            flash("Welcome back! 👋", "success")
            return redirect(url_for('home'))
        flash("Invalid credentials! ❌", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    flash("Logged out! 🔒", "success")
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
