import hmac
import werkzeug.security
werkzeug.security.safe_str_cmp = hmac.compare_digest
import os
from flask import Flask, render_template, url_for, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, date

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bhishmak_kanban_secret_key_101'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kanban_taskpro.db' 

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    tasks = db.relationship('Todo', backref='author', lazy=True)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.String(20), default='Medium')
    category = db.Column(db.String(50), default='General')
    status = db.Column(db.String(20), default='Backlog') 
    due_date = db.Column(db.Date)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



@app.route('/', methods=['POST', 'GET'])
@login_required
def home():
    if request.method == 'POST':
        task_content = request.form['content']
        task_priority = request.form.get('priority', 'Medium')
        task_category = request.form.get('category', 'General')
        
        date_str = request.form.get('due_date')
        task_due_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        
       
        new_task = Todo(
            content=task_content, 
            priority=task_priority, 
            category=task_category,
            due_date=task_due_date,
            status='Backlog', 
            author=current_user
        )
        db.session.add(new_task)
        db.session.commit()
        flash('Task added to Backlog! 📋', 'success')
        return redirect('/')
    
    all_tasks = Todo.query.filter_by(author=current_user).order_by(Todo.date_created.desc()).all()
    
  
    board = {
        'Backlog': [t for t in all_tasks if t.status == 'Backlog'],
        'To Do': [t for t in all_tasks if t.status == 'To Do'],
        'In Progress': [t for t in all_tasks if t.status == 'In Progress'],
        'Done': [t for t in all_tasks if t.status == 'Done']
    }
    
    return render_template('index.html', board=board, today=date.today())



from flask import jsonify 

@app.route('/move_next/<int:id>')
@login_required
def move_next(id):
    task = Todo.query.get_or_404(id)
    status_flow = ['Backlog', 'To Do', 'In Progress', 'Done']
    
    if task.status in status_flow:
        current_index = status_flow.index(task.status)
        if current_index < len(status_flow) - 1:
            task.status = status_flow[current_index + 1]
            db.session.commit()
            
            
            return jsonify({
                'success': True, 
                'new_status': task.status, 
                'task_id': task.id
            })
            
    return jsonify({'success': False, 'error': 'Cannot move further'})


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    task = Todo.query.get_or_404(id)
    if request.method == 'POST':
        task.content = request.form['content']
        task.category = request.form['category']
        task.priority = request.form['priority']
        task.status = request.form['status']
        
        date_str = request.form.get('due_date')
        task.due_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        
        db.session.commit()
        flash('Task Updated Successfully! ✨', 'success')
        return redirect('/')
        
    return render_template('edit.html', task=task)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    task = Todo.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()

    
    return jsonify({
        'success': True,
        'task_id': id
    })


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect('/')
    if request.method == 'POST':
        hashed_pw = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(username=request.form['username'], password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect('/')
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
