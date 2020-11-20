from flask import Blueprint
from ckan.lib.base import render

help = Blueprint(u'help', __name__, url_prefix=u'/help')


def csv_import():
    return render('static/help_csv-import.html')


def delete_datasets():
    return render('static/help_delete.html')


help.add_url_rule(u'/csv-import', view_func=csv_import)
help.add_url_rule(u'/delete-datasets', view_func=delete_datasets)


