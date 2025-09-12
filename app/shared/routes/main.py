import logging

from flask import Blueprint, render_template

logger = logging.getLogger(__name__)

main = Blueprint("main", __name__)


@main.route("/", methods=["GET"])
def index():
    return render_template("shared/pages/home.html")
