from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import secrets
import csv
import io
import os
import smtplib
from email.mime.text import MIMEText
import threading
from authlib.integrations.flask_client import OAuth

from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bhishmak_ka_secret_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trello_board_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 🚀 EMAIL SETTINGS (Tumhara Email aur Password)
SENDER_EMAIL = 'aparnathakur157@gmail.com'
APP_PASSWORD = 'igtxkngkafhblrav'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['GOOGLE_CLIENT_ID'] = '126513598147-gqe13705587dm1gbvhg6en6h4q32t1p0.apps.googleusercontent.com'
app.config['GOOGLE_CLIENT_SECRET'] = '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' 

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

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True)

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(300), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)

# 🚀 NAYA MODEL: Sub-Tasks / Checklists ke liye
class SubTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), default='Personal')
    priority = db.Column(db.String(20), default='Medium')
    due_date = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='Backlog')
    description = db.Column(db.Text, default='', nullable=True) 
    
    attachments = db.relationship('Attachment', backref='task', cascade='all, delete-orphan', lazy=True)
    # 🚀 NAYA RELATIONSHIP: Task aur SubTask ke beech
    subtasks = db.relationship('SubTask', backref='task', cascade='all, delete-orphan', lazy=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30))

with app.app_context():
    db.create_all()

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

def send_daily_brief():
    with app.app_context():
        users = User.query.all()
        for user in users:
            tasks = Task.query.filter_by(user_id=user.id).all()
            pending_tasks = [t for t in tasks if t.status != 'Done']
            
            if not pending_tasks:
                continue 
                
            total_pending = len(pending_tasks)
            high_priority = len([t for t in pending_tasks if t.priority == 'High'])
            
            subject = f"☀️ Your Daily TaskPro Brief: {total_pending} Tasks Pending!"
            body = f"Good Morning {user.username}!\n\nHere is a quick summary of your TaskPro Elite board for today:\n\n"
            body += f"📊 Total Pending Tasks: {total_pending}\n"
            body += f"🔴 High Priority / Urgent Tasks: {high_priority}\n\n"
            body += "Here are your tasks to focus on today:\n"
            
            for i, t in enumerate(pending_tasks, 1):
                due = t.due_date if t.due_date else "No deadline"
                body += f"  {i}. {t.name} (Due: {due})\n"
                
            body += "\nHave a productive day ahead!\n- TaskPro Elite AI 🤖"
            
            try:
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = SENDER_EMAIL
                msg['To'] = user.username 
                
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(SENDER_EMAIL, APP_PASSWORD)
                server.sendmail(SENDER_EMAIL, user.username, msg.as_string())
                server.quit()
            except:
                pass

if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=send_daily_brief, trigger="cron", hour=8, minute=0)
    scheduler.start()

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
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
        hashed_pw = generate_password_hash(random_safe_password, method='pbkdf2:sha256')
        user = User(username=email, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    session['profile_pic'] = picture
    flash(f"Welcome back! Logged in as {email} 🚀", "success")
    return redirect(url_for('home'))

@app.route("/")
@login_required
def home():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    today_dt = datetime.utcnow() + timedelta(hours=5, minutes=30)
    today_date_only = today_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    for t in tasks:
        t.is_overdue = False
        t.is_due_soon = False
        t.sort_score = 9999
        
        if t.due_date and t.status != 'Done':
            try:
                d = datetime.strptime(t.due_date, '%d %b %Y')
                delta = (d - today_date_only).days
                
                if delta < 0:
                    t.is_overdue = True
                    t.sort_score = 1 
                elif delta == 0 or delta == 1:
                    t.is_due_soon = True
                    t.sort_score = 2 
                else:
                    t.sort_score = 3 + delta
            except:
                t.sort_score = 1000
        elif t.status == 'Done':
            t.sort_score = 9999 
        else:
            priority_map = {'High': 500, 'Medium': 600, 'Low': 700}
            t.sort_score = priority_map.get(t.priority, 600)
            
    tasks.sort(key=lambda x: x.sort_score)
    
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.status == 'Done')
    
    if total_tasks > 0:
        progress_percent = round((done_tasks / total_tasks) * 100)
    else:
        progress_percent = 0
        
    return render_template("index.html", tasks=tasks, user_name=current_user.username, progress=progress_percent)

@app.route("/add", methods=["POST"])
@login_required
def add_task():
    name = request.form.get("task_name")
    category = request.form.get("category")
    priority = request.form.get("priority", "Medium")
    
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    auto_date = ist_now.strftime('%d %b %Y')

    if name:
        new_task = Task(name=name, user_id=current_user.id, category=category, priority=priority, due_date=auto_date, description='')
        db.session.add(new_task)
        db.session.commit()
        
        if priority == "High" or category == "Urgent":
            email_thread = threading.Thread(target=send_email_background, args=(current_user.username, name, priority, category))
            email_thread.start()

        flash("Task added! 🚀", "success")
    return redirect(url_for('home'))

