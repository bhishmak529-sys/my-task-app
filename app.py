import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import secrets
import csv
import io
import smtplib
from email.mime.text import MIMEText
import threading
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)

# 🛡️ SECURITY
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'supersecretkey123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///trello_board_final.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 🚀 EMAIL SETTINGS
SENDER_EMAIL = 'aparnathakur157@gmail.com'
APP_PASSWORD = os.getenv('EMAIL_PASSWORD')

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 🛡️ GOOGLE LOGIN
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_SECRET')

db = SQLAlchemy(app)
oauth = OAuth(app)

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

# ================= MODELS =================
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True)

task_collaborators = db.Table('task_collaborators',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('task_id', db.Integer, db.ForeignKey('task.id'), primary_key=True)
)

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(300), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)

class SubTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(300), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), default='Personal')
    priority = db.Column(db.String(20), default='Medium')
    due_date = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='Backlog')
    description = db.Column(db.Text, default='', nullable=True) 
    attachments = db.relationship('Attachment', backref='task', cascade='all, delete-orphan', lazy=True)
    subtasks = db.relationship('SubTask', backref='task', cascade='all, delete-orphan', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))
    collaborators = db.relationship('User', secondary=task_collaborators, backref=db.backref('shared_tasks', lazy='dynamic'))

with app.app_context():
    db.create_all()

# ================= HELPER FUNCTIONS =================
def send_email_background(recipient_email, task_name, task_priority, task_category):
    try:
        subject = f"🚨 URGENT TASK ALERT: {task_name}"
        body = f"Hello,\n\nYou just added a highly important task to your TaskPro Elite board.\n\nTask Name: {task_name}\nCategory: {task_category}\nPriority: {task_priority}\n\nPlease make sure to complete this on time!\n\nBest Regards,\nTaskPro Elite Bot 🤖"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
    except Exception as e:
        pass

# ================= AUTH ROUTES =================
@app.route('/login/google')
def google_login():
    return google.authorize_redirect(url_for('google_authorize', _external=True))

@app.route('/login/google/authorize')
def google_authorize():
    token = google.authorize_access_token()
    user_info = google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
    email = user_info.get('email')
    picture = user_info.get('picture')
    user = User.query.filter_by(username=email).first()
    if not user:
        random_safe_password = secrets.token_urlsafe(20)
        user = User(username=email, password=generate_password_hash(random_safe_password, method='pbkdf2:sha256'))
        db.session.add(user)
        db.session.commit()
    login_user(user)
    session['profile_pic'] = picture
    return redirect(url_for('home'))

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        un, pw = request.form.get('username'), request.form.get('password')
        if not User.query.filter_by(username=un).first():
            db.session.add(User(username=un, password=generate_password_hash(pw, method='pbkdf2:sha256')))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            session['profile_pic'] = f"https://ui-avatars.com/api/?name={user.username}&background=6366f1&color=fff"
            return redirect(url_for('home'))
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    session.pop('profile_pic', None)
    return redirect(url_for('login'))

