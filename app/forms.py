"""
app/forms.py — web forms, defined as Python classes (Flask-WTF / WTForms).

Each class attribute is one form field with a list of validators. When a
form is submitted, form.validate_on_submit() runs every validator and
collects error messages, so the routes stay short and all input is checked
server-side before it touches the database.

Flask-WTF also adds a hidden CSRF token to every form (form.hidden_tag()
in the template) and rejects submissions that don't carry a valid one.
"""
from datetime import date

from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from app.models import Holding, User


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


class HoldingForm(FlaskForm):
    """
    Add or edit one portfolio holding.

    Phase 3A checks the ticker's *format* only (1-5 letters, optional
    class suffix such as BRK.B). Phase 3B adds a live check that the
    ticker actually exists, once the market-data service is connected.
    """

    ticker = StringField(
        "Ticker symbol",
        # filters run before validators: trim spaces and upper-case the input
        # so "aapl " is stored as "AAPL".
        filters=[lambda value: value.strip().upper() if value else value],
        validators=[
            DataRequired(),
            Length(max=10),
            Regexp(
                r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$",
                message="Use a stock symbol such as AAPL, MSFT, or BRK.B.",
            ),
        ],
        render_kw={"placeholder": "e.g. AAPL", "autocapitalize": "characters"},
    )
    # DecimalField keeps exact decimals during validation; the route converts
    # to float for storage. InputRequired (not DataRequired) so that "0" is
    # reported by NumberRange as "must be greater than 0" rather than "missing".
    shares = DecimalField(
        "Number of shares",
        places=4,
        validators=[
            InputRequired(),
            NumberRange(min=0.0001, max=1_000_000_000, message="Shares must be greater than 0."),
        ],
        render_kw={"placeholder": "e.g. 10 or 2.5", "inputmode": "decimal"},
    )
    avg_price = DecimalField(
        "Average purchase price (USD)",
        places=4,
        validators=[
            InputRequired(),
            NumberRange(min=0.0001, max=10_000_000, message="Price must be greater than 0."),
        ],
        render_kw={"placeholder": "e.g. 150.25", "inputmode": "decimal"},
    )
    # DateField renders as <input type="date">. Optional() lets it be blank.
    purchase_date = DateField("Purchase date (optional)", validators=[Optional()])
    notes = StringField(
        "Notes (optional)",
        validators=[Optional(), Length(max=200)],
        render_kw={"placeholder": "e.g. Long-term position"},
    )
    submit = SubmitField("Save holding")

    def __init__(self, *args, holding_id=None, **kwargs):
        """holding_id is set when editing, so the duplicate-ticker check
        ignores the row currently being edited."""
        super().__init__(*args, **kwargs)
        self.holding_id = holding_id

    def validate_ticker(self, field):
        existing = Holding.query.filter_by(
            user_id=current_user.id, ticker=field.data
        ).first()
        if existing and existing.id != self.holding_id:
            raise ValidationError(
                f"{field.data} is already in your portfolio. Edit that holding instead."
            )

    def validate_purchase_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("Purchase date can't be in the future.")
