from werkzeug.utils import secure_filename
from flask_uploads import UploadSet, configure_uploads, ALL
# from werkzeug import secure_filename, FileStorage
import pandas as pd
import os 
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from datetime import datetime, timezone
import humanize
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import jwt_required, get_jwt_identity
from wtforms.validators import DataRequired, Email, EqualTo,Length,ValidationError,Optional,Regexp
from flask_wtf.csrf import generate_csrf, validate_csrf,CSRFError
from wtforms import SubmitField
from wtforms import StringField, SubmitField, FloatField,PasswordField,SelectField,BooleanField
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
from flask_login import UserMixin

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
csrf = CSRFProtect(app)
login_manager = LoginManager()
login_manager.init_app(app)
# db.init_app(app)


# # Set the upload folder (you can choose a temporary folder or memory storage)

UPLOAD_FOLDER = '/path/to/uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Allowed file extensions
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


##..............database table..............#############
# #The User class defines the database model.
class Member(UserMixin, db.Model):
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

class Admin(UserMixin, db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    admin_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    password = db.Column(db.String(200))
    is_admin_flag = db.Column(db.Boolean, default=True)  # Renamed to avoid conflict
    
    # Relationship with Webmaster
    last_edited_by_webmaster_id = db.Column(db.Integer, db.ForeignKey('webmaster.id'))
    last_edited_by_webmaster = db.relationship('Webmaster', backref='admin_records', foreign_keys=[last_edited_by_webmaster_id])
    
    @property
    def is_admin(self):
        return self.is_admin_flag

class Webmaster(UserMixin, db.Model):
    __tablename__ = 'webmaster'
    id = db.Column(db.Integer, primary_key=True)
    webmaster_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    password = db.Column(db.String(200))
    is_webmaster = db.Column(db.Boolean, default=True)

    @property
    def is_admin(self):
        return self.is_webmaster


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


#Helper Function for Logging Actions

def log_action(action_type, user_id, record_type=None, record_id=None):
    if action_type == 'delete_admin':
        delete_log = DeleteLog(
            record_type=record_type,
            record_id=record_id,
            deleted_by=user_id
        )
        db.session.add(delete_log)
        db.session.commit()
    # Handle other action types if necessary



#loader 
@login_manager.user_loader
def load_user(user_id):
    # Try to load the user from each user type table
    user = Webmaster.query.get(int(user_id))
    if user:
        return user
    user = Admin.query.get(int(user_id))
    if user:
        return user
    user = Member.query.get(int(user_id))
    if user:
        return user
    return None

###########..............wrappers and decorators.......##############

# Wrapper for normal member login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
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

# Wrapper for both login
def admin_or_webmaster_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not (session.get('is_admin') or session.get('is_webmaster')):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

#############################################################

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))



##########........login......######################
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        # Check for webmaster login
        webmaster = Webmaster.query.filter_by(email=email).first()
        if webmaster and check_password_hash(webmaster.password, password):
            login_user(webmaster, remember=form.remember_me.data)
            session['is_webmaster'] = True
            session['is_admin'] = False
            flash('Login successful as Webmaster!', 'success')
            return redirect(url_for('webmaster_dashboard'))

        # Check for admin login
        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password, password):
            login_user(admin, remember=form.remember_me.data)
            session['is_admin'] = True
            session['is_webmaster'] = False
            flash('Login successful as Admin!', 'success')
            return redirect(url_for('admin_dashboard'))

        # Check for member login
        member = Member.query.filter_by(email=email).first()
        if member and check_password_hash(member.password, password):
            login_user(member, remember=form.remember_me.data)
            session['is_admin'] = False
            session['is_webmaster'] = False
            flash('Login successful as Member!', 'success')
            return redirect(url_for('member_dashboard'))

        # If login fails
        flash('Login failed. Check your credentials and try again.', 'danger')

    return render_template('login.html', form=form)

