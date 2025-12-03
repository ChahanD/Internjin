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
from models import User, Offer

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_globals():
    return dict(
        role=session.get('role', 'student'),
        lang=session.get('lang', 'en')
    )

@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['en', 'fr', 'jp']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

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
    offers_data = Offer.query.order_by(Offer.created_at.desc()).all()
    return render_template('offers.html', offers=offers_data)

@app.route('/offer/<int:offer_id>')
def offer_detail(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    return render_template('offer_detail.html', offer=offer)

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
        
        role = request.form.get('role', 'student')
        new_user = User(email=email, name=name, role=role)
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

@app.route('/recruiter/dashboard')
@login_required
def recruiter_dashboard():
    if current_user.role != 'recruiter':
        flash('Access denied. Recruiter role required.')
        return redirect(url_for('index'))
    my_offers = Offer.query.filter_by(recruiter_id=current_user.id).order_by(Offer.created_at.desc()).all()
    return render_template('recruiter/dashboard.html', offers=my_offers)

@app.route('/recruiter/offer/new', methods=['GET', 'POST'])
@login_required
def new_offer():
    if current_user.role != 'recruiter':
        flash('Access denied.')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        company = request.form.get('company')
        location = request.form.get('location')
        duration = request.form.get('duration')
        description = request.form.get('description')
        tags = request.form.get('tags')
        
        offer = Offer(
            title=title,
            company=company,
            location=location,
            duration=duration,
            description=description,
            tags=tags,
            recruiter_id=current_user.id
        )
        db.session.add(offer)
        db.session.commit()
        flash('Offer created successfully!')
        return redirect(url_for('recruiter_dashboard'))
        
    return render_template('recruiter/offer_form.html', action='create')

@app.route('/recruiter/offer/<int:offer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_offer(offer_id):
    if current_user.role != 'recruiter':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    offer = Offer.query.get_or_404(offer_id)
    if offer.recruiter_id != current_user.id:
        flash('You can only edit your own offers.')
        return redirect(url_for('recruiter_dashboard'))
        
    if request.method == 'POST':
        offer.title = request.form.get('title')
        offer.company = request.form.get('company')
        offer.location = request.form.get('location')
        offer.duration = request.form.get('duration')
        offer.description = request.form.get('description')
        offer.tags = request.form.get('tags')
        
        db.session.commit()
        flash('Offer updated successfully!')
        return redirect(url_for('recruiter_dashboard'))
        
    return render_template('recruiter/offer_form.html', offer=offer, action='edit')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
