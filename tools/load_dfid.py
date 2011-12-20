#!/bin/python 
import csv
import ckanclient

from xml import IatiXmlParser

def parse_list(file_name):
    fh = open(file_name, 'rU')
    reader = csv.DictReader(fh)
    for row in reader:
        yield row
    fh.close()

def load_packages(file_name):
    #cc = ckanclient.CkanClient(base_location="http://iatiregistry.org/api", api_key="29098b9d-a8e5-4894-b897-ab4094ce8331")
    cc = ckanclient.CkanClient(base_location="http://iati.ckan.net/api", api_key="16e0b5c3-60a6-4f5a-9519-49aa057ef9e9")
    packages = []
    for row in list(parse_list(file_name))[:5]:
        uri = row.get('URI')
        print "URI", uri
        country = uri.split('/')[-1]
        parser = IatiXmlParser.open(uri)
        name = "dfid-%s" % country
        name = name.lower()
        pkg = {"name": name, 
               "title": "DFID Activity File %s" % row.get('BenefittingCountryName'), 
               "author_email": "ppisupport@dfid.gov.uk", 
               "resources": [{
                    "format": "IATI-XML", 
                    "url": uri
                    }], 
                "download_url": uri, 
                "extras": {
                    "activity_count": row.get('ComponentActivityCount'), 
                    "country": country, 
                    "donors": ["dfid"], 
                    "donors_country": ["UK"], 
                    "donors_type": ["bilateral"], 
                    "activity_period-from": parser.start_date.strftime("%Y-%m-%d"),
                    "activity_period-to": parser.end_date.strftime("%Y-%m-%d"),
                    "verified": "yes"}
                }
        packages.append(name)
        try:
            pkg_old = cc.package_entity_get(name)
            cc.package_entity_put(pkg)
        except:
            cc.package_register_post(pkg)
        print "CC", pkg
        print cc.last_status, cc.last_message
    dfid = cc.group_entity_get("dfid")
    dfid['packages'] = list(set(dfid.get('packages', []) + packages))
    cc.group_entity_put(dfid)

load_packages("IATILinks.csv")
