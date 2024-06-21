import os, click
from datetime import datetime, UTC
from flask import Flask, render_template, flash, redirect, url_for, abort, request
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_ckeditor import CKEditor, CKEditorField
from flask_toastr import Toastr
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# create database if app is given commandline argument
@click.command('init-db')
def create_tables():
    db.create_all()
    user = User()
    user.username = "admin"
    user.password = argon2_ph.hash("1234")
    db.session.add(user)
    db.session.commit()

base_dir = os.path.dirname(os.path.realpath(__file__))

app = Flask(__name__, template_folder='templates')
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///' + os.path.join(base_dir, 'bloggable.db')
app.config["SECRET_KEY"] = 'dev'
app.cli.add_command(create_tables)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
ckeditor = CKEditor(app)
argon2_ph = PasswordHasher()
toastr = Toastr(app)

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(16), unique=True, nullable=False)
    password = db.Column(db.String(64), nullable=False)
    # get all 'Post' objects related to our User
    posts = db.relationship('Post', backref='user', lazy=True)

    def __repr__(self):
        return f"User('{self.id}', '{self.username}', '{self.password}')"

class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    author = db.Column(db.Integer, db.ForeignKey('user.username'), nullable=False)
    title = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.now(UTC))
    date_edited = db.Column(db.DateTime, nullable=True)
    content = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"Post('{self.id}', '{self.author}', '{self.title}', '{self.date_posted}', '{self.content}')"

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Submit')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Submit')

class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    body = CKEditorField('Body', validators=[DataRequired()])
    submit = SubmitField('Submit')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    posts = Post.query.all()
    # pass posts to Jinja2 template
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            try:
                argon2_ph.verify(user.password, form.password.data)
                login_user(user)
                return redirect(url_for('dashboard'))
            except VerifyMismatchError:
                pass
        flash('Login unsuccessful!', 'error')
        return redirect(url_for('login'))
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out!', 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            flash('User already exists!', 'error')
        else:
            hashed_password = argon2_ph.hash(form.password.data)
            user = User(username=form.username.data, password=hashed_password)
            db.session.add(user)
            db.session.commit()
            flash(f"Account '{form.username.data}' successfully registered!")
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    posts = Post.query.filter_by(author=current_user.username)
    return render_template('dashboard.html', posts=posts)

# CREATE
@app.route("/create", methods=['GET', 'POST'])
@login_required
def create():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(author=current_user.username, date_posted=datetime.now(UTC), title=form.title.data, content=form.body.data)
        db.session.add(post)
        db.session.commit()
        flash('Post created!', 'success')
        return redirect(url_for('post', post_id=post.id))
    return render_template('create.html', title='New Post', form=form)

# READ
@app.route("/post/<int:post_id>", methods=['GET', 'POST'])
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

# UPDATE
@app.route("/post/<int:post_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user.username:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.body.data
        post.date_edited = datetime.now(UTC)
        db.session.commit()
        flash('Post edited!', 'success')
        return redirect(url_for('post', post_id=post_id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.body.data = post.content
    return render_template('edit.html', form=form, post=post)

# DELETE
@app.route("/post/<int:post_id>/delete", methods=['GET', 'POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user.username:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Post has been deleted!', 'success')
    return redirect(url_for('index'))