from flask import Blueprint, jsonify

healthz_route = Blueprint("healthz_route", __name__)

@healthz_route.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "OK"}), 200
