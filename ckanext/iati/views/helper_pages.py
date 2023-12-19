from flask import Blueprint
from ckan.lib.base import render

helper_pages = Blueprint('help', __name__, url_prefix='/help')


def csv_import():
    return render('static/help_csv-import.html')


def delete_datasets():
    return render('static/help_delete.html')


helper_pages.add_url_rule('/csv-import', view_func=csv_import)
helper_pages.add_url_rule('/delete-datasets', view_func=delete_datasets)


