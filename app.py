from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import hmac
import werkzeug.security

# नए पाइथन वर्जन के लिए safe_str_cmp एरर का फिक्स
werkzeug.security.safe_str_cmp = hmac.compare_digest
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-bhishmak'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///final_task.db'  # 🚀 बिल्कुल नया डेटाबेस नाम ताकि फ्रेश टेबल बने
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# डेटाबेस और लॉगिन मैनेजर सेटअप
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- डेटाबेस मॉडल्स (Models) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    
    # ✅ ये प्रॉपर्टीज मैन्युअली जोड़ दी हैं ताकि 'no such column: user.is_active' एरर कभी न आए
    @property
    def is_active(self):
        return True
    @property
    def is_authenticated(self):
        return True
    @property
    def is_anonymous(self):
        return False
    def get_id(self):
        return str(self.id)

# सही जगह पर यूजर लोडर
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='Todo')  # Todo, In Progress, Done
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# 🚀 रेंडर सर्वर के लिए बिल्कुल सही जगह पर टेबल बनाने का कोड
with app.app_context():
    db.create_all()

# --- वेबसाइट के सारे राउट्स (Routes) ---

@app.route('/')
@login_required
def index():
    todos = Todo.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', todos=todos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
            
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required
def add_todo():
    title = request.form.get('title')
    if title:
        new_todo = Todo(title=title, user_id=current_user.id)
        db.session.add(new_todo)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/update/<int:todo_id>/<string:status>')
@login_required
def update_todo(todo_id, status):
    todo = Todo.query.get_or_404(todo_id)
    if todo.user_id == current_user.id:
        todo.status = status
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:todo_id>')
@login_required
def delete_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    if todo.user_id == current_user.id:
        db.session.delete(todo)
        db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
