from werkzeug.utils import secure_filename
from flask_uploads import UploadSet, configure_uploads, ALL
# from werkzeug import secure_filename, FileStorage
import pandas as pd
import os

from flask_wtf import CSRFProtect, FlaskForm
from datetime import datetime, timezone
import humanize
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import jwt_required, get_jwt_identity
from wtforms.validators import DataRequired, Email, EqualTo,Length,ValidationError,Optional,Regexp
from flask_wtf.csrf import generate_csrf, validate_csrf,CSRFError
from wtforms import SubmitField
from wtforms import StringField, SubmitField, FloatField,PasswordField,SelectField
from wtforms.validators import DataRequired
from flask import Flask, render_template, request, redirect, url_for, flash,jsonify, abort,session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user,login_required, logout_user, UserMixin,login_manager,current_user
from Crypto.Hash import SHA256
from flask_migrate import Migrate
from werkzeug.datastructures import MultiDict
from alembic import op
import json
from sqlalchemy import ForeignKey
from functools import wraps
import pandas as pd
import pymysql, logging

# from utils import load_config, generate_db_uri

import pandas as pd
import joblib
import pickle, sqlite3
import random, time
from datetime import timedelta


# Initialize Flask app
app = Flask(__name__)
application = app
#sqlite3 flask default db
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///members.db'


db = SQLAlchemy(app)
# csrf = CSRFProtect(app)
# csrf.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Define allowed file extensions
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


#connecting to an external database.
# Store database credentials in environment variables
# app.config['SECRET_KEY'] = 'english92'
# app.config['SQLALCHEMY_DATABASE_URI'] = generate_db_uri()
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
#     "pool_pre_ping": True,
#     "pool_recycle": 250
# }


class DeleteMemberForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Delete Member')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

    @classmethod
    def from_json(cls, data):
        # Implement logic to create a LoginForm object from JSON data
        # For example:
        email = data.get('email')
        password = data.get('password')
        return cls(email=email, password=password)
    


class MemberForm(FlaskForm):

    member_name = StringField('Member Name', validators=[Optional(), Length(min=2, max=100)])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(max=15), Regexp(regex='^\d+$', message="Phone number must contain only digits")])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=100)])
    area = StringField('Member Area', validators=[Optional(), Length(min=2, max=100)])
    parish = StringField('Member Area', validators=[Optional(), Length(min=2, max=100)])
    gender = SelectField('gender', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[DataRequired()])
    submit = SubmitField('Add Member')



def validate_email(self, field):
        if not field.data.endswith('@rcr.com'):
            raise ValidationError('Email must have the domain "@rcr.com".')


class WebmasterForm(FlaskForm):

    webmaster_name = StringField('Name', validators=[DataRequired(), Length(min=2, max=50)])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(max=15), Regexp(regex='^\d+$', message="Phone number must contain only digits")])
    email = StringField('Email', validators=[DataRequired(), Email(), validate_email])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message="Password mismatch")])
    submit = SubmitField('Register')



class AdminForm(FlaskForm):

    admin_name = StringField('Admin Name', validators=[DataRequired(), Length(min=2, max=50)])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(max=15), Regexp(regex='^\d+$', message="Phone number must contain only digits")])
    email = StringField('Email', validators=[DataRequired(), Email(), validate_email])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message="Password mismatch")])
    submit = SubmitField('Register')


class SearchForm(FlaskForm):
    search_term = StringField('Search Term')
    search_member = SubmitField('Search Member')

class SearchAdminForm(FlaskForm):
    search_term = StringField('Search Term')
    search_admin = SubmitField('Search Admin')

# #The User class defines the database model.

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_name = db.Column(db.String(100), nullable=False)
    parish = db.Column(db.String(100))
    area = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    last_edited_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_edited_by = db.Column(db.Integer, db.ForeignKey('webmaster.id'))
    deleted_by = db.Column(db.Integer, db.ForeignKey('webmaster.id'))
    is_present = db.Column(db.Boolean, default=False)
    registered_by_admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    registered_by_webmaster_id = db.Column(db.Integer, db.ForeignKey('webmaster.id'))

    # Relationships
    last_edited_by_webmaster = db.relationship('Webmaster', backref='edited_members', foreign_keys=[last_edited_by])
    deleted_by_webmaster = db.relationship('Webmaster', backref='deleted_members', foreign_keys=[deleted_by])
    registered_by_admin = db.relationship('Admin', backref='registered_members', foreign_keys=[registered_by_admin_id])
    registered_by_webmaster = db.relationship('Webmaster', backref='registered_members', foreign_keys=[registered_by_webmaster_id])

    def __repr__(self):
        return f'<Member {self.member_name}>'



