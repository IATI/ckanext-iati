import logging
import os 
from lxml import etree
from urllib2 import urlopen


PREVIEW_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'xsl', 'activities_file_preview.xsl')

log = logging.getLogger(__name__)


def get_preview_transformer():
    fh = open(PREVIEW_PATH, 'r') 
    tf = etree.XSLT(etree.parse(fh))
    fh.close()
    return tf

    
def parse_iati_xml(url):
    if not url or not (url.startswith('http:') or url.startswith('https:') or url.startswith('ftp:')):
        return None
    try:
        urlfh = urlopen(url)
        return etree.parse(urlfh) 
    except Exception, e:
        logging.exception(e)
        return None
    finally:
        urlfh.close()

        
def generate_preview(url):
    transform = get_preview_transformer()
    doc = parse_iati_xml(url) 
    if not doc: 
        return None
    #print etree.tostring(doc).encode('utf-8')
    return etree.tostring(transform(doc))


# plugin impl.
from ckan import model, signals

def on_package(pkg):
    preview = ''
    for resource in pkg.resources:
        pkg_preview = generate_preview(resource.url)
        if pkg_preview is not None:
            preview += pkg_preview
    pkg.extras['iati:preview'] = preview
    
signals.PACKAGE_NEW.connect(on_package)
signals.PACKAGE_EDIT.connect(on_package)


#cli test.
if __name__ == '__main__':
    doc = etree.parse(open('data/xml/undp-congo.xml', 'r')) 
    from xml import IatiXmlParser
    parser = IatiXmlParser(doc)
    
    transform = get_preview_transformer()
    print etree.tostring(transform(doc)).encode('utf-8')
