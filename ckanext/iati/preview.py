import logging
import os 
from lxml import etree
from urllib2 import urlopen
from ckan.plugins import implements, SingletonPlugin, IPackageController

PREVIEW_XSL = os.path.join(os.path.dirname(__file__), '..', '..', 'xsl', 'activities_file_preview.xsl')

log = logging.getLogger(__name__)

def get_preview_transformer():
    fh = open(PREVIEW_XSL, 'r') 
    tf = etree.XSLT(etree.parse(fh))
    fh.close()
    return tf

class IatiPackagePreviewExtension(SingletonPlugin):
    """ 
    Download the IATI XML file from the web and generate an HTML preview
    snippet using an XSL transformation. 
    """
    implements(IPackageController, inherit=True)
    
    @property
    def transformer(self):
        if not hasattr(self, '_tf'):
            self._tf = get_preview_transformer()
        return self._tf
    
    def load_xml(self, url):
        if not url or not (url.startswith('http:') or url.startswith('https:') or url.startswith('ftp:')):
            return None
        try:
            urlfh = urlopen(url)
            return etree.parse(urlfh) 
        finally:
            urlfh.close()

    def preview(self, url):
        try:
            doc = self.load_xml(url) 
            if doc:
                return etree.tostring(self.transformer(doc))
        except Exception, e:
            # TODO: Generate an HTML snippet with validation errors etc.
            log.exception(e)
            return None
    
    def create(self, package):
        return self.edit(package)
        
    def edit(self, package):
        for resource in package.resources:
            preview = self.preview(resource.url)
            if preview is not None:
                key = 'iati:preview:%s' % resource.id
                package.extras[key] = preview

#cli test.
if __name__ == '__main__':
    doc = etree.parse(open('data/xml/undp-congo.xml', 'r')) 
    transform = get_preview_transformer()
    print etree.tostring(transform(doc)).encode('utf-8')