#connecting to an external database.
# Store database credentials in environment variables
# app.config['SECRET_KEY'] = 'english92'
# app.config['SQLALCHEMY_DATABASE_URI'] = generate_db_uri()
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
#     "pool_pre_ping": True,
#     "pool_recycle": 250
# }

##############################################

#...........search forms...............######
class SearchForm(FlaskForm):
    search_term = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Search')

class SearchWebForm(FlaskForm):
    search_term = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Search')

class SearchAdminForm(FlaskForm):
    search_query = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Search')

class DeleteMemberForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Delete Member')


##########class forms...........###################
class MemberForm(FlaskForm):

    member_name = StringField('Member Name', validators=[Optional(), Length(min=2, max=100)])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(max=15), Regexp(regex='^\d+$', message="Phone number must contain only digits")])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=100)])
    area = StringField('Member Area', validators=[Optional(), Length(min=2, max=100)])
    parish = StringField('Member Parish', validators=[Optional(), Length(min=2, max=100)])
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


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=64)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

    @classmethod
    def from_json(cls, data):
        # Implement logic to create a LoginForm object from JSON data
        # For example:
        email = data.get('email')
        password = data.get('password')
        return cls(email=email, password=password)
 
# Base form with CSRF protection enabled
class MyBaseForm(FlaskForm):
    class Meta:
        csrf = False

# Form for deleting a member
class DeleteMemberForm(MyBaseForm):
    submit = SubmitField('Delete')
    

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

####.........logged out session............############
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


###################.................###########################

@app.route('/search', methods=['GET', 'POST'])
# @admin_required
@login_required
def search():
    member_form = MemberForm()
    admin_form = AdminForm()
    search_form = SearchForm() #search for member
    search_admin_form = SearchAdminForm() #search for admins
    # Assuming you have a MemberForm class for member search
    member_results = []
    admin_results = []

    # Handle member search form submission
    if search_form.validate_on_submit():
        search_term = search_form.search_term.data
        member_results = Member.query.filter(
            (Member.phone_number.ilike(f'%{search_term}%')) | 
            (Member.email.ilike(f'%{search_term}%'))).all()
        if not member_results:
            flash('User not found', 'danger')

    #returning admin that register a member
    # for member in member_results:
    #         member.added_by_admin = Admin.query.get(member.registered_by_admin_id)

    # Handle cassava search form submission
    if search_admin_form.validate_on_submit():
        search_query = search_admin_form.search_query.data
        admin_results = Admin.query.filter(
            (Admin.phone_number.ilike(f'%{search_query}%')) | 
            (Admin.email.ilike(f'%{search_query}%'))).all()
        if not admin_results:
            flash('No results found for the search query', 'danger')

    return render_template('admin_dashboard.html',member_form=member_form, admin_form=admin_form,
                                            member_results=member_results, search_form=search_form,
                                            admin_results=admin_results)

##############################################

# #homepage route...........
@app.route("/", methods=['GET', 'POST'])
def home():
        
        return redirect(url_for('login'))
        # return render_template("login.html")
#webmaster registration ................

