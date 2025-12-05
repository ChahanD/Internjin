from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///internjin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/offers'
app.config['UPLOAD_FOLDER_CV'] = 'static/uploads/cvs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

import os
from datetime import datetime
from werkzeug.utils import secure_filename

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Ensure upload directory exists
os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)

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
    if current_user.is_authenticated:
        role = current_user.role
    else:
        role = session.get('role', 'student')
        
    return dict(
        role=role,
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
    # Get filter parameters
    selected_locations = request.args.getlist('location')
    selected_durations = request.args.getlist('duration')
    selected_companies = request.args.getlist('company')
    
    # Base query
    query = Offer.query
    
    # Apply filters
    if selected_locations:
        query = query.filter(Offer.location.in_(selected_locations))
    if selected_durations:
        query = query.filter(Offer.duration.in_(selected_durations))
    if selected_companies:
        query = query.filter(Offer.company.in_(selected_companies))
        
    offers_data = query.order_by(Offer.created_at.desc()).all()
    
    # Get unique values for filters from ALL offers (not just filtered ones) to keep options visible
    all_offers = Offer.query.all()
    unique_locations = sorted(list(set(o.location for o in all_offers if o.location)))
    unique_companies = sorted(list(set(o.company for o in all_offers if o.company)))
    
    # Custom sort for durations
    duration_order = {
        "1 mois": 1,
        "3 mois": 3,
        "6 mois": 6,
        "9 mois": 9,
        "12 mois": 12, # Handle legacy if exists, but we filter it out for display if needed or map it
        "1 an": 12,
        "2 ans": 24
    }
    
    raw_durations = set(o.duration for o in all_offers if o.duration)
    # Filter out '12 mois' if '1 an' is preferred, or just keep what's in DB. 
    # User asked to remove '12 mois' filter.
    unique_durations = sorted(
        [d for d in raw_durations if d != "12 mois"], 
        key=lambda x: duration_order.get(x, 99)
    )
    
    return render_template('offers.html', 
                         offers=offers_data,
                         unique_locations=unique_locations,
                         unique_durations=unique_durations,
                         unique_companies=unique_companies,
                         selected_locations=selected_locations,
                         selected_durations=selected_durations,
                         selected_companies=selected_companies)

@app.route('/offer/<int:offer_id>')
def offer_detail(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    return render_template('offer_detail.html', offer=offer)

@app.route('/companies')
def companies_list():
    # Aggregate data from offers
    offers = Offer.query.all()
    companies_data = {}
    
    for offer in offers:
        if offer.company not in companies_data:
            companies_data[offer.company] = {
                'name': offer.company,
                'offer_count': 0,
                'locations': set(),
                'latest_offer_date': offer.created_at
            }
        
        companies_data[offer.company]['offer_count'] += 1
        companies_data[offer.company]['locations'].add(offer.location)
        if offer.created_at > companies_data[offer.company]['latest_offer_date']:
            companies_data[offer.company]['latest_offer_date'] = offer.created_at
            
    # Convert to list and sort by latest offer
    companies = sorted(companies_data.values(), key=lambda x: x['latest_offer_date'], reverse=True)
    
    return render_template('companies_list.html', companies=companies)

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
        location = request.form.get('location').title() if request.form.get('location') else None
        duration = request.form.get('duration')
        start_date = request.form.get('start_date')
        description = request.form.get('description')
        tags = request.form.get('tags')
        
        pdf_filename = None
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to filename to avoid collisions
                import time
                filename = f"{int(time.time())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                pdf_filename = filename

        offer = Offer(
            title=title,
            company=company,
            location=location,
            duration=duration,
            description=description,
            tags=tags,
            pdf_filename=pdf_filename,
            start_date=start_date,
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
        offer.location = request.form.get('location').title() if request.form.get('location') else None
        offer.duration = request.form.get('duration')
        offer.start_date = request.form.get('start_date')
        offer.description = request.form.get('description')
        offer.tags = request.form.get('tags')
        
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to filename to avoid collisions
                import time
                filename = f"{int(time.time())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                # Delete old file if exists
                if offer.pdf_filename:
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], offer.pdf_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                        
                offer.pdf_filename = filename
        
        db.session.commit()
        flash('Offer updated successfully!')
        return redirect(url_for('recruiter_dashboard'))
        
    return render_template('recruiter/offer_form.html', offer=offer, action='edit')

@app.route('/recruiter/offer/<int:offer_id>/delete', methods=['POST'])
@login_required
def delete_offer(offer_id):
    if current_user.role != 'recruiter':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    offer = Offer.query.get_or_404(offer_id)
    if offer.recruiter_id != current_user.id:
        flash('You can only delete your own offers.')
        return redirect(url_for('recruiter_dashboard'))
        
    # Delete associated PDF if exists
    if offer.pdf_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], offer.pdf_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            
    db.session.delete(offer)
    db.session.commit()
    flash('Offer deleted successfully!')
    return redirect(url_for('recruiter_dashboard'))

@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
def student_profile():
    if current_user.role != 'student':
        flash('Access denied. Student role required.')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.diploma = request.form.get('diploma')
        
        # Handle CV Upload
        if 'cv_file' in request.files:
            file = request.files['cv_file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to filename to prevent collisions
                timestamp = int(datetime.utcnow().timestamp())
                filename = f"{timestamp}_{filename}"
                
                # Ensure directory exists
                os.makedirs(app.config['UPLOAD_FOLDER_CV'], exist_ok=True)
                
                # Delete old CV if exists
                if current_user.cv_filename:
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER_CV'], current_user.cv_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                
                file.save(os.path.join(app.config['UPLOAD_FOLDER_CV'], filename))
                current_user.cv_filename = filename
        
        db.session.commit()
        flash('Profile updated successfully!')
        return redirect(url_for('student_profile'))
        
    return render_template('student/profile.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
