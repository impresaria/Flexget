from __future__ import unicode_literals, division, absolute_import
import urllib2
import time
import logging
from datetime import timedelta, datetime
from urlparse import urlparse
import requests
# Allow some request objects to be imported from here instead of requests
from requests import RequestException
from flexget.utils.tools import parse_timedelta

log = logging.getLogger('requests')

# Don't emit info level urllib3 log messages or below
logging.getLogger('requests.packages.urllib3').setLevel(logging.WARNING)

# Remembers sites that have timed out
unresponsive_hosts = {}
# Time to wait before trying an unresponsive site again
WAIT_TIME = timedelta(seconds=60)


def is_unresponsive(url):
    """
    Checks if host of given url has timed out within WAIT_TIME

    :param url: The url to check
    :return: True if the host has timed out within WAIT_TIME
    :rtype: bool
    """
    host = urlparse(url).hostname
    if host in unresponsive_hosts and unresponsive_hosts[host] + WAIT_TIME < datetime.now():
        return True
    return False


def set_unresponsive(url):
    """
    Marks the host of a given url as unresponsive

    :param url: The url that timed out
    """
    host = urlparse(url).hostname
    unresponsive_hosts[host] = datetime.now()


class FileAdapter(requests.adapters.BaseAdapter):
    """Handles file:// URIs by passing them to urllib2"""
    def send(self, request, **kwargs):
        url = request.url
        try:
            raw = urllib2.urlopen(url)
        except IOError as e:
            msg = 'IOError openening file %s: %s' % (url, e)
            log.error(msg)
            raise RequestException(msg)
        resp = requests.Response()
        resp.raw = raw
        resp.status_code = 200
        resp.headers = requests.structures.CaseInsensitiveDict(raw.headers)
        return resp

    def close(self):
        pass


class Session(requests.Session):
    """Subclass of requests Session class which defines some of our own defaults, records unresponsive sites,
    and raises errors by default."""

    def __init__(self, timeout=30, max_retries=None):
        """Set some defaults for our session if not explicitly defined."""
        requests.Session.__init__(self)
        self.timeout = timeout
        self.stream = True
        self.mount('file://', FileAdapter())
        self.adapters['http://'].max_retries = max_retries or 1
        # Stores min intervals between requests for certain sites
        self.domain_delay = {}

    def add_cookiejar(self, cookiejar):
        """
        Merges cookies from `cookiejar` into cookiejar for this session.

        :param cookiejar: CookieJar instance to add to the session.
        """
        for cookie in cookiejar:
            self.cookies.set_cookie(cookie)

    def set_domain_delay(self, domain, delay):
        """
        Registers a minimum interval between requests to `domain`

        :param domain: The domain to set the interval on
        :param delay: The amount of time between requests, can be a timedelta or string like '3 seconds'
        """
        self.domain_delay[domain] = {'delay': parse_timedelta(delay)}

    def request(self, method, url, *args, **kwargs):
        """
        Does a request, but raises Timeout immediately if site is known to timeout, and records sites that timeout.
        Also raises errors getting the content by default.
        """

        # Raise Timeout right away if site is known to timeout
        if is_unresponsive(url):
            raise requests.Timeout('Requests to this site are known to timeout.')

        # Check if we need to add a delay before request to this site
        for domain, domain_dict in self.domain_delay.iteritems():
            if domain in url:
                next_req = domain_dict.get('next_req')
                if next_req and datetime.now() < next_req:
                    wait_time = next_req - datetime.now()
                    seconds = wait_time.seconds + (wait_time.microseconds / 1000000.0)
                    log.debug('Waiting %.2f seconds until next request to %s' % (seconds, domain))
                    # Sleep until it is time for the next request
                    time.sleep(seconds)
                # Record the next allowable request time for this domain
                domain_dict['next_req'] = datetime.now() + domain_dict['delay']
                break

        kwargs.setdefault('timeout', self.timeout)
        raise_status = kwargs.pop('raise_status', True)

        try:
            result = requests.Session.request(self, method, url, *args, **kwargs)
        except requests.Timeout:
            # Mark this site in known unresponsive list
            set_unresponsive(url)
            raise

        if raise_status:
            result.raise_for_status()

        return result


# Define some module level functions that use our Session, so this module can be used like main requests module
def request(method, url, **kwargs):
    s = kwargs.pop('session', Session())
    return s.request(method=method, url=url, **kwargs)


def get(url, **kwargs):
    """Sends a GET request. Returns :class:`Response` object.

    :param url: URL for the new :class:`Request` object.
    :param kwargs: Optional arguments that ``request`` takes.
    """
    kwargs.setdefault('allow_redirects', True)
    return request('get', url, **kwargs)


def post(url, data=None, **kwargs):
    """Sends a POST request. Returns :class:`Response` object.

    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary or bytes to send in the body of the :class:`Request`.
    :param kwargs: Optional arguments that ``request`` takes.
    """
    return request('post', url, data=data, **kwargs)
