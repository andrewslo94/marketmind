"""
app/extensions.py — shared Flask extension objects.

The extensions are created here *without* an app, then attached to the app
inside create_app() with `.init_app(app)`. This two-step pattern avoids
circular imports: models.py needs `db`, and the app factory needs models.py,
so `db` must live in a neutral module that neither of them depends on.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# db: the database handle. Models are defined as classes that extend db.Model.
db = SQLAlchemy()

# login_manager: keeps track of which user is logged in via the session
# cookie, and protects pages with the @login_required decorator.
login_manager = LoginManager()

# Where to send a visitor who tries to open a protected page while logged
# out. "auth.login" = the `login` route inside the `auth` blueprint (Phase 2B).
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "warning"

# csrf: makes csrf_token() available in templates and checks every POST.
# Flask-WTF forms carry the token automatically via form.hidden_tag().
csrf = CSRFProtect()
