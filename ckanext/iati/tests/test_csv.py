import os

from ckan import model
from ckan.model import Session

from ckan.logic.action.get import package_list, package_show, package_show_rest
from ckan.tests import CreateTestData
from ckanext.iati.controllers.spreadsheet import CSVController


class TestCSVImporter():

    base_csv_path = ''

    controller = CSVController()

    context = {
        'model':model,
        'session':Session,
        'user':u'tester',
        'api_version':1
    }

    @classmethod
    def setup_class(cls):

        cls.base_csv_path = os.path.join(os.path.dirname(os.path.abspath( __file__ )), 'csv')
    
    def setup(self):
        # Create a test user and publisher
        # TODO: use logic functions (there are conflicts with the IATI plugins)
        CreateTestData.create_test_user()
        group = model.Group(name='test-publisher',title='Test Publisher')
        model.repo.new_revision()
        model.Session.add(group)
        model.setup_default_user_roles(group, [model.User.get(u'tester')])
        model.Session.commit()

    def teardown(self):
        model.Session.remove()
        model.repo.rebuild_db()

    @classmethod
    def assert_csv_import(cls,file_name,expected_added=0,expected_updated=0,expected_warnings=0,expected_errors=0):

        f = open(os.path.join(cls.base_csv_path,file_name),'r')

        added, updated, warnings, errors = cls.controller.read_csv_file(f,context=cls.context)

        assert len(added) == expected_added, '{0} != {1}'.format(len(added), expected_added)
        assert len(updated) == expected_updated, '{0} != {1}'.format(len(updated), expected_updated)
        assert len(warnings) == expected_warnings, '{0} != {1}'.format(len(warnings), expected_warnings)
        assert len(errors) == expected_errors, '{0} != {1}'.format(len(errors), expected_errors)

        return added, updated, warnings, errors

    def test_basic(self):

        # Create new records
        added, updated, warnings, errors = self.assert_csv_import('from_the_registry.csv',3,0,0,0)
        
        # Check that packages were actually created
        pkgs = package_list(self.context,{})
        assert len(pkgs) == 3

        # Update existing records and create a new one
        added, updated, warnings, errors = self.assert_csv_import('from_the_registry_update.csv',1,3,0,0)

        # Check that packages were updated and the new one created
        pkgs = package_list(self.context,{})
        assert len(pkgs) == 4
        
        pkg = package_show(self.context,{'id':'test-publisher-vu'})
        assert 'UPDATED' in pkg['title']
        pkg = package_show(self.context,{'id':'test-publisher-iq'})
        assert 'NEW' in pkg['title']

    def test_warnings(self): 
        # Missing columns
        added, updated, warnings, errors = self.assert_csv_import('from_the_registry_extra_column.csv',3,0,1,0)

        assert 'ignoring extra columns: generated-datetime' in warnings[0][1]['file'].lower()

    def test_errors(self):

        # Not a CSV file (binary)
        added, updated, warnings, errors = self.assert_csv_import('error_not_a_csv_1.csv',0,0,0,1)

        assert 'error reading csv file: line contains null byte' in errors[0][1]['file'].lower()

        # Not a CSV file (text)
        added, updated, warnings, errors = self.assert_csv_import('error_not_a_csv_2.csv',0,0,0,1)

        assert 'missing columns' in errors[0][1]['file'].lower()

        # Missing columns
        added, updated, warnings, errors = self.assert_csv_import('error_missing_columns.csv',0,0,0,1)

        assert 'missing columns: activity-count, registry-file-id, registry-publisher-id' in errors[0][1]['file'].lower()

        # Miscellaneous errors:
        #   * Unknown publisher
        #   * Wrong dataset name
        #   * Wrong activity count
        #   * Wrong country code
        #   * Wrong file type
        #   * Wrong validation status
        #   * Missing publisher name
        #   * Missing dataset name  
        added, updated, warnings, errors = self.assert_csv_import('error_misc.csv',0,0,0,8)

        assert errors == [
            ('1', {'registry-publisher-id': ['Publisher not found: test-publisher-unknown']}),
            ('2', {'registry-file-id': [u'Dataset name does not follow the convention <publisher>-<code>: "test-wrong-name" (using publisher test-publisher)']}),
            ('3', {'activity-count': [u'Invalid integer']}),
            ('4', {'recipient-country': ['Unknown country code "NOT_A_COUNTRY"']}),
            ('5', {'file-type': ['File type must be one of [activity, organisation]']}),
            ('6', {'verification-status': ['Value must be one of [yes, no]']}),
            ('7', {'registry-publisher-id': [u'Missing value'], 'registry-file-id': ['Publisher name missing']}),
            ('8', {'registry-file-id': [u'Missing value']})

            ]

    def test_format(self):

        #
        # Should work
        # -----------

        # Comma delimiter + Quoted fields
        added, updated, warnings, errors = self.assert_csv_import('from_the_registry.csv',3,0,0,0)

        # Semicolon delimiter + Quoted fields
        added, updated, warnings, errors = self.assert_csv_import('format_semicolon_quoted.csv',0,3,0,0)

        # Tab delimiter + Quoted fields
        added, updated, warnings, errors = self.assert_csv_import('format_tab_quoted.csv',0,3,0,0)

        # Comma delimiter + Unquoted fields
        added, updated, warnings, errors = self.assert_csv_import('format_comma_unquoted.csv',0,3,0,0)

        # Semicolon delimiter + Unquoted fields
        added, updated, warnings, errors = self.assert_csv_import('format_semicolon_unquoted.csv',0,3,0,0)

    def test_dates(self):
        
        # ISO style (YYYY-MM-DD HH:MM, YYYY-MM-DD, YYYY-MM, YYYY)
        added, updated, warnings, errors = self.assert_csv_import('dates_iso.csv',1,0,0,0)

        pkg = package_show_rest(self.context,{'id':'test-publisher-vu'})

        assert pkg['extras']['activity_period-from'] == '1904-06-16 10:01'
        assert pkg['extras']['activity_period-to'] == '1904-06-16'
        assert pkg['extras']['data_updated'] == '1904-06'

        # "Excel" style (DD/MM/YYYY HH:MM, DD/MM/YYYY, MM/YYYY, YYYY)
        added, updated, warnings, errors = self.assert_csv_import('dates_excel.csv',1,0,0,0)

        pkg = package_show_rest(self.context,{'id':'test-publisher-vu'})

        assert pkg['extras']['activity_period-from'] == '1904-06-16 10:01'
        assert pkg['extras']['activity_period-to'] == '1904-06-16'
        assert pkg['extras']['data_updated'] == '1904-06'

        # Wrong dates
        added, updated, warnings, errors = self.assert_csv_import('dates_errors.csv',0,0,0,1)

        for field, msg in errors[0][1].iteritems():
            assert 'cannot parse db date' in msg[0].lower()

