from flask_admin import Admin
from app.shared.admin.views import SecureAdminIndexView

admin = Admin(name="Github Conmmunity Admin", template_mode="bootstrap4", index_view=SecureAdminIndexView())