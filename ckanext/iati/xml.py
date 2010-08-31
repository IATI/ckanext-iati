from lxml import etree
from datetime import datetime
from copy import deepcopy
from hashlib import sha1
import unittest
import os

def parse_iso_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d")


class IatiActivity(object):
    
    def __init__(self, node):
        self.node = deepcopy(node)
    
    @property
    def title(self):
        return self.node.findtext('title')
    
    @property
    def start_date(self):
        subn = self.node.find('activity-date[@type="start"]')
        if subn is not None:
            return parse_iso_date(subn.get('iso-date'))
        
    @property
    def end_date(self):
        subn = self.node.find('activity-date[@type="end"]')
        if subn is not None:
            return parse_iso_date(subn.get('iso-date'))


class IatiXmlParser(object):
    
    def __init__(self, tree):
        self.tree = tree
        assert self.tree.getroot().tag == 'iati-activities'
        assert float(self.tree.getroot().get('version')) >= 1.0
        
    @classmethod
    def open(cls, doc_name):
        tree = etree.parse(doc_name)
        return cls(tree)
    
    @property
    def donors(self):
        funders = self.tree.findall('//participating-org[@role="funding"]')
        return set([f.text for f in funders if f.text is not None])
    
    @property
    def activities(self):
        return [IatiActivity(n) for n in self.tree.findall('/iati-activity')]
    
    @property
    def start_date(self):
        return min([a.start_date for a in self.activities if a.start_date is not None])

    @property
    def end_date(self):
        return max([a.end_date for a in self.activities if a.end_date is not None])
    
    def __len__(self):
        return len(self.activities)
    
    @property
    def hash(self):
        return sha1().update(etree.tostring(self.tree)).hexdigest()
    
    # TODO: to_package
    # TODO: to_excel

CONGO_XML = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'xml', 'undp-congo.xml')

class IatiXmlParserTest(unittest.TestCase):
    
    def setUp(self):
        self.congo = IatiXmlParser.open(CONGO_XML)
        
    def test_read(self):
        assert self.congo.tree is not None
        
    def test_parse_iso_date(self):
        dt = datetime(2009, 1, 4)
        assert parse_iso_date("2009-01-04") == dt
    
    def test_activities(self):
        assert len(self.congo.activities)==656
    
    def test_activity_dates(self):
        first = self.congo.activities[0]
        assert 'DDR' in first.title
        assert first.start_date == datetime(2009, 10, 8), first.start_date
        assert first.end_date == datetime(2010,12,31), first.end_date
        
    def test_date_range(self):
        assert self.congo.start_date == datetime(2000,1,1), self.congo.start_date
        assert self.congo.end_date == datetime(2025,12,31), self.congo.end_date
    
    def test_donors(self):
        print self.congo.donors

if __name__ == '__main__':
    unittest.main()