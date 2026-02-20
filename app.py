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
from models import User, Offer, Application
from pypdf import PdfReader
import json

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.template_filter('from_json')
def from_json_filter(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except:
        return {}

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
        required_skills = request.form.get('required_skills')
        
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
            required_skills=required_skills,
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
        offer.required_skills = request.form.get('required_skills')
        
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
        
        # Recalculate compatibility scores for all existing applications of this offer
        for app_record in offer.applications:
            import json
            try:
                final_data = json.loads(app_record.extracted_data)
                
                compatibility_score = 0.0
                if offer.required_skills:
                    req_skills = [s.strip().lower() for s in offer.required_skills.split(',') if s.strip()]
                    student_skills_raw = final_data.get('skills') or ''
                    student_skills = [s.strip().lower() for s in student_skills_raw.split(',') if s.strip()]
                    experience_text = (final_data.get('experience') or '').lower()
                    
                    if req_skills:
                        match_count = 0
                        for rs in req_skills:
                            if rs in student_skills or rs in experience_text:
                                match_count += 1
                        compatibility_score = (match_count / len(req_skills)) * 100
                else:
                    offer_text = ((offer.title or "") + " " + (offer.description or "") + " " + (offer.tags or "")).lower()
                    student_text = ((final_data.get('skills') or '') + " " + (final_data.get('experience') or '')).lower()
                    
                    offer_words = set(offer_text.split())
                    student_words = set(student_text.split())
                    
                    overlap = offer_words.intersection(student_words)
                    if len(offer_words) > 0:
                        compatibility_score = min(len(overlap) / (len(offer_words) * 0.1) * 100, 100.0)
                        
                app_record.compatibility_score = round(compatibility_score, 1)
            except Exception as e:
                # If JSON parsing fails, just leave the score as is
                pass
                
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

def extract_text_from_pdf(filepath):
    try:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def analyze_cv_text(text):
    data = {
        'name': '',
        'email': '',
        'phone': '',
        'diploma': '',
        'github': '',
        'nationality': '',
        'languages': '',
        'skills': '',
        'experience': ''
    }
    
    # 0. Clean "spaced out" text often found in PDFs (e.g., "S k i l l s")
    import re
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if len(line) > 10 and line.count(' ') / len(line) > 0.4:
            cleaned_line = line.replace('  ', '<SPACE>').replace(' ', '').replace('<SPACE>', ' ')
            cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)
    
    clean_text = '\n'.join(cleaned_lines)
    
    # 1. Extract Email Using Regex
    email_regex = r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
    email_match = re.search(email_regex, clean_text)
    if email_match:
        data['email'] = email_match.group(1)

    # 2. Extract Phone Number (Basic Regex)
    phone_regex = r"(\+?\d{1,4}?[\s.-]?\(?\d{1,3}?\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9})"
    phone_match = re.search(phone_regex, clean_text)
    if phone_match:
         data['phone'] = phone_match.group(1)
         
    # 3. Extract Name (Heuristics: Usually at the top, Title Case)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    if lines:
        possible_names = []
        for line in lines[:8]: # Look in first 8 lines
            # Name typical structure: 2-4 words, First letters capitalized or ALL CAPS
            words = line.split()
            if 1 < len(words) < 5 and all(word.isalpha() or '-' in word for word in words):
                possible_names.append(line)
        
        if possible_names:
            bad_words = ["resume", "cv", "curriculum", "vitae", "contact", "profile"]
            for p_name in possible_names:
                if not any(bw in p_name.lower() for bw in bad_words):
                    # Clean up capitalization for display
                    data['name'] = p_name.title()
                    break

    # 4. Extract Github
    github_regex = r"(?i)(?:github\.com/)([a-zA-Z0-9-]+)"
    github_match = re.search(github_regex, clean_text)
    if github_match:
        data['github'] = "https://github.com/" + github_match.group(1)
    else:
        # Sometimes it's just written as "GitHub: username"
        github_regex_2 = r"(?i)github\s*[:\-]?\s*([a-zA-Z0-9-]+)"
        github_match_2 = re.search(github_regex_2, clean_text)
        if github_match_2:
            data['github'] = "https://github.com/" + github_match_2.group(1)

    # 5. Extract Nationality
    nationalities = ['french', 'english', 'american', 'japanese', 'chinese', 'indian', 'german', 'spanish', 'italian', 'canadian']
    words = set(re.split(r'\W+', clean_text.lower()))
    
    # Very naive approach: If it says "Nationality: French" or just finds the word near the top
    nat_regex = r"(?i)(?:nationality|nationalité)\s*[:\-]\s*([A-Za-z]+)"
    nat_match = re.search(nat_regex, clean_text)
    if nat_match:
        data['nationality'] = nat_match.group(1).title()
    else:
        # Fallback: check first 500 characters for common nationalities
        top_text = clean_text[:500].lower()
        for nat in nationalities:
            if nat in top_text:
                data['nationality'] = nat.title()
                break

    # 6. Extract Languages
    languages_list = ['french', 'english', 'spanish', 'german', 'japanese', 'chinese', 'mandarin', 'italian', 'arabic', 'russian', 'portuguese', 'korean']
    found_langs = []
    
    # Try to find a language section, or just scan the document
    for lang in languages_list:
        if re.search(r'\b' + lang + r'\b', clean_text.lower()):
            found_langs.append(lang.title())
    
    # Exclude nationalities mistakenly picked up as languages if they are the only match 
    if len(found_langs) > 0:
         data['languages'] = ", ".join(found_langs)

    # 7. Extract Diploma / Education
    # Look for keywords like "Master", "Bachelor", "Degree", "Engineering", "Licence"
    edu_regex = r"(?i)(?:master|bachelor|degree|licence|engineering|ingénieur)(?:'s)?\s*(?:in|of|en)?\s*([a-zA-Z\s]+)"
    edu_match = re.search(edu_regex, clean_text)
    if edu_match:
        # Capture the context line
        for line in lines:
            if edu_match.group(0).lower() in line.lower():
                data['diploma'] = line.strip()
                break

    # 8. Extract Skills (Expanded List)
    skills_list = [
        'python', 'java', 'c++', 'c#', 'c', 'javascript', 'html', 'css', 'react', 'angular', 'vue', 
        'node.js', 'django', 'flask', 'spring', 'sql', 'mysql', 'postgresql', 'mongodb', 
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git', 'linux', 'machine learning', 
        'deep learning', 'data analysis', 'pandas', 'numpy', 'tensorflow', 'pytorch', 'scikit-learn',
        'php', 'ruby', 'swift', 'kotlin', 'go', 'rust', 'typescript', 'figma', 'ros', 'ros2', 'arduino', 'stm32',
        'project management', 'agile', 'scrum', 'leadership', 'communication', 'teamwork',
        'problem solving', 'management', 'marketing', 'sales', 'finance', 'accounting', 'seo'
    ]
    
    words = set(re.split(r'\W+', clean_text.lower()))
    found_skills = []
    text_lower = clean_text.lower()
    
    for skill in skills_list:
        if ' ' in skill or skill in ['c++', 'c#', 'node.js', 'ros2']: 
            if skill in text_lower:
                found_skills.append(skill.upper() if len(skill) <= 3 else skill.title())
        elif skill in words:
            found_skills.append(skill.upper() if len(skill) <= 3 else skill.title())
            
    data['skills'] = ", ".join(found_skills)

    # 9. Extract Experience Summary
    exp_regex = r"(?i)(?:experience|work experience|emploi|professionnelles)(.*?)(?:education|skills|projects|interests|$)"
    exp_match = re.search(exp_regex, clean_text, re.DOTALL)
    if exp_match:
        snippet = exp_match.group(1).strip()
        data['experience'] = snippet[:300] + ('...' if len(snippet) > 300 else '')

    return data

