import os
# 🌟 NAYA CHANGE 1: Local development ke liye .env file se keys load karna
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
from sqlalchemy import text, func  
from flask_socketio import SocketIO, emit
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)

# ================= EMAIL CREDENTIALS =================
SYSTEM_EMAIL = "task.manage.0@gmail.com" 
SYSTEM_APP_PASSWORD = "dryd orfy gpnl vfzb" 

# 🛡️ SECURITY & CONFIG
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'supersecretkey123')

# 🌟 DATABASE FIX: Handle Render's postgres:// vs postgresql://
db_url = os.getenv('DATABASE_URL', 'sqlite:///trello_board_final.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 🌟 Socket.IO Engine
socketio = SocketIO(app, cors_allowed_origins="*")

# ================= GOOGLE OAUTH CONFIG =================
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
    display_name = db.Column(db.String(100), nullable=True)
    profile_pic = db.Column(db.String(300), nullable=True)
    password = db.Column(db.String(150), nullable=False)
    xp = db.Column(db.Integer, default=0) 
    tasks = db.relationship('Task', backref='owner', lazy=True)

    @property
    def badge(self):
        current_xp = self.xp if self.xp else 0
        if current_xp >= 500: return "Legend 💎"
        elif current_xp >= 300: return "Elite 🥇"
        elif current_xp >= 150: return "Pro 🥈"
        elif current_xp >= 50: return "Apprentice 🎖️"
        else: return "Novice 🥉"

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

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='task_comments')

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
    comments = db.relationship('Comment', backref='task', cascade='all, delete-orphan', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))
    collaborators = db.relationship('User', secondary=task_collaborators, backref=db.backref('shared_tasks', lazy='dynamic'))

with app.app_context():
    db.create_all()

# ================= HELPER FUNCTIONS =================
def send_notification_email(receiver_email, sender_name, task_name):
    if SYSTEM_EMAIL == "your_actual_email@gmail.com":
        print("⚠️ Email not sent! Please configure SYSTEM_EMAIL in app.py")
        return
    try:
        msg = MIMEText(f"Hello!\n\n{sender_name} has just shared a task with you on TaskPro Elite.\n\nTask Name: {task_name}\n\nLogin to your dashboard to check it out!\n\nCheers,\nTaskPro Elite Team")
        msg['Subject'] = f"New Task Shared: {task_name}"
        msg['From'] = SYSTEM_EMAIL
        msg['To'] = receiver_email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SYSTEM_EMAIL, SYSTEM_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"📧 Email sent successfully to {receiver_email}!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ================= AUTH ROUTES =================