@app.route("/edit/<int:tid>", methods=['GET', 'POST'])
@login_required
def edit_task(tid):
    task = Task.query.get(tid)
    if not task or task.user_id != current_user.id:
        return redirect(url_for('home'))
    if request.method == 'POST':
        task.name = request.form.get("task_name")
        task.category = request.form.get("category")
        task.priority = request.form.get("priority")
        task.status = request.form.get("status")
        task.due_date = request.form.get("due_date")
        db.session.commit()
        flash("Task updated! ✨", "success")
        return redirect(url_for('home'))
    return render_template("edit.html", task=task)

@app.route("/delete/<int:tid>")
@login_required
def delete_task(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
        flash("Task removed! 🗑️", "danger")
    return redirect(url_for('home'))

@app.route("/save_description", methods=["POST"])
@login_required
def save_description():
    data = request.get_json()
    task_id = data.get('task_id')
    desc_text = data.get('description')
    
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        task.description = desc_text
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# 🚀 --- NAYE AJAX ROUTES: SUB-TASKS KE LIYE --- 🚀
@app.route("/get_subtasks/<int:tid>")
@login_required
def get_subtasks(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        subtasks = SubTask.query.filter_by(task_id=tid).all()
        return jsonify([{"id": s.id, "title": s.title, "is_completed": s.is_completed} for s in subtasks])
    return jsonify([])

@app.route("/add_subtask/<int:tid>", methods=["POST"])
@login_required
def add_subtask(tid):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        data = request.get_json()
        title = data.get("title")
        if title:
            new_sub = SubTask(title=title, task_id=tid)
            db.session.add(new_sub)
            db.session.commit()
            return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/toggle_subtask/<int:sid>", methods=["POST"])
@login_required
def toggle_subtask(sid):
    sub = SubTask.query.get(sid)
    if sub and sub.task.user_id == current_user.id:
        sub.is_completed = not sub.is_completed
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/delete_subtask/<int:sid>", methods=["POST"])
@login_required
def delete_subtask(sid):
    sub = SubTask.query.get(sid)
    if sub and sub.task.user_id == current_user.id:
        db.session.delete(sub)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/upload_attachment/<int:tid>", methods=["POST"])
@login_required
def upload_attachment(tid):
    task = Task.query.get(tid)
    if not task or task.user_id != current_user.id:
        return redirect(url_for('home'))
        
    files = request.files.getlist('task_file')
    for file in files:
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_filename = f"task_{tid}_{secrets.token_hex(4)}_{filename}"
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            new_attachment = Attachment(file_path=f"/static/uploads/{unique_filename}", task_id=tid)
            db.session.add(new_attachment)
            
    db.session.commit()
    flash(f"{len(files)} File(s) attached successfully! 📎", "success")
    return redirect(url_for('home'))

@app.route("/remove_attachment/<int:aid>", methods=["POST"])
@login_required
def remove_attachment(aid):
    attachment = Attachment.query.get(aid)
    if attachment and attachment.task.user_id == current_user.id:
        file_path = attachment.file_path.lstrip('/') 
        try:
            if os.path.exists(file_path):
                os.remove(file_path) 
        except:
            pass
        db.session.delete(attachment)
        db.session.commit()
        flash("File deleted permanently! 🗑️", "success")
    return redirect(url_for('home'))

@app.route("/move/<int:tid>/<new_status>")
@login_required
def move_task(tid, new_status):
    task = Task.query.get(tid)
    if task and task.user_id == current_user.id:
        task.status = new_status
        db.session.commit()
    return redirect(url_for('home'))

@app.route("/clear_done", methods=["POST"])
@login_required
def clear_done():
    tasks_to_delete = Task.query.filter_by(user_id=current_user.id, status='Done').all()
    for task in tasks_to_delete:
        db.session.delete(task)
    db.session.commit()
    flash("All completed tasks cleared! 🧹", "success")
    return redirect(url_for('home'))

@app.route("/export")
@login_required
def export_tasks():
    user_tasks = Task.query.filter_by(user_id=current_user.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Task Name', 'Category', 'Priority', 'Current Status', 'Date Created', 'Description'])
    for t in user_tasks:
        writer.writerow([t.name, t.category, t.priority, t.status, t.due_date, t.description])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TaskPro_Elite_Backup.csv"}
    )

@app.route("/update_status", methods=["POST"])
@login_required
def update_status():
    data = request.get_json()
    task_id = data.get('task_id')
    new_status = data.get('new_status')
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        task.status = new_status
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

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
            session['profile_pic'] = f"https://ui-avatars.com/api/?name={user.username}&background=6366f1&color=fff"
            return redirect(url_for('home'))
        flash("Invalid credentials! ❌", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    session.pop('profile_pic', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
