from app import app, db
from models import Application, User
from flask import render_template
from flask_login import login_user

with app.app_context():
    with app.test_request_context():
        user = User.query.filter_by(role='recruiter').first()
        if user:
            login_user(user)
        
        app_record = Application.query.first()
        if not app_record:
            print("No application found")
        else:
            try:
                # Actual render of the file
                output = render_template('recruiter/application_detail.html', application=app_record, current_user=user)
                print("Template rendered successfully.")
            except Exception as e:
                import traceback
                traceback.print_exc()