@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    
    # 🌟 NAYA CHANGE 2: Render HTTPS Proxy Fix
    if redirect_uri.startswith('http://') and 'onrender.com' in redirect_uri:
        redirect_uri = redirect_uri.replace('http://', 'https://', 1)
        print(f"Forcefully secured Redirect URI: {redirect_uri}")
        
    return google.authorize_redirect(redirect_uri)

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
    if not current_user.profile_pic:
        session['profile_pic'] = picture
    flash("Logged in successfully via Google! 🚀", "success")
    return redirect(url_for('home'))

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        un, pw = request.form.get('username'), request.form.get('password')
        if not User.query.filter_by(username=un).first():
            db.session.add(User(username=un, password=generate_password_hash(pw, method='pbkdf2:sha256')))
            db.session.commit()
            flash("Account created successfully! Please login.", "success")
            return redirect(url_for('login'))
        else:
            flash("Username already exists! ❌", "error")
    return render_template("register.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            if not current_user.profile_pic:
                session['profile_pic'] = f"https://ui-avatars.com/api/?name={user.username}&background=6366f1&color=fff"
            flash("Logged in successfully! 🚀", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password! ❌", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    session.pop('profile_pic', None)
    flash("You have been logged out securely. 👋", "info")
    return redirect(url_for('login'))

# ================= PROFILE & SECURITY ROUTE =================
@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    new_name = request.form.get("display_name")
    if new_name:
        current_user.display_name = new_name 
        db.session.add(ActivityLog(description="Updated Display Name", user_id=current_user.id))

    file = request.files.get("profile_pic")
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        unique_filename = f"dp_{current_user.id}_{secrets.token_hex(4)}_{filename}"
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path) 
        current_user.profile_pic = f"/static/uploads/{unique_filename}" 
        session['profile_pic'] = current_user.profile_pic
        db.session.add(ActivityLog(description="Updated Profile Picture", user_id=current_user.id))

    db.session.commit()
    flash("Profile Settings Updated Successfully! 🌟", "success")
    return redirect(url_for('home'))

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("security.html")

    old_pw = request.form.get("old_password")
    new_pw = request.form.get("new_password")
    confirm_pw = request.form.get("confirm_password")
    
    old_err = None
    new_err = None
    
    if not check_password_hash(current_user.password, old_pw):
        old_err = "Incorrect current password!"
        
    if new_pw != confirm_pw:
        new_err = "New passwords do not match!"
    elif len(new_pw) < 4:
        new_err = "Password must be at least 4 characters long!"
        
    if old_err or new_err:
        return render_template("security.html", old_err=old_err, new_err=new_err)

    current_user.password = generate_password_hash(new_pw, method='pbkdf2:sha256')
    db.session.add(ActivityLog(description="Changed Account Password", user_id=current_user.id))
    db.session.commit()
    flash("Security Alert: Password changed successfully! 🔒", "success")
    return redirect(url_for('home'))

# ================= MAIN ROUTES =================
@app.route("/")
@login_required
def home():
    cat_filter = request.args.get('category', 'All')
    pri_filter = request.args.get('priority', 'All')

    my_query = Task.query.filter_by(user_id=current_user.id)
    if cat_filter != 'All':
        my_query = my_query.filter_by(category=cat_filter)
    if pri_filter != 'All':
        my_query = my_query.filter_by(priority=pri_filter)
        
    my_tasks = my_query.all()

    shared_tasks = current_user.shared_tasks.all()
    if cat_filter != 'All':
        shared_tasks = [t for t in shared_tasks if t.category == cat_filter]
    if pri_filter != 'All':
        shared_tasks = [t for t in shared_tasks if t.priority == pri_filter]

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
    
    return render_template("index.html", tasks=tasks, user_name=current_user.username, progress=progress, logs=logs, current_cat=cat_filter, current_pri=pri_filter)

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
        
        final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
        socketio.emit('board_changed', {'user': final_name, 'task': name, 'status': 'Backlog'})
        
        flash(f"New task '{name}' added successfully! ✅", "success")
    return redirect(url_for('home'))

@app.route("/move/<int:tid>/<string:new_status>")
@login_required
def move_task(tid, new_status):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        old_status = task.status
        task.status = new_status
        
        if current_user.xp is None: current_user.xp = 0
        if old_status != 'Done' and new_status == 'Done':
            current_user.xp += 10
        elif old_status == 'Done' and new_status != 'Done':
            current_user.xp -= 10
            if current_user.xp < 0: current_user.xp = 0

        db.session.add(ActivityLog(description=f"Moved task '{task.name}' to {task.status}", user_id=current_user.id))
        db.session.commit()
        
        final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
        socketio.emit('board_changed', {'user': final_name, 'task': task.name, 'status': task.status})
        
    return redirect(url_for('home'))

@app.route("/update_status", methods=["POST"])
@login_required
def update_status():
    data = request.get_json()
    task = Task.query.get(data['task_id'])
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        old_status = task.status
        task.status = data['new_status']

        if current_user.xp is None: current_user.xp = 0
        if old_status != 'Done' and task.status == 'Done':
            current_user.xp += 10
        elif old_status == 'Done' and task.status != 'Done':
            current_user.xp -= 10
            if current_user.xp < 0: current_user.xp = 0

        db.session.add(ActivityLog(description=f"Moved task '{task.name}' to {task.status}", user_id=current_user.id))
        db.session.commit()
        
        final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
        socketio.emit('board_changed', {'user': final_name, 'task': task.name, 'status': task.status})
        
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
        
        final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
        socketio.emit('board_changed', {'user': final_name, 'task': task.name, 'status': "Updated"})
        
        flash("Task updated! 📝", "info")
        return redirect(url_for('home'))
    return render_template("edit.html", task=task)

@app.route("/delete/<int:tid>")
@login_required
def delete_task(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        task_name = task.name
        db.session.add(ActivityLog(description=f"Deleted task: '{task.name}'", user_id=current_user.id))
        db.session.delete(task)
        db.session.commit()
        
        final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
        socketio.emit('board_changed', {'user': final_name, 'task': task_name, 'status': "Deleted"})
        
        flash("Task deleted permanently! 🗑️", "success")
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

# ================= SUB-TASKS & COMMENTS =================
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

@app.route("/get_comments/<int:tid>")
@login_required
def get_comments(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        comments = Comment.query.filter_by(task_id=tid).order_by(Comment.timestamp.asc()).all()
        return jsonify([{
            "id": c.id, 
            "text": c.text, 
            "username": c.user.display_name if c.user.display_name else c.user.username.split('@')[0], 
            "time": c.timestamp.strftime('%I:%M %p')
        } for c in comments])
    return jsonify([])

@app.route("/add_comment/<int:tid>", methods=["POST"])
@login_required
def add_comment(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        text = request.get_json().get("text")
        if text:
            new_comment = Comment(text=text, task_id=tid, user_id=current_user.id)
            db.session.add(new_comment)
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
                socketio.emit('board_changed', {'user': 'System', 'task': task.name, 'status': f"Shared with {friend.username}"})
                
                sender_display = current_user.display_name if current_user.display_name else current_user.username
                email_thread = threading.Thread(target=send_notification_email, args=(friend.username, sender_display, task.name))
                email_thread.start()

                return jsonify({"success": True, "message": "Task shared & Email sent! 🤝📧"})
            return jsonify({"success": False, "message": "Already shared!"})
        return jsonify({"success": False, "message": "User not found!"})
    return jsonify({"success": False, "message": "Unauthorized."})

@app.route("/get_collaborators/<int:tid>")
@login_required
def get_collaborators(tid):
    task = Task.query.get(tid)
    if task and (task.user_id == current_user.id or current_user in task.collaborators):
        return jsonify([{"id": u.id, "username": u.display_name if u.display_name else u.username.split('@')[0]} for u in task.collaborators])
    return jsonify([])

@app.route("/remove_collaborator/<int:tid>/<int:uid>", methods=["POST"])
@login_required
def remove_collaborator(tid, uid):
    task = Task.query.get(tid)
    user_to_remove = User.query.get(uid)
    if task and task.user_id == current_user.id and user_to_remove in task.collaborators:
        task.collaborators.remove(user_to_remove)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# ================= DASHBOARD & EXPORT =================
@app.route("/dashboard")
@login_required
def dashboard():
    my_tasks = Task.query.filter_by(user_id=current_user.id).all()
    tasks = list(set(my_tasks + current_user.shared_tasks.all()))
    
    status_data = {
        'backlog': len([t for t in tasks if t.status == 'Backlog']),
        'todo': len([t for t in tasks if t.status == 'To Do']),
        'in_progress': len([t for t in tasks if t.status == 'In Progress']),
        'done': len([t for t in tasks if t.status == 'Done'])
    }
    priority_data = {
        'high': len([t for t in tasks if t.priority == 'High']),
        'medium': len([t for t in tasks if t.priority == 'Medium']),
        'low': len([t for t in tasks if t.priority == 'Low'])
    }
    category_data = {
        'personal': len([t for t in tasks if t.category == 'Personal']),
        'work': len([t for t in tasks if t.category == 'Work']),
        'urgent': len([t for t in tasks if t.category == 'Urgent'])
    }

    final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
    return render_template("dashboard.html", user_name=final_name, total_tasks=len(tasks), status_data=status_data, priority_data=priority_data, category_data=category_data)

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

# ================= CALENDAR ROUTES =================
@app.route("/calendar")
@login_required
def calendar_view():
    final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
    return render_template("calendar.html", user_name=final_name)

@app.route("/api/calendar_events")
@login_required
def get_calendar_events():
    my_tasks = Task.query.filter_by(user_id=current_user.id).all()
    shared_tasks = current_user.shared_tasks.all()
    tasks = list(set(my_tasks + shared_tasks))
    
    events = []
    for t in tasks:
        if t.due_date:
            try:
                date_obj = datetime.strptime(t.due_date, '%d %b %Y')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                color = '#6366f1' 
                if t.status == 'Done': color = '#10b981'
                elif t.priority == 'High': color = '#ef4444'
                events.append({'id': t.id, 'title': f"{t.name} ({t.status})", 'start': formatted_date, 'color': color, 'url': '/'})
            except Exception as e: pass
    return jsonify(events)

# ================= ANALYTICS DASHBOARD =================
@app.route("/analytics")
@login_required
def analytics():
    status_counts = db.session.query(Task.status, func.count(Task.id)).filter_by(user_id=current_user.id).group_by(Task.status).all()
    status_dict = {status: count for status, count in status_counts}

    priority_counts = db.session.query(Task.priority, func.count(Task.id)).filter_by(user_id=current_user.id).group_by(Task.priority).all()
    priority_dict = {priority: count for priority, count in priority_counts}

    final_name = current_user.display_name if current_user.display_name else current_user.username.split('@')[0]
    return render_template("analytics.html", user_name=final_name, status_dict=status_dict, priority_dict=priority_dict)


# ================= AUTOMATED SCHEDULER & BRIEFING =================
def daily_morning_briefing():
    with app.app_context():
        print("\n🔔 [SCHEDULER WOKE UP]: Checking database for tasks due today...")
        today_str = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d %b %Y')
        users = User.query.all()
        
        for user in users:
            # 🌟 NAYA CHANGE 3: Email Validation Guard (ffwc fix)
            if user.username and '@' in user.username and '.' in user.username:
                due_tasks = Task.query.filter_by(user_id=user.id, due_date=today_str).filter(Task.status != 'Done').all()
                
                if due_tasks:
                    try:
                        task_list_text = "\n".join([f"- {t.name} (Priority: {t.priority})" for t in due_tasks])
                        display_name = user.display_name if user.display_name else user.username.split('@')[0]
                        
                        email_body = f"Good Morning {display_name}!\n\nHere is your daily briefing from TaskPro Elite. You have the following tasks due today:\n\n{task_list_text}\n\nLogin to your dashboard to complete them.\n\nHave a productive day!\n- TaskPro Elite AI"
                        
                        msg = MIMEText(email_body, 'plain')
                        msg['Subject'] = f"📅 Today's Agenda: {len(due_tasks)} Tasks Due"
                        msg['From'] = SYSTEM_EMAIL
                        msg['To'] = user.username
                        
                        server = smtplib.SMTP('smtp.gmail.com', 587)
                        server.starttls()
                        server.login(SYSTEM_EMAIL, SYSTEM_APP_PASSWORD)
                        server.send_message(msg)
                        server.quit()
                        print(f"✅ Daily Briefing email sent to {user.username}")
                    except Exception as e:
                        print(f"❌ Failed to send briefing to {user.username}: {e}")
            else:
                print(f"⚠️ Skipped invalid/fake email: {user.username}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=daily_morning_briefing, trigger="interval", minutes=1)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == "__main__":
    socketio.run(app, debug=True)