class Admin(db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    admin_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=True)
    
    # Relationship with Webmaster
    # Specify the foreign key explicitly
    last_edited_by_webmaster_id = db.Column(db.Integer, db.ForeignKey('webmaster.id'))
    last_edited_by_webmaster = db.relationship('Webmaster', backref='admin_records', foreign_keys=[last_edited_by_webmaster_id])
    
    def __repr__(self):
        return f'<Admin {self.admin_name}>'

class Webmaster(db.Model):
    __tablename__ = 'webmaster'
    id = db.Column(db.Integer, primary_key=True)
    webmaster_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    password = db.Column(db.String(200))
    is_webmaster = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Webmaster {self.webmaster_name}>'



# preent 
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    marked_by_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)  # or 'user.id' if you're tracking by user
    member = db.relationship('Member', backref='attendances')
    marked_by = db.relationship('Admin', backref='attendances')  # or 'User' if you're tracking by user


class DeleteLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(50), nullable=False)  # E.g., 'admin', 'member'
    record_id = db.Column(db.Integer, nullable=False)  # ID of the deleted record
    deleted_by = db.Column(db.Integer, db.ForeignKey('webmaster.id'))  # ID of the webmaster who deleted
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationship with Webmaster
    deleted_by_webmaster = db.relationship('Webmaster', foreign_keys=[deleted_by])

    def __repr__(self):
        return f'<DeleteLog {self.record_type} {self.record_id} deleted by {self.deleted_by} at {self.deleted_at}>'




#### Event listener to convert admin_name to title case before insert and update
@event.listens_for(Admin, 'before_insert')
@event.listens_for(Admin, 'before_update')
def receive_before_insert(mapper, connection, target):
    target.admin_name = target.admin_name.title()
    target.email = target.email.lower()
    

@event.listens_for(Member, 'before_insert')
@event.listens_for(Member, 'before_update')
def receive_before_insert(mapper, connection, target):
    target.member_name = target.member_name.title()
    target.parish = target.parish.title()
    target.gender = target.gender.title()
    target.area = target.area.title()
    target.email = target.email.lower()

    

@event.listens_for(Webmaster, 'before_insert')
@event.listens_for(Webmaster, 'before_update')
def receive_before_insert(mapper, connection, target):
    target.webmaster_name = target.webmaster_name.title()
    target.email = target.email.lower()

#logged out session................
@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=20)
    session.modified = True
    session['last_activity'] = time.time()

@app.route('/check_activity', methods=['POST'])
def check_activity():
    if 'last_activity' in session:
        last_activity = session['last_activity']
        current_time = time.time()
        if current_time - last_activity > 1200:
            session.clear()
            return jsonify({'message': 'Session expired due to inactivity'}), 401
    return jsonify({'message': 'Activity checked'}), 200



# Wrapper for normal member login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You need to be logged in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Wrapper for admin login
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Wrapper for webmaster login
def webmaster_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_webmaster'):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_or_webmaster_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not (session.get('is_admin') or session.get('is_webmaster')):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


#delete route............
# Base form with CSRF protection enabled
class MyBaseForm(FlaskForm):
    class Meta:
        csrf = False

# Form for deleting a member
class DeleteMemberForm(MyBaseForm):
    submit = SubmitField('Delete')

# Search Admin: Searches for an admin by ID or email.

@app.route('/search_admin', methods=['POST'])
@webmaster_required
def search_admin():
    search_term = request.json.get('search_term')
    admin = Admin.query.filter((Admin.id == search_term) | (Admin.email == search_term)).first()
    if admin:
        return jsonify({'status': 'success', 'admin': admin.to_dict()})
    else:
        return jsonify({'status': 'error', 'message': 'Admin not found'})
    

# Search Member: Searches for a member by ID or email.

@app.route('/search_member', methods=['POST'])
@webmaster_required
def search_member():
    search_term = request.json.get('search_term')
    member = Member.query.filter((Member.id == search_term) | (Member.email == search_term)).first()
    if member:
        return jsonify({'status': 'success', 'member': member.to_dict()})
    else:
        return jsonify({'status': 'error', 'message': 'Member not found'})


## #The /register route handles user registration, hashing the password before storing it.
# @app.route('/register', methods=['GET', 'POST'])
# @admin_or_webmaster_required

# def register():
#     form = RegistrationForm()
    
