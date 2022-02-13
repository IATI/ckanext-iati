from flask import Blueprint, render_template
import logging

log = logging.getLogger(__name__)

registration_blueprint = Blueprint(u'registration', __name__)


def register():
    return render_template('register/registration.html')


registration_blueprint.add_url_rule(u'/register', view_func=register, methods=["GET"])
