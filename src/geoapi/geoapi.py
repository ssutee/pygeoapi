#! /usr/bin/env python
#
# pyGeoApi - Python bindings for GeoAPI, by @marram
#
# Based on Samuel Cormier-Iijima's implementation of pyfacebook
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the author nor the names of its contributors may
#       be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys
import time
import struct
import urllib
import urllib2
import httplib
try:
    import hashlib
except ImportError:
    import md5 as hashlib
import binascii
import urlparse
import mimetypes
import logging

# Try to import json/simplejson
try:
    import json as simplejson
except ImportError:
    try:
        import simplejson
    except ImportError:
        try:
            from django.utils import simplejson
        except ImportError:
            try:
                import jsonlib as simplejson
                simplejson.loads
            except (ImportError, AttributeError):
                raise

# New versions of Google App Engine do support the urllib2 syntax
def urlread(url, data=None):
    # Force a GET, because urllib2.urlopen uses POST when the data parameter is used.
    # For some reason, the GeoAPI api does not support POST.
    #res = urllib2.urlopen(url, data=data)
    res = urllib2.urlopen("%s?%s" % (url, str(data)))
    return res.read()

__all__ = ['GeoAPI']

VERSION = '0.1'

GEOAPI_URL = "http://api.geoapi.com/v1/"

class json(object): pass

# simple IDL for the GeoAPI service
METHODS = {
    'search': {
        'simple': {
            "params":[
            ('lat', float, []),
            ('lon', float, []),
            ('radius', int,['optional']),
            ('type', str,['optional']),
            ('include_parents', int,['optional']),
            ('limit', int, ['optional']),
            ('pretty', int,['optional']),
            # No support for jsoncallback, because that would mess with
            # demarshalling the response.
            #('jsoncallback', int,['optional']),
            ],
            "url": "%ssearch" % GEOAPI_URL},
        'keyword_global': {
            "params":[
            ('q', str, []),
            ('limit', int, ['optional']),
            ('include_parents', int,['optional']),
            ('type', str,['optional']),
            ('pretty', int,['optional']),
            # No support for jsoncallback, because that would mess with
            # demarshalling the response.
            #('jsoncallback', int,['optional']),
            ],
            "url": "%skeyword-search" % GEOAPI_URL},
        'keyword_entity': {
            "params": [
            ('guid', str, []),
            ('q', str, []),
            ('limit', int, ['optional']),
            ('include_parents', int,['optional']),
            ('type', str,['optional']),
            ('pretty', int,['optional']),
            # No support for jsoncallback, because that would mess with
            # demarshalling the response.
            #('jsoncallback', int,['optional']),
            ],
            "url": 'lambda params: "%se/%s/keyword-search" % (GEOAPI_URL, params.get("guid"))'}        
    }
}

class Proxy(object):
    """Represents a "namespace" of GeoAPI calls, like search or view"""

    def __init__(self, client, name):
        self._client = client
        self._name = name
        
    def __call__(self, method=None, args=None, url=None):
        # for Django templates
        if method is None:
            return self
        if not url:
            url = GEOAPI_URL
        self._url = url
        return self._client('%s.%s' % (self._name, method), url, args)


# generate the API proxies
def __generate_proxies():
    for namespace in METHODS:
        methods = {}

        for method in METHODS[namespace]:
            params = ['self']
            body = ['args = {}']

            for param_name, param_type, param_options in METHODS[namespace][method].get("params"):
                param = param_name

                for option in param_options:
                    if isinstance(option, tuple) and option[0] == 'default':
                        if param_type == list:
                            param = '%s=None' % param_name
                            body.append('if %s is None: %s = %s' % (param_name, param_name, repr(option[1])))
                        else:
                            param = '%s=%s' % (param_name, repr(option[1]))

                if param_type == json:
                    # we only jsonify the argument if it's a list or a dict, for compatibility
                    body.append('if isinstance(%s, list) or isinstance(%s, dict): %s = simplejson.dumps(%s)' % ((param_name,) * 4))

                if 'optional' in param_options:
                    param = '%s=None' % param_name
                    body.append('if %s is not None: args[\'%s\'] = %s' % (param_name, param_name, param_name))
                else:
                    body.append('args[\'%s\'] = %s' % (param_name, param_name))

                params.append(param)

            # simple docstring to refer them to GeoAPI docs
            #body.insert(0, '"""GeoAPI call. See http://docs.geoapi.com/"""' % (namespace, method))

            body.insert(0, 'def %s(%s):' % (method, ', '.join(params)))
            url = METHODS[namespace][method].get('url', None)
            # A trick to have a lambda url generator
            if str(url).startswith("http"):
                body.append('url = "%s"' % url)
            else:
                body.append('url = %s' % url)
                body.append('url = url(args)')
            body.append('return self(\'%s\', args, url)' % method)

            exec('\n    '.join(body))
            methods[method] = eval(method)

        proxy = type('%sProxy' % namespace.title(), (Proxy, ), methods)

        globals()[proxy.__name__] = proxy


__generate_proxies()


class GeoAPI(object):
    """
    """

    def __init__(self, api_key):
        """

        """
        self.api_key = api_key

        for namespace in METHODS:
            self.__dict__[namespace] = eval('%sProxy(self, \'%s\')' % (namespace.title(), 'geoapi.%s' % namespace))

    def _check_error(self, response):
        """ @todo: Check for response errors """
        pass

    def _build_post_args(self, args=None):
        """Adds to args parameters that are necessary for every call to the API."""
        if args is None:
            args = {}

        for arg in args.items():
            if type(arg[1]) == list:
                args[arg[0]] = ','.join(str(a) for a in arg[1])
            elif type(arg[1]) == unicode:
                args[arg[0]] = arg[1].encode("UTF-8")
            elif type(arg[1]) == bool:
                args[arg[0]] = str(arg[1]).lower()
        
        args['apikey'] = self.api_key

        return args


    def _parse_response(self, response, method):
        """Parses the response. GeoAPI speaks JSON."""
        result = simplejson.loads(response)
        self._check_error(result)
        return result

    def unicode_urlencode(self, params):
        """
        @author: houyr
        A unicode aware version of urllib.urlencode.
        """
        if isinstance(params, dict):
            params = params.items()
        return urllib.urlencode([(k, isinstance(v, unicode) and v.encode('utf-8') or v)
                          for k, v in params])


    def __call__(self, method=None, url=None, args=None):
        """Make a call to GeoAPI's REST server."""
        # for Django templates, if this object is called without any arguments
        # return the object itself
        if method is None:
            return self
        
        post_data = self.unicode_urlencode(self._build_post_args(args))
        response = urlread(url, post_data)

        return self._parse_response(response, method)


if __name__ == '__main__':
    api = GeoAPI("demo")
    print api.search.keyword_global(q="Boston, MA")
    print api.search.keyword_entity(q="MIT", guid="cambridge-ma")