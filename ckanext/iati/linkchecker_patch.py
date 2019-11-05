import httplib
import requests
import json
import urllib
import json
from ckanext.archiver import tasks
import logging

log = logging.getLogger(__name__)
USER_AGENT = 'ckanext-archiver'


# This is the patch for URL Error bad handshake SSL.
# Added verify=False while getting a head request
def link_checker(context, data):
    """
    Check that the resource's url is valid, and accepts a HEAD request.
    Redirects are not followed - they simple return 'location' in the headers.
    data is a JSON dict describing the link:
        { 'url': url,
          'url_timeout': url_timeout }
    Raises LinkInvalidError if the URL is invalid
    Raises LinkHeadRequestError if HEAD request fails
    Raises LinkHeadMethodNotSupported if server says HEAD is not supported
    Returns a json dict of the headers of the request
    """
    data = json.loads(data)
    url_timeout = data.get('url_timeout', 30)

    error_message = ''
    headers = {'User-Agent': USER_AGENT}

    url = tasks.tidy_url(data['url'])

    # Send a head request
    try:
        res = requests.head(url, timeout=url_timeout, verify=False)
        headers = res.headers
    except httplib.InvalidURL, ve:
        log.error("Could not make a head request to %r, error is: %s."
                  " Package is: %r. This sometimes happens when using an old version of requests on a URL"
                  " which issues a 301 redirect. Version=%s", url, ve, data.get('package'), requests.__version__)
        raise LinkHeadRequestError(_("Invalid URL or Redirect Link"))
    except ValueError, ve:
        log.error("Could not make a head request to %r, error is: %s. Package is: %r.", url, ve, data.get('package'))
        raise tasks.LinkHeadRequestError(_("Could not make HEAD request"))
    except requests.exceptions.ConnectionError, e:
        raise tasks.LinkHeadRequestError(_('Connection error: %s') % e)
    except requests.exceptions.HTTPError, e:
        raise tasks.LinkHeadRequestError(_('Invalid HTTP response: %s') % e)
    except requests.exceptions.Timeout, e:
        raise tasks.LinkHeadRequestError(_('Connection timed out after %ss') % url_timeout)
    except requests.exceptions.TooManyRedirects, e:
        raise tasks.LinkHeadRequestError(_('Too many redirects'))
    except requests.exceptions.RequestException, e:
        raise tasks.LinkHeadRequestError(_('Error during request: %s') % e)
    except Exception, e:
        raise tasks.LinkHeadRequestError(_('Error with the request: %s') % e)
    else:
        if res.status_code == 405:
            # this suggests a GET request may be ok, so proceed to that
            # in the download
            raise tasks.LinkHeadMethodNotSupported()
        if not res.ok or res.status_code >= 400:
            error_message = _('Server returned HTTP error status: %s %s') % \
                (res.status_code, res.reason)
            raise tasks.LinkHeadRequestError(error_message)
    return json.dumps(dict(headers))