# ================= MAIN ROUTES =================
@app.route("/")
@login_required
def home():
    my_tasks = Task.query.filter_by(user_id=current_user.id).all()
    shared_tasks = current_user.shared_tasks.all()
    tasks = list(set(my_tasks + shared_tasks))
    logs = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.timestamp.desc()).limit(20).all()
    
    today_date_only = (datetime.utcnow() + timedelta(hours=5, minutes=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    for t in tasks:
        t.is_overdue = False
        t.is_due_soon = False
        t.sort_score = 9999
        if t.due_date and t.status != 'Done':
            try:
                delta = (datetime.strptime(t.due_date, '%d %b %Y') - today_date_only).days
                if delta < 0: t.is_overdue = True; t.sort_score = 1 
                elif delta in [0, 1]: t.is_due_soon = True; t.sort_score = 2 
                else: t.sort_score = 3 + delta
            except: t.sort_score = 1000
        elif t.status == 'Done': t.sort_score = 9999 
        else: t.sort_score = {'High': 500, 'Medium': 600, 'Low': 700}.get(t.priority, 600)
            
    tasks.sort(key=lambda x: x.sort_score)
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.status == 'Done')
    progress = round((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    return render_template("index.html", tasks=tasks, user_name=current_user.username, progress=progress, logs=logs)

@app.route("/add", methods=["POST"])
@login_required
def add_task():
    name = request.form.get("task_name")
    category = request.form.get("category")
    priority = request.form.get("priority", "Medium")
    raw_date = request.form.get("due_date") 

    try:
        date_obj = datetime.strptime(raw_date, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%d %b %Y')
    except:
        formatted_date = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d %b %Y')

    if name:
        new_task = Task(name=name, user_id=current_user.id, category=category, priority=priority, due_date=formatted_date, description='')
        db.session.add(new_task)
        db.session.add(ActivityLog(description=f"Created a new task: '{name}' due on {formatted_date}", user_id=current_user.id))
        db.session.commit()
        if priority == "High" or category == "Urgent":
            threading.Thread(target=send_email_background, args=(current_user.username, name, priority, category)).start()
    return redirect(url_for('home'))

@app.route("/update_status", methods=["POST"])
@login_required
def update_status():
    data = request.get_json()
    task = Task.query.get(data['task_id'])
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        task.status = data['new_status']
        db.session.add(ActivityLog(description=f"Moved task '{task.name}' to {task.status}", user_id=current_user.id))
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/edit/<int:tid>", methods=['GET', 'POST'])
@login_required
def edit_task(tid):
    task = Task.query.get(tid)
    if not task or (task.user_id != current_user.id and current_user not in task.collaborators):
        return redirect(url_for('home'))
    if request.method == 'POST':
        task.name = request.form.get("task_name")
        task.category = request.form.get("category")
        task.priority = request.form.get("priority")
        task.status = request.form.get("status")
        task.due_date = request.form.get("due_date")
        db.session.add(ActivityLog(description=f"Edited details of task '{task.name}'", user_id=current_user.id))
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("edit.html", task=task)

@app.route("/delete/<int:tid>")
@login_required
def delete_task(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        db.session.add(ActivityLog(description=f"Deleted task: '{task.name}'", user_id=current_user.id))
        db.session.delete(task)
        db.session.commit()
    return redirect(url_for('home'))

@app.route("/save_description", methods=["POST"])
@login_required
def save_description():
    data = request.get_json()
    task = Task.query.get(data.get('task_id'))
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        task.description = data.get('description')
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# ================= SUB-TASKS ROUTES =================
@app.route("/get_subtasks/<int:tid>")
@login_required
def get_subtasks(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        subtasks = SubTask.query.filter_by(task_id=tid).all()
        return jsonify([{"id": s.id, "title": s.title, "is_completed": s.is_completed} for s in subtasks])
    return jsonify([])

@app.route("/add_subtask/<int:tid>", methods=["POST"])
@login_required
def add_subtask(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        title = request.get_json().get("title")
        if title:
            db.session.add(SubTask(title=title, task_id=tid))
            db.session.commit()
            return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/toggle_subtask/<int:sid>", methods=["POST"])
@login_required
def toggle_subtask(sid):
    sub = SubTask.query.get(sid)
    if sub and (sub.task.user_id == current_user.id or current_user in sub.task.collaborators):
        sub.is_completed = not sub.is_completed
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/delete_subtask/<int:sid>", methods=["POST"])
@login_required
def delete_subtask(sid):
    sub = SubTask.query.get(sid)
    if sub and (sub.task.user_id == current_user.id or current_user in sub.task.collaborators):
        db.session.delete(sub)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# ================= COLLABORATORS ROUTES =================
@app.route("/share_task", methods=["POST"])
@login_required
def share_task():
    data = request.get_json()
    task = Task.query.get(data.get('task_id'))
    friend = User.query.filter_by(username=data.get('friend_username')).first()
    
    if task and task.user_id == current_user.id:
        if friend:
            if friend not in task.collaborators and friend.id != current_user.id:
                task.collaborators.append(friend)
                db.session.add(ActivityLog(description=f"Shared task '{task.name}' with {friend.username}", user_id=current_user.id))
                db.session.commit()
                return jsonify({"success": True, "message": "Task shared successfully! 🤝"})
            return jsonify({"success": False, "message": "Already shared!"})
        return jsonify({"success": False, "message": "User not found!"})
    return jsonify({"success": False, "message": "Unauthorized."})

@app.route("/get_collaborators/<int:tid>")
@login_required
def get_collaborators(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        return jsonify([{"id": u.id, "username": u.username} for u in task.collaborators])
    return jsonify([])

@app.route("/remove_collaborator/<int:tid>/<int:uid>", methods=["POST"])
@login_required
def remove_collaborator(tid, uid):
    task = Task.query.get(tid)
    user_to_remove = User.query.get(uid)
    if task and task.user_id == current_user.id and user_to_remove in task.collaborators:
        task.collaborators.remove(user_to_remove)
        db.session.add(ActivityLog(description=f"Removed access of {user_to_remove.username}", user_id=current_user.id))
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# ================= ANALYTICS DASHBOARD ROUTE 📊 =================
@app.route("/dashboard")
@login_required
def dashboard():
    my_tasks = Task.query.filter_by(user_id=current_user.id).all()
    tasks = list(set(my_tasks + current_user.shared_tasks.all()))
    
    # 1. Status Data (Pie Chart)
    status_data = {
        'backlog': len([t for t in tasks if t.status == 'Backlog']),
        'todo': len([t for t in tasks if t.status == 'To Do']),
        'in_progress': len([t for t in tasks if t.status == 'In Progress']),
        'done': len([t for t in tasks if t.status == 'Done'])
    }
    
    # 2. Priority Data (Bar Chart)
    priority_data = {
        'high': len([t for t in tasks if t.priority == 'High']),
        'medium': len([t for t in tasks if t.priority == 'Medium']),
        'low': len([t for t in tasks if t.priority == 'Low'])
    }

    # 3. Category Data (Doughnut Chart)
    category_data = {
        'personal': len([t for t in tasks if t.category == 'Personal']),
        'work': len([t for t in tasks if t.category == 'Work']),
        'urgent': len([t for t in tasks if t.category == 'Urgent'])
    }

    return render_template("dashboard.html", 
                           user_name=current_user.username,
                           total_tasks=len(tasks),
                           status_data=status_data,
                           priority_data=priority_data,
                           category_data=category_data)

@app.route("/clear_done", methods=["POST"])
@login_required
def clear_done():
    tasks_to_delete = Task.query.filter_by(user_id=current_user.id, status='Done').all()
    for task in tasks_to_delete: db.session.delete(task)
    db.session.commit()
    return redirect(url_for('home'))

@app.route("/about")
def about(): return render_template("about.html")

@app.route("/export")
@login_required
def export_tasks():
    user_tasks = list(set(Task.query.filter_by(user_id=current_user.id).all() + current_user.shared_tasks.all()))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Task Name', 'Category', 'Priority', 'Current Status', 'Due Date', 'Description'])
    for t in user_tasks: writer.writerow([t.name, t.category, t.priority, t.status, t.due_date, t.description])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=TaskPro_Elite_Backup.csv"})

@app.route("/upload_attachment/<int:tid>", methods=["POST"])
@login_required
def upload_attachment(tid):
    task = Task.query.get(tid)
    if not task or (task.user_id != current_user.id and current_user not in task.collaborators):
        return redirect(url_for('home'))
    for file in request.files.getlist('task_file'):
        if file and file.filename != '':
            unique_filename = f"task_{tid}_{secrets.token_hex(4)}_{secure_filename(file.filename)}"
            if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            db.session.add(Attachment(file_path=f"/static/uploads/{unique_filename}", task_id=tid))
    db.session.commit()
    return redirect(url_for('home'))

@app.route("/remove_attachment/<int:aid>", methods=["POST"])
@login_required
def remove_attachment(aid):
    attachment = Attachment.query.get(aid)
    if attachment and (attachment.task.user_id == current_user.id or current_user in attachment.task.collaborators):
        file_path = attachment.file_path.lstrip('/') 
        try:
            if os.path.exists(file_path): os.remove(file_path) 
        except: pass
        db.session.delete(attachment)
        db.session.commit()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)
