from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///internjin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Import models after db init to avoid circular imports
from models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_role():
    return dict(role=session.get('role', 'student'))

@app.route('/switch_role/<role>')
def switch_role(role):
    if role in ['student', 'recruiter']:
        session['role'] = role
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/offers')
def offers():
    # Dummy data for offers
    offers_data = [
        {
            "id": 1,
            "title": "Software Engineer Intern",
            "company": "TechJapan",
            "location": "Tokyo",
            "duration": "6 months",
            "tags": ["Python", "React", "English"]
        },
        {
            "id": 2,
            "title": "Marketing Assistant",
            "company": "Global Corp",
            "location": "Osaka",
            "duration": "4 months",
            "tags": ["Marketing", "Japanese N3"]
        },
        {
            "id": 3,
            "title": "Business Developer",
            "company": "StartUp Kyoto",
            "location": "Kyoto",
            "duration": "6 months",
            "tags": ["Sales", "English", "French"]
        }
    ]
    return render_template('offers.html', offers=offers_data)

@app.route('/companies')
def companies_list():
    return render_template('companies_list.html')

@app.route('/companies/solutions')
def company_solutions():
    return render_template('company_solutions.html')

@app.route('/companies/packs')
def company_packs():
    return render_template('company_packs.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/language')
def language():
    return render_template('language.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists')
            return redirect(url_for('register'))
        
        new_user = User(email=email, name=name)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('index'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