@app.route('/add_webmaster', methods=['GET', 'POST'])
def add_webmaster():
    form = WebmasterForm()
    if form.validate_on_submit():
        # Check if the email already exists
        existing_webmaster = Webmaster.query.filter_by(email=form.email.data).first()
        if existing_webmaster:
            flash('A webmaster with this email already exists.', 'danger')
            return redirect(url_for('add_webmaster'))

        # Hash the password and create a new webmaster
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')

        new_webmaster = Webmaster(
            webmaster_name=form.webmaster_name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            password=hashed_password
        )
        db.session.add(new_webmaster)
        db.session.commit()
        flash('Webmaster registered successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('add_webmaster.html', form=form)

############################################################
@app.route('/mark_present', methods=['POST'])
@login_required
def mark_present():
    data = request.get_json()
    member_id = data.get('member_id')
    
    if not member_id:
        return jsonify({'status': 'error', 'message': 'Member ID is required'}), 400

    member = Member.query.get(member_id)
    
    if not member:
        return jsonify({'status': 'error', 'message': 'Member not found'}), 404
    
    if member.is_present:
        return jsonify({'status': 'error', 'message': 'Member has already been marked as present'}), 400

    # Mark the member as present
    member.is_present = True
    member.last_edited_by = current_user.id
    member.last_edited_at = datetime.utcnow()

    # Create Attendance record
    attendance = Attendance(
        member_id=member.id,
        marked_by_id=current_user.id
    )
    db.session.add(attendance)
    db.session.commit()

    return jsonify({'status': 'success', 'message': 'Member marked as present'}), 200




###.........print attendance.................#######
@app.route('/attendance_records', methods=['GET', 'POST'])
@login_required
def attendance_records():
    attendances = Attendance.query.all()
    results = []
    for attendance in attendances:
        results.append({
            'id': attendance.id,
            'member_id': attendance.member_id,
            'timestamp': attendance.timestamp,
            'marked_by_id': attendance.marked_by_id,
            'marked_by_name': attendance.marked_by.admin_name  # Ensure 'name' or similar attribute exists
        })
    return jsonify(results)


#members route 
@app.route('/members')
@login_required
# @admin_required
# @webmaster_required
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

#####################################################################

@app.route('/webmaster_dashboard', methods=['GET', 'POST'])
@login_required
# @webmaster_required
def webmaster_dashboard():
    member_form = MemberForm()
    search_form = SearchForm()
    admin_form = AdminForm()
    member_results = []
    admin_results = []
    admin_form = AdminForm()
    search_admin_form = SearchAdminForm() #search for admins # Assuming you have a MemberForm class for member search
    # Handle member search form submission
    if search_form.validate_on_submit():
        search_term = search_form.search_term.data
        print(f"Search Term: {search_term}")  # Debugging line
        member_results = Member.query.filter(
            (Member.phone_number.ilike(f'%{search_term}%')) | 
            (Member.email.ilike(f'%{search_term}%'))).all()
        if not member_results:
            flash('Member not found', 'danger')

    #returning admin that register a member
    # for member in member_results:
    #         member.added_by_admin = Admin.query.get(member.registered_by_admin_id)
    # Handle cassava search form submission
    if search_admin_form.validate_on_submit():
        search_query = search_admin_form.search_query.data
        print(f"Search Term: {search_query}")  # Debugging line
        admin_results = Admin.query.filter(
            (Admin.phone_number.ilike(f'%{search_query}%')) | 
            (Admin.email.ilike(f'%{search_query}%'))).all()
        if not admin_results:
            flash('No results found for the search query', 'danger')

    return render_template(
        'webmaster_dashboard.html',
        member_form=member_form, search_form=search_form,
        admin_form=admin_form, search_admin_form=search_admin_form,
        member_results=member_results, admin_results=admin_results
    )


@app.route('/admin_dashboard', methods=['GET', 'POST'])
@login_required
# @admin_required
def admin_dashboard():
    member_form = MemberForm()
    search_admin_form = SearchAdminForm() 
    member_results = []
    admin_results = []
    search_form = SearchForm() #search for member
    admin_form = AdminForm()

    # Handle member search form submission
    if search_form.validate_on_submit():
        search_term = search_form.search_term.data
        print(f"Search Term: {search_term}")  # Debugging line
        member_results = Member.query.filter(
            (Member.phone_number.ilike(f'%{search_term}%')) | 
            (Member.email.ilike(f'%{search_term}%'))).all()
        if not member_results:
            flash('Member not found', 'danger')
    #returning admin that register a member
    # for member in member_results:
    #         member.added_by_admin = Admin.query.get(member.registered_by_admin_id)

    return render_template(
        'admin_dashboard.html',
        member_form=member_form, search_form=search_form, member_results=member_results,
        admin_results=admin_results, search_admin_form= search_admin_form, admin_form =admin_form)
     
    
############........webmaster and admin role.........##################
@app.route('/add_member', methods=['GET', 'POST'])
@login_required
# @admin_or_webmaster_required
def add_member():
    form = MemberForm()
    if form.validate_on_submit():
    # Check if the email already exists
        existing_member = Member.query.filter_by(email=form.email.data).first()
        if existing_member:
            flash('An member already exists.', 'danger')
            return redirect(url_for('admin_dashboard'))
        existing_member = Member.query.filter_by(phone_number=form.phone_number.data).first()
        if existing_member:
            flash('An member already exists.', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        new_member = Member(
            member_name=form.member_name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            area=form.area.data,
            parish=form.parish.data,
            gender=form.gender.data,
            registered_by_admin_id=current_user.id if current_user.is_admin else None)
        


        db.session.add(new_member)
        db.session.commit()
        flash('Member added successfully!', 'success')
        return redirect(url_for('add_member'))
    return render_template('add_member.html', form=form)


@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
# @admin_or_webmaster_required
def edit_member(member_id):
    member = Member.query.get_or_404(member_id)
    form = MemberForm(obj=member)
    
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
         # Log the action
        # log_action('edit_member', current_user.id, member_id)
    
        
        flash('Member updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))  # Adjust if necessary

    return render_template('edit_member.html', form=form, member=member)


@app.route('/delete_member/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    member = Member.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    
    # Log the action
    log_action('delete_member', current_user.id, member_id)
    
    flash('Member deleted successfully!', 'success')
    return jsonify({'status': 'success'})


######..............webmster role .............###################################


# Admin registration route
@app.route('/add_admin', methods=['GET', 'POST'])
@login_required
# @webmaster_required
def add_admin():
    form = AdminForm()
    admin_form=AdminForm()
    if form.validate_on_submit():
        # Check if the email already exists
        existing_admin = Admin.query.filter_by(email=form.email.data).first()
        if existing_admin:
            flash('An admin with this email already exists.', 'danger')
            return redirect(url_for('webmaster_dashboard'))

        # Hash the password and create a new admin
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        new_admin = Admin(
            admin_name=form.admin_name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            password=hashed_password,
            last_edited_by_webmaster_id=current_user.id
        )
        db.session.add(new_admin)
        db.session.commit()
        flash('Admin registered successfully!', 'success')
        return redirect(url_for('webmaster_dashboard'))
    return render_template('add_admin.html', admin_form=admin_form, form =form)


@app.route('/edit_admin/<int:admin_id>', methods=['GET', 'POST'])
@login_required
def edit_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    form = AdminForm(obj=admin)

    if form.validate_on_submit():
        admin.email = form.email.data
        if form.password.data:
            admin.password = generate_password_hash(form.password.data)
        admin.admin_name = form.admin_name.data
        admin.phone_number = form.phone_number.data

        db.session.commit()

        # Log the action
        log_action('edit_admin', current_user.id)

        flash('Admin updated successfully!', 'success')
        return redirect(url_for('webmaster_dashboard'))  # Adjust if necessary

    return render_template('edit_admin.html', form=form, admin=admin)


@app.route('/delete_admin/<int:admin_id>', methods=['POST'])
@login_required
# @webmaster_required
def delete_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    
    # Log the deletion
    log_action('delete_admin', current_user.id, record_type='admin', record_id=admin.id)
    
    db.session.delete(admin)
    db.session.commit()
    
    flash('Admin deleted successfully!', 'success')
    return jsonify({'status': 'success'})

#upload file
@app.route('/upload', methods=['POST'])

@login_required
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
                    last_edited_by=current_user.id,
                    last_edited_at=datetime.utcnow()
                )
                db.session.add(member)
            
            db.session.commit()
            
            os.remove(filepath)
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'duplicates': duplicates,
                'new_members_count': len(new_members)
            })
        
        except Exception as e:
            return jsonify({'message': f'Error processing file: {e}'}), 500
    
    return jsonify({'message': 'Invalid file type'}), 400

#################################################################
@app.route('/member_dashboard')
@login_required
def member_dashboard():
    return render_template('member_dashboard.html') 




############################################################################################
       
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