@app.route('/offer/<int:offer_id>/apply', methods=['GET', 'POST'])
@login_required
def apply_to_offer(offer_id):
    if current_user.role != 'student':
        flash('Only students can apply.')
        return redirect(url_for('offer_detail', offer_id=offer_id))
        
    offer = Offer.query.get_or_404(offer_id)
    
    # Check if already applied
    existing_application = Application.query.filter_by(student_id=current_user.id, offer_id=offer_id).first()
    if existing_application:
        flash('You have already applied to this offer.')
        return redirect(url_for('offer_detail', offer_id=offer_id))

    if request.method == 'POST':
        if 'cv_file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['cv_file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            import time
            filename = f"app_{int(time.time())}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER_CV'], filename)
            
            # Ensure directory exists
            os.makedirs(app.config['UPLOAD_FOLDER_CV'], exist_ok=True)
            
            file.save(filepath)
            
            # Parsing logic
            text = extract_text_from_pdf(filepath)
            parsed_data = analyze_cv_text(text)
            
            return render_template('student/apply_step2.html', offer=offer, cv_filename=filename, parsed_data=parsed_data)
            
    return render_template('student/apply_step1.html', offer=offer)

@app.route('/offer/<int:offer_id>/apply/confirm', methods=['POST'])
@login_required
def confirm_application(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    
    cv_filename = request.form.get('cv_filename')
    
    # Gather final data
    final_data = {
        'name': request.form.get('name'),
        'email': request.form.get('email'),
        'phone': request.form.get('phone'),
        'diploma': request.form.get('diploma'),
        'github': request.form.get('github'),
        'nationality': request.form.get('nationality'),
        'languages': request.form.get('languages'),
        'skills': request.form.get('skills'),
        'experience': request.form.get('experience')
    }
    
    # Calculate compatibility based on required_skills
    compatibility_score = 0.0
    
    if offer.required_skills:
        # Split and clean required skills (e.g. "Python, AWS, React")
        req_skills = [s.strip().lower() for s in offer.required_skills.split(',') if s.strip()]
        
        # Extract student skills (comma separated from the parser, or manually entered)
        student_skills_raw = final_data.get('skills') or ''
        student_skills = [s.strip().lower() for s in student_skills_raw.split(',') if s.strip()]
        
        experience_text = (final_data.get('experience') or '').lower()
        
        if req_skills:
            match_count = 0
            for rs in req_skills:
                # Check if the required skill is exactly in the student's skills list
                # Or if the required skill is a substring of the student's free text experience
                if rs in student_skills or rs in experience_text:
                    match_count += 1
            
            compatibility_score = (match_count / len(req_skills)) * 100
    else:
        # Fallback to naive logic if recruiter didn't provide required skills
        offer_text = ((offer.title or "") + " " + (offer.description or "") + " " + (offer.tags or "")).lower()
        student_text = ((final_data.get('skills') or '') + " " + (final_data.get('experience') or '')).lower()
        
        offer_words = set(offer_text.split())
        student_words = set(student_text.split())
        
        overlap = offer_words.intersection(student_words)
        if len(offer_words) > 0:
            compatibility_score = min(len(overlap) / (len(offer_words) * 0.1) * 100, 100.0)
    
    application = Application(
        student_id=current_user.id,
        offer_id=offer_id,
        cv_filename=cv_filename,
        extracted_data=json.dumps(final_data),
        compatibility_score=round(compatibility_score, 1),
        status='pending'
    )
    
    db.session.add(application)
    db.session.commit()
    
    return render_template('student/apply_success.html', offer=offer)

@app.route('/student/applications')
@login_required
def student_applications():
    if current_user.role != 'student':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    applications = Application.query.filter_by(student_id=current_user.id).order_by(Application.created_at.desc()).all()
    return render_template('student/applications.html', applications=applications)

@app.route('/recruiter/offer/<int:offer_id>/applications')
@login_required
def view_offer_applications(offer_id):
    if current_user.role != 'recruiter':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    offer = Offer.query.get_or_404(offer_id)
    if offer.recruiter_id != current_user.id:
        flash('You can only view applications for your own offers.')
        return redirect(url_for('recruiter_dashboard'))
        
    applications = Application.query.filter_by(offer_id=offer_id).order_by(Application.created_at.desc()).all()
    
    # Calculate match details for each application to display in a tooltip
    if offer.required_skills:
        req_skills = [s.strip().lower() for s in offer.required_skills.split(',') if s.strip()]
        for app_record in applications:
            import json
            try:
                final_data = json.loads(app_record.extracted_data)
                student_skills_raw = final_data.get('skills') or ''
                student_skills = [s.strip().lower() for s in student_skills_raw.split(',') if s.strip()]
                experience_text = (final_data.get('experience') or '').lower()
                
                matched = []
                missing = []
                for rs in req_skills:
                    if rs in student_skills or rs in experience_text:
                        matched.append(rs.title())
                    else:
                        missing.append(rs.title())
                
                app_record.match_details = {
                    'matched': matched,
                    'missing': missing
                }
            except Exception:
                app_record.match_details = None
    
    return render_template('recruiter/applications.html', offer=offer, applications=applications)

@app.route('/recruiter/application/<int:application_id>')
@login_required
def view_application(application_id):
    if current_user.role != 'recruiter':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    application = Application.query.get_or_404(application_id)
    if application.offer.recruiter_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('recruiter_dashboard'))
        
    # We no longer mark as viewed to keep it hidden from the student
    # if application.status == 'pending':
    #     application.status = 'viewed'
    #     db.session.commit()
        
    return render_template('recruiter/application_detail.html', application=application)

@app.route('/student/application/<int:application_id>/delete', methods=['POST'])
@login_required
def delete_application(application_id):
    if current_user.role != 'student':
        flash('Access denied.')
        return redirect(url_for('index'))
        
    application = Application.query.get_or_404(application_id)
    
    # Ensure the application belongs to the current user
    if application.student_id != current_user.id:
        flash('You can only delete your own applications.')
        return redirect(url_for('student_applications'))
        
    # Optional: Prevent deletion if status is already accepted
    # if application.status == 'accepted':
    #     flash('Cannot delete an accepted application.')
    #     return redirect(url_for('student_applications'))
        
    db.session.delete(application)
    db.session.commit()
    flash('Application deleted successfully.')
    return redirect(url_for('student_applications'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
