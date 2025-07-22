import logging
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from app.projects.acronyms.db_models import Acronym

from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

acronyms_main = Blueprint("acronyms_main", __name__)

@acronyms_main.route("/", methods=["GET", "POST"])
@requires_auth
def index():
    search_term = ""

    if request.method == "POST":
        search_term = request.form.get("name", "").strip()

        return redirect(url_for('acronyms_main.index', name=search_term))

    search_term = request.args.get('name', '')
    if search_term:
        acronyms = Acronym.query.filter(Acronym.abbreviation.ilike(f"%{search_term}%")).all()

    else:
        acronyms = Acronym.query.all()

    return render_template("projects/acronyms/pages/main.html", acronyms=acronyms, search_term=search_term)

@acronyms_main.route("/live-search", methods=["GET"])
@requires_auth
def live_search():
    search_term = request.args.get("q", "").strip()

    if not search_term:
        return jsonify([])

    acronyms = Acronym.query.filter(
        Acronym.abbreviation.ilike(f"%{search_term}%")
    ).all()

    return jsonify([
        {
            "abbreviation": a.abbreviation,
            "definition": a.definition,
            "description": a.description
        } for a in acronyms
    ])
