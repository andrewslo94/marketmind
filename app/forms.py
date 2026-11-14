"""
app/forms.py — web forms, defined as Python classes (Flask-WTF / WTForms).

Each class attribute is one form field with a list of validators. When a
form is submitted, form.validate_on_submit() runs every validator and
collects error messages, so the routes stay short and all input is checked
server-side before it touches the database.

Flask-WTF also adds a hidden CSRF token to every form (form.hidden_tag()
in the template) and rejects submissions that don't carry a valid one.
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Regexp,
    ValidationError,
)

from app.models import User


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=30),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="Letters, numbers, and underscores only.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=120)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Create account")

    # WTForms calls any method named validate_<fieldname> as an extra
    # validator for that field. We use it to check the database.
    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("That username is already taken.")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("An account with that email already exists.")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=30)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Keep me logged in")
    submit = SubmitField("Log in")