#     if form.validate_on_submit():
#         try:
#             member_name = form.member_name.data
#             parish = form.parish.data
#             gender = form.gender.data
#             phone_number = form.phone_number.data
#             email = form.email.data
#             area = form.area.data
# # 
#             # Check for existing user
#             if Member.query.filter_by(email=email).first():
#                 flash('Email already registered!', 'danger')
#                 return redirect(url_for('register'))
           
#             if Member.query.filter_by(phone_number=phone_number).first():
#                 flash('Member already registered!', 'danger')
#                 return redirect(url_for('register'))
            

#             # Capture the current admin's and webmaster's IDs if available
#             admin_id = session.get('admin_id')
#             webmaster_id = session.get('webmaster_id')

#             # Create and save new member
#             new_member = Member(
#                 member_name=member_name,
#                 gender=gender,
#                 parish=parish,
#                 phone_number=phone_number,
#                 email=email,
#                 area=area,
#                 registered_by_admin_id=admin_id,  # Ensure this matches the model
#                 registered_by_webmaster_id=webmaster_id  # Ensure this matches the model
                 
#             )
#             db.session.add(new_member)
#             db.session.commit()
#             flash('Registration successful!', 'success')
#             return redirect(url_for('register'))
#         except Exception as e:
#             flash(f'Error: {str(e)}', 'danger')
#             return redirect(url_for('register'))

#     # Render form with validation errors (if any)
#     return render_template('register.html', form=form)


@login_manager.user_loader
def load_member(member_id):
    return Member.query.get(int(member_id))


# #homepage route...........
@app.route("/", methods=['GET', 'POST'])
def home():
        
        return redirect(url_for('login'))
        # return render_template("login.html")

#login route.....
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        # Clear any existing session data
        session.clear()

        email = form.email.data
        password = form.password.data

        # Check for webmaster login
        webmaster = Webmaster.query.filter_by(email=email).first()
        if webmaster:
            if check_password_hash(webmaster.password, password):
                session['user_id'] = webmaster.id
                session['email'] = webmaster.email
                session['is_webmaster'] = True
                flash('Login successful as Webmaster!', 'success')
                return redirect(url_for('webmaster_dashboard'))
            else:
                flash('Login failed. Incorrect password.', 'danger')

        # Check for admin login
        admin = Admin.query.filter_by(email=email).first()
        if admin:
            if check_password_hash(admin.password, password):
                session['user_id'] = admin.id
                session['email'] = admin.email
                session['is_admin'] = True
                flash('Login successful as Admin!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Login failed. Incorrect password.', 'danger')
        else:
            flash('Login failed. Admin not found.', 'danger')

        # If login fails
        flash('Login failed. Check your credentials and try again.', 'danger')

    return render_template('login.html', form=form)

 
# Admin registration route
@app.route('/register_admin', methods=['GET', 'POST'])
# @webmaster_required
def register_admin():

    form = RegisterAdminForm()
    if form.validate_on_submit():
        admin_name = form.admin_name.data
        phone_number = form.phone_number.data
        email = form.email.data
        password = form.password.data
        confirm_password = generate_password_hash(password)
        is_admin = True  # Ensure the new member is an webmaster

        # Check if member email already exists
        existing_admin = Admin.query.filter_by(email=email).first()
        if existing_admin:
            flash('Email already registered!', 'danger')
            return redirect(url_for('register_admin'))

        existing_admin = Admin.query.filter_by(admin_name=admin_name).first()
        if existing_admin:
            flash('Admin already registered!', 'danger')
            return redirect(url_for('register_admin'))
        
        existing_admin = Admin.query.filter_by(phone_number=phone_number).first()
        if existing_admin:
            flash('Admin already registered!', 'danger')
            return redirect(url_for('register_admin'))

        # If no duplicates proceed...
        new_admin = Admin(
            admin_name=admin_name,
            phone_number=phone_number,
            email=email,
            password=confirm_password,
            is_admin=is_admin
        )
        db.session.add(new_admin)
        db.session.commit()

        flash('New admin registered successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('register_admin.html', form=form)


#webmaster registration ................
# Admin registration route
@app.route('/register_webmaster', methods=['GET', 'POST'])
# @webmaster_required
def register_webmaster():

    form = RegisterWebmasterForm()
    if form.validate_on_submit():
        webmaster_name = form.webmaster_name.data
        phone_number = form.phone_number.data
        email = form.email.data
        password = form.password.data
        confirm_password = generate_password_hash(password)
        is_webmaster = True  # Ensure the new member is an webmaster

        # Check if member email already exists
        existing_webmaster = Webmaster.query.filter_by(email=email).first()
        if existing_webmaster:
            flash('Email already registered!', 'danger')
            return redirect(url_for('register_webmaster'))

        existing_webmaster = Webmaster.query.filter_by(webmaster_name=webmaster_name).first()
        if existing_webmaster:
            flash('Webmaster already registered!', 'danger')
            return redirect(url_for('register_webmaster'))
        
        existing_webmaster = Webmaster.query.filter_by(phone_number=phone_number).first()
        if existing_webmaster:
            flash('Webmaster already registered!', 'danger')
            return redirect(url_for('register_webmaster'))

        # If no duplicates proceed...
        new_webmaster = Webmaster(
            webmaster_name=webmaster_name,
            phone_number=phone_number,
            email=email,
            password=confirm_password,
            is_webmaster=is_webmaster
        )

        db.session.add(new_webmaster)
        db.session.commit()

        flash('New Webmaster registered successfully!', 'success')
        return redirect(url_for('webmaster_dashboard'))

    return render_template('register_webmaster.html', form=form)




#get attendance

@app.route('/attendance_records', methods=['GET'])
def attendance_records():
    attendances = Attendance.query.all()
    results = []
    for attendance in attendances:
        results.append({
            'id': attendance.id,
            'member_id': attendance.member_id,
            'timestamp': attendance.timestamp,
            'marked_by_id': attendance.marked_by_id,
            'marked_by_name': attendance.marked_by.name  # or similar attribute
        })
    return jsonify(results)


#members route 
@app.route('/members')
# @admin_required
@webmaster_required

def show_members():
    members = Member.query.all()
    admins = Admin.query.all()
    for member in members:
        print(f"Registered by Admin ID: {member.registered_by_admin_id}")
    return render_template('members.html', members=members, admins=admins) 
 

#show all admins in table route 
@app.route('/admins')
# @webmaster_dashboard

def show_admins():
    webmasters = Webmaster.query.all()
    admins = Admin.query.all()
    return render_template('admins.html', admins=admins, webmasters=webmasters)


#show all admins in table route 
@app.route('/webmasters')
@webmaster_required

def show_webmasters():
    webmasters = Webmaster.query.all()
    return render_template('webmaster.html', webmasters=webmasters)


# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

#####################################################################
@app.route('/webmaster_dashboard', methods=['GET', 'POST'])

def webmaster_dashboard():
   
    member_form = MemberForm()
    admin_form = AdminForm()
    search_form = SearchForm()
    search_admin_form = SearchAdminForm()
    
    if search_form.validate_on_submit() and 'search_member' in request.form:
        search_term = search_form.search_term.data
        # Logic to search for the member
        member = Member.query.filter_by(email=search_term).first()  # Adjust based on your search logic
        return render_template('webmaster_dashboard.html', member=member, member_form=member_form, admin_form=admin_form, search_form=search_form, search_admin_form=search_admin_form)

    if search_admin_form.validate_on_submit() and 'search_admin' in request.form:
        search_term = search_admin_form.search_term.data
        # Logic to search for the admin
        admin = Admin.query.filter_by(email=search_term).first()  # Adjust based on your search logic
        return render_template('webmaster_dashboard.html', admin=admin, member_form=member_form, admin_form=admin_form, search_form=search_form, search_admin_form=search_admin_form)
    
    return render_template('webmaster_dashboard.html', member_form=member_form, admin_form=admin_form, search_form=search_form, search_admin_form=search_admin_form)

@app.route('/add_member', methods=['GET', 'POST'])
@login_required
@admin_or_webmaster_required
def add_member():
    form = RegistrationForm()
    if form.validate_on_submit():
        new_member = Member(
            member_name=form.member_name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            area=form.area.data,
            parish=form.parish.data,
            gender=form.gender.data,
            registered_by_admin_id=current_user.id if current_user.is_admin else None,
            registered_by_webmaster_id=current_user.id if not current_user.is_admin else None
        )
        db.session.add(new_member)
        db.session.commit()
        
        # Log the action
        log_action('add_member', current_user.id)
        
        flash('Member added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))  # Adjust if necessary

    return render_template('add_member.html', form=form)



@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
@admin_or_webmaster_required
def edit_member(member_id):
    member = Member.query.get_or_404(member_id)
    form = RegistrationForm(obj=member)
    
    if form.validate_on_submit():
        member.member_name = form.member_name.data
        member.phone_number = form.phone_number.data
        member.email = form.email.data
        member.area = form.area.data
        member.parish = form.parish.data
        member.gender = form.gender.data
        member.last_edited_at = datetime.utcnow()
        member.last_edited_by = current_user.id
        
        db.session.commit()
        
        # Log the action
        log_action('edit_member', current_user.id)
        
        flash('Member updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))  # Adjust if necessary

    return render_template('edit_member.html', form=form, member=member)


@app.route('/delete_member/<int:member_id>', methods=['POST'])
@login_required
@admin_or_webmaster_required
def delete_member(member_id):
    member = Member.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    
    # Log the action
    log_action('delete_member', current_user.id)
    
    flash('Member deleted successfully!', 'success')
    return jsonify({'status': 'success'})


@app.route('/add_admin', methods=['GET', 'POST'])
@login_required
@webmaster_required
def add_admin():
    form = AdminForm()
    if form.validate_on_submit():
        new_admin = Admin(
            email=form.email.data,
            password=generate_password_hash(form.password.data),
            admin_name=form.name.data,
            phone_number=form.phone_number.data,
            is_admin=True,
        )
        db.session.add(new_admin)
        db.session.commit()
        
        # Log the action
        log_action('add_admin', current_user.id)
        
        flash('Admin added successfully!', 'success')
        return redirect(url_for('webmaster_dashboard'))  # Adjust if necessary

    return render_template('add_admin.html', form=form)

@app.route('/edit_admin/<int:admin_id>', methods=['GET', 'POST'])
@login_required
@webmaster_required
def edit_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    form = AdminForm(obj=admin)
    
    if form.validate_on_submit():
        admin.email = form.email.data
        if form.password.data:
            admin.password = generate_password_hash(form.password.data)
        admin.admin_name = form.name.data
        admin.phone_number = form.phone_number.data
        
        db.session.commit()
        
        # Log the action
        log_action('edit_admin', current_user.id)
        
        flash('Admin updated successfully!', 'success')
        return redirect(url_for('webmaster_dashboard'))  # Adjust if necessary

    return render_template('edit_admin.html', form=form, admin=admin)


@app.route('/delete_admin/<int:admin_id>', methods=['POST'])
@login_required
@webmaster_required
def delete_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    db.session.delete(admin)
    db.session.commit()
    
    # Log the action
    log_action('delete_admin', current_user.id)
    
    flash('Admin deleted successfully!', 'success')
    return jsonify({'status': 'success'})

#Helper Function for Logging Actions

def log_action(action_type, user_id):
    log = DeleteLog(
        action_type=action_type,
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()

#upload
@app.route('/upload', methods=['POST'])
@webmaster_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            
            # Ensure columns are consistent with Member model
            required_columns = {'member_name', 'email', 'phone_number', 'parish', 'area', 'gender'}
            if not required_columns.issubset(df.columns):
                return jsonify({'message': 'Invalid file format. Missing required columns.'}), 400
            
            members_data = df.to_dict(orient='records')
            existing_members = {member.email for member in Member.query.all()}
            new_members = []
            duplicates = []
            
            for data in members_data:
                if data.get('email') in existing_members:
                    duplicates.append(data)
                else:
                    new_members.append(data)
            
            for member_data in new_members:
                member = Member(
                    member_name=member_data.get('member_name'),
                    email=member_data.get('email'),
                    phone_number=member_data.get('phone_number'),
                    parish=member_data.get('parish'),
                    area=member_data.get('area'),
                    gender=member_data.get('gender'),
                    last_edited_by=current_user.id,  # Track the user who performs the operation
                    last_edited_at=datetime.utcnow()
                )
                db.session.add(member)
            
            db.session.commit()
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'duplicates': duplicates,
                'new_members_count': len(new_members)
            })
        
        except Exception as e:
            return jsonify({'message': f'Error processing file: {e}'}), 500
    
    return jsonify({'message': 'Invalid file type'}), 400


@app.route('/mark_present', methods=['POST'])
@admin_or_webmaster_required  # Ensure both admins and webmasters can access this endpoint
def mark_present():
    member_id = request.json.get('member_id')
    member = Member.query.get(member_id)
    
    if not member:
        return jsonify({'status': 'error', 'message': 'Member not found'})
    
    # Check if the user is logged in and has an appropriate role
    if not current_user.is_authenticated:
        return jsonify({'status': 'error', 'message': 'User not authenticated'})

    # Mark the member as present
    member.is_present = True
    member.last_edited_by = current_user.id  # Track who marked the attendance
    member.last_edited_at = datetime.utcnow()  # Update the timestamp

    db.session.commit()

    return jsonify({'status': 'success', 'message': 'Member marked as present'})


############################################################################################



       
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)


