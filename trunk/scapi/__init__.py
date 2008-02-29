##    SouncCloudAPI implements a Python wrapper around the SoundCloud RESTful
##    API
##
##    Copyright (C) 2008  Diez B. Roggisch
##    Contact mailto:deets@soundcloud.com
##
##    This library is free software; you can redistribute it and/or
##    modify it under the terms of the GNU Lesser General Public
##    License as published by the Free Software Foundation; either
##    version 2.1 of the License, or (at your option) any later version.
##
##    This library is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
##    Lesser General Public License for more details.
##
##    You should have received a copy of the GNU Lesser General Public
##    License along with this library; if not, write to the Free Software
##    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
import sys
import md5
import urllib
import urllib2
import mimetools
import os.path
import logging
import copy
import webbrowser
import base64
import simplejson
import cookielib
import scapi.config
from scapi.MultipartPostHandler import MultipartPostHandler
from inspect import isclass
import urlparse
from scapi.authentication import BasicAuthenticator
from scapi.util import escape

logging.basicConfig()
logger = logging.getLogger(__name__)

USE_PROXY = False
"""
Something like http://127.0.0.1:10000/
"""
PROXY = ''


__all__ = ['SoundCloudAPI', 'RESTBase',]


class NoResultFromRequest(Exception):
    pass

class InvalidMethodException(Exception):

    def __init__(self, message):
        self._message = message
        Exception.__init__(self)

    def __repr__(self):
        res = Exception.__repr__(self)
        res += "\n" 
        res += "-" * 10
        res += "\nmessage:\n\n"
        res += self._message
        return res


class SoundCloudAPI(object):
    """
    The SoundCloudAPI Singleton. It must be initialized with constructor parameters once
    to make the connection to the SoundCloud-server possible. Afterwards, a simple non-argument
    instantiation will be sufficient.
    """

    """
    SoundClound imposes a maximum on the number of returned items. This value is that
    maximum.
    """
    LIST_LIMIT = 50

    """
    The query-parameter that is used to request results beginning from a certain offset.
    """
    LIST_OFFSET_PARAMETER = 'offset'
    """
    The query-parameter that is used to request results being limited to a certain amount.
    
    Currently this is of no use and just for completeness sake.
    """
    LIST_LIMIT_PARAMETER = 'limit'

    __shared_state = {'base64string' : None, 'collapse_scope' : True, '_base' : 'api/'}

    def __init__(self, host=None, base64string=None, user=None, password=None, authenticator=None):
        """
        Constructor for the API-Singleton. Use it once with parameters, and then the
        subsequent calls internal to the API will work.

        @type host: str
        @param host: the host to connect to, e.g. "api.soundcloud.com". If a port is needed, use
                "api.soundcloud.com:1234"
        @type user: str
        @param user: if given, the username for basic HTTP authentication
        @type password: str
        @param password: if the user is given, you have to give a password as well
        @type authenticator: OAuthAuthenticator | BasicAuthenticator
        @param authenticator: the authenticator to use, see L{scapi.authentication}
        """
        self.__dict__ = self.__shared_state
        if host is not None:
            self.host = host
        if authenticator is not None:
            self.authenticator = authenticator
        elif user is not None and password is not None:
            self.authenticator = BasicAuthenticator(user, password)

    def normalize_method(self, method):
        """ 
        This method will take a method that has been part of a redirect of some sort
        and see if it's valid, which means that it's located beneath our base. 
        If yes, we return it normalized without that very base.
        """
        protocol, host, path, params, query, fragment = urlparse.urlparse(method)
        if path.startswith("/"):
            path = path[1:]
        if path.startswith(self._base):
            return path[len(self._base)-1:]
        raise InvalidMethodException("Not a valid API method: %s" % method)


class SCRedirectHandler(urllib2.HTTPRedirectHandler):
    """
    A urllib2-Handler to deal with the redirects the RESTful API of SC uses.
    """
    alternate_method = None

    def http_error_303(self, req, fp, code, msg, hdrs):
        """
        In case of return-code 303 (See-other), we have to store the location we got
        because that will determine the actual type of resource returned.
        """
        self.alternate_method = hdrs['location']
        return urllib2.HTTPRedirectHandler.http_error_303(self, req, fp, code, msg, hdrs)

    def http_error_201(self, req, fp, code, msg, hdrs):
        """
        We fake a 201 being a 303 so that our redirection-scheme takes place
        for the 201 the API throws in case we created something. If the location is
        not available though, that means that whatever we created has succeded - without
        being a named resource. Assigning an asset to a track is an example of such
        case.
        """
        if 'location' not in hdrs:
            raise NoResultFromRequest()
        return self.http_error_303(req, fp, 303, msg, hdrs)

class Scope(object):
    """
    The basic means to query and create resources. The Scope uses the L{SoundCloudAPI} to
    create the proper URIs for querying or creating resources. It will only work after
    you created the L{SoundCloudAPI}-singleton once with the proper connection parameters.

    For accessing resources from the root level, you explcitly create a Scope and query it 
    or create new resources like this:

    >>> scapi.SoundCloudAPI(host='host', user='user', password='password') # initialize the API
    >>> scope = scapi.Scope() # get the root scope
    >>> users = scope.users()
    [<scapi.User object at 0x12345>, ...]

    When accessing resources that belong to another resource, like contancts of a user, you access
    the parent's resource scope implicitly through the resource instance like this:

    >>> user = scope.users()[0]
    >>> user.contacts()
    [<scapi.Contact object at 0x12345>, ...]

    """
    def __init__(self, scope=None, parent=None):
        """
        Create the Scope. It can have a resource as scope, and possibly a parent-scope.

        @type scope: scapi.RESTBase
        @param scope: the resource to make this scope belong to
        @type parent: scapi.Scope
        @param parent: the parent scope of this scope
        """

        if scope is None:
            scope = ()
        else:
            scope = scope,
        if parent is not None:
            scope = parent._scope + scope
        self._scope = scope

    def _create_request(self, url, api, parameters, queryparams, alternate_http_method=None):
        """
        This method returnes the urllib2.Request to perform the actual HTTP-request.

        We return a subclass that overload the get_method-method to return a custom method like "PUT".
        Additionally, the request is enhanced with the current authenticators authorization scheme
        headers.

        @param url: the destination url
        @param api: our api-instance
        @param parameters: the POST-parameters to use.
        @type parameters: None|dict<str, basestring|list<basestring>>
        @param queryparams: the queryparams to use
        @type queryparams: None|dict<str, basestring|list<basestring>>
        @param alternate_http_method: an alternate HTTP-method to use
        @type alternate_http_method: str
        @return: the fully equipped request
        @rtype: urllib2.Request
        """
        class MyRequest(urllib2.Request):
            def get_method(self):
                if alternate_http_method is not None:
                    return alternate_http_method
                return urllib2.Request.get_method(self)

        req = MyRequest(url)
        all_params = {}
        if parameters is not None:
            all_params.update(parameters)
        if queryparams is not None:
            all_params.update(queryparams)
        if not all_params:
            all_params = None
        api.authenticator.augment_request(req, all_params)
        req.add_header("Accept", "application/json")
        return req

    def _create_query_string(self, queryparams):
        """
        Small helpermethod to create the querystring from a dict.

        @type queryparams: None|dict<str, basestring|list<basestring>>
        @param alternate_http_method: an alternate HTTP-method to use
        @return: either the empty string, or a "?" followed by the parameters joined by "&"
        @rtype: str
        """
        if not queryparams:
            return ""
        h = []
        for key, values in queryparams.iteritems():
            if isinstance(values, (int, long, float)):
                values = str(values)
            if isinstance(values, basestring):
                values = [values]
            for v in values:
                v = v.encode("utf-8")
                h.append("%s=%s" % (key, escape(v)))
        return "?" + "&".join(h)

    def _call(self, method, *args, **kwargs):
        """
        The workhorse. It's complicated, convoluted and beyond understanding of a mortal being.

        You have been warned.
        """
        queryparams = {}
        __offset__ = SoundCloudAPI.LIST_LIMIT
        if "__offset__" in kwargs:
            offset = kwargs.pop("__offset__")
            queryparams['offset'] = offset
            __offset__ = offset + SoundCloudAPI.LIST_LIMIT

        # create a closure to invoke this method again with a greater offset
        _cl_method = method
        _cl_args = tuple(args)
        _cl_kwargs = {}
        _cl_kwargs.update(kwargs)
        _cl_kwargs["__offset__"] = __offset__
        def continue_list_fetching():
            return self._call(method, *_cl_args, **_cl_kwargs)
        api = SoundCloudAPI()
        def filelike(v):
            if isinstance(v, file):
                return True
            if hasattr(v, "read"):
                return True
            return False 
        alternate_http_method = None
        if "_alternate_http_method" in kwargs:
            alternate_http_method = kwargs.pop("_alternate_http_method")
        urlparams = kwargs if kwargs else None
        use_multipart = False
        if urlparams is not None:
            fileargs = dict((key, value) for key, value in urlparams.iteritems() if filelike(value))
            use_multipart = bool(fileargs)

        # ensure the method has a trailing /
        if method[-1] != "/":
            method = method + "/"
        if args:
            method = "%s%s" % (method, "/".join(str(a) for a in args))

        scope = ''
        if self._scope:
            scopes = self._scope
            if api.collapse_scope:
                scopes = scopes[-1:]
            scope = "/".join([sc._scope() for sc in scopes]) + "/"
        url = "http://%(host)s/%(base)s%(scope)s%(method)s%(queryparams)s" % dict(host=api.host, method=method, base=api._base, scope=scope, queryparams=self._create_query_string(queryparams))

        # we need to install SCRedirectHandler
        # to gather possible See-Other redirects
        # so that we can exchange our method
        redirect_handler = SCRedirectHandler()
        handlers = [redirect_handler]
        if USE_PROXY:
            handlers.append(urllib2.ProxyHandler({'http' : PROXY}))

        req = self._create_request(url, api, urlparams, queryparams, alternate_http_method)

        http_method = req.get_method()
        if urlparams is not None:
            logger.debug("Posting url: %s, method: %s", url, http_method)
        else:
            logger.debug("Fetching url: %s, method: %s", url, http_method)

            
        if use_multipart:
            cookies = cookielib.CookieJar()
            handlers.extend([MultipartPostHandler])            
        else:
            if urlparams is not None:
                urlparams = urllib.urlencode(urlparams.items(), True)
        opener = urllib2.build_opener(*handlers)
        try:
            handle = opener.open(req, urlparams)
        except NoResultFromRequest:
            return None
        except urllib2.HTTPError, e:
            if http_method == "GET" and e.code == 404:
                return None
            raise

        info = handle.info()
        ct = info['Content-Type']
        content = handle.read()
        logger.debug("Request Content:\n%s", content)
        if redirect_handler.alternate_method is not None:
            method = api.normalize_method(redirect_handler.alternate_method)
            logger.debug("Method changed through redirect to: <%s>", method)

        try:
            if "application/json" in ct:
                content = content.strip()
                if not content:
                    content = "{}"
                try:
                    res = simplejson.loads(content)
                except:
                    logger.error("Couldn't decode returned json")
                    logger.error(content)
                    raise
                res = self._map(res, method, continue_list_fetching)
                return res
            elif len(content) <= 1:
                # this might be the famous SeeOtherSpecialCase which means that
                # all that matters is just the method
                pass
            raise "Unknown Content-Type: %s, returned:\n%s" % (ct, content)
        finally:
            handle.close()

    def _map(self, res, method, continue_list_fetching):
        """
        This method will take the JSON-result of a HTTP-call and return our domain-objects.

        It's also deep magic, don't look.
        """
        pathparts = reversed(method.split("/"))
        stack = []
        for part in pathparts:
            stack.append(part)
            if part in RESTBase.REGISTRY:
                cls = RESTBase.REGISTRY[part]
                # multiple objects
                #if part in res:
                if isinstance(res, list):
                    items = []
                    #for item in res[part]:
                    for item in res:
                        items.append(cls(item, self, stack))
                    if res:
                        items.extend(continue_list_fetching())
                    return items
                else:
                    return cls(res, self, stack)
        logger.debug("don't know how to handle result")
        logger.debug(res)
        return res

    def __getattr__(self, _name):
        """
        Retrieve an API-method. The result is a callable that supports the following invocations:

         - calling (...), with possible arguments (positional/keyword), return the resulting resource or list of resources.

         - invoking append(resource) on it will PUT the resource, making it part of the current resource. Makes
           sense only if it's a collection of course.

         - invoking remove(resource) on it will DELETE the resource from it's container. Also only usable on collections.
        """
        class api_call(object):
            def __call__(selfish, *args, **kwargs):
                return self._call(_name, *args, **kwargs)

            def new(selfish, **kwargs):
                """
                Will invoke the new method on the named resource _name, with 
                self as scope.
                """
                cls = RESTBase.REGISTRY[_name]
                return cls.new(self, **kwargs)

            def append(selfish, resource):
                """
                If the current scope is 
                """
                self._call(_name, str(resource.id), _alternate_http_method="PUT")

            def remove(selfish, resource):
                self._call(_name, str(resource.id), _alternate_http_method="DELETE")

        return api_call()

    def __repr__(self):
        return str(self)

    def __str__(self):
        scopes = self._scope
        base = ""
        if len(scopes) > 1:
            base = str(scopes[-2])
        return base + "/" + str(scopes[-1])


# maybe someday I'll make that work.
# class RESTBaseMeta(type):
#     def __new__(self, name, bases, d):
#         clazz = type(name, bases, d)
#         if 'KIND' in d:
#             kind = d['KIND']
#             RESTBase.REGISTRY[kind] = clazz
#         return clazz

class RESTBase(object):
    """
    The baseclass for all our domain-objects/resources.

    
    """
    REGISTRY = {}

    ALIASES = []

    def __init__(self, data, scope, path_stack=None):
        self.__data = data
        self.__scope = scope
        # try and see if we can/must create an id out of our path
        logger.debug("path_stack: %r", path_stack)
        if path_stack:
            try:
                id = int(path_stack[0])
                self.__data['id'] = id
            except ValueError:
                pass

    def __getattr__(self, name):
        if name in self.__data:
            return self.__data[name]
        scope = Scope(scope=self, parent=self.__scope)
        return getattr(scope, name)

    def __setattr__(self, name, value):
        """
        This method is used to set a resource or a list of resources as property of the resource the
        method is invoked on.

        For example, to set a comment on a track, do

        >>> sca = scapi.Scope()
        >>> track = scapi.Track.new(title='bar', sharing="private")
        >>> comment = scapi.Comment.create(body="This is the body of my comment", timestamp=10)    
        >>> track.comments = comment

        To set a list of users as permissions, do

        >>> sca = scapi.Scope()
        >>> me = sca.me()
        >>> track = scapi.Track.new(title='bar', sharing="private")
        >>> users = sca.users()
        >>> users_to_set = [user  for user in users[:10] if user != me]
        >>> track.permissions = users_to_set

        @param name: the property name
        @type name: str
        @param value: the resource or resources to set
        @type value: RESTBase | list<RESTBase>
        @return: None
        """

        if "_RESTBase__" in name:
            self.__dict__[name] = value
        else:
            if isinstance(value, list) and len(value):
                # the parametername is something like
                # permissions[user_id][]
                # so we try to infer that.
                parameter_name = "%s[%s_id][]" % (name, value[0]._singleton())
                values = [o.id for o in value]
                kwargs = {"_alternate_http_method" : "PUT",
                          parameter_name : values}
                self.__scope._call(self.KIND, self.id, name, **kwargs)
            else:
                # we got a single instance, so make that an argument
                self.__scope._call(self.KIND, self.id, name, **value._as_arguments())

    def _as_arguments(self):        
        """
        Converts a resource to a argument-string the way Rails expects it.
        """
        res = {}
        for key, value in self.__data.items():
            if isinstance(value, basestring):
                value = value.encode("utf-8")
            else:
                value = str(value)
            res["%s[%s]" % (self._singleton(), key)] = value
        return res

    @classmethod
    def create(cls, **data):
        """
        This is a convenience-method for creating an object that will be passed
        as parameter - e.g. a comment. A usage would look like this:

        >>> sca = scapi.Scope()
        >>> track = scapi.Track.new(title='bar', sharing="private")
        >>> comment = scapi.Comment.create(body="This is the body of my comment", timestamp=10)    
        >>> track.comments = comment

        """
        return cls(data, None)

    @classmethod
    def new(cls, *args, **data):
        """
        Create a new resource. The actual values are in data. If the creation
        is scoped, that is e.g. a new contact as part of an user, the 
        args command is a one-element-tuple containing the L{Scope}.

        So for creating new resources, you have two options:
        
         - create an instance directly using the class:

           >>> scope = scapi.Scope()
           >>> scope.User.new(...)
           <scapi.User object at 0x1234>

         - create a instance in a certain scope:

           >>> scope = scapi.Scope()
           >>> user = scapi.User("1")
           >>> track = user.tracks.new()
           <scapi.Track object at 0x1234>

        @param args: if not empty, a one-element tuple containing the Scope
        @type args: tuple<Scope>[1]
        @param data: the data
        @type data: dict
        @return: new instance of the resource
        """
        if args:
            scope = args[0]
        else:
            scope = Scope()
        # prepend the data with our kind
        d = {}
        name = cls._singleton()
        for key, value in data.iteritems():
            d['%s[%s]' % (name, key)] = value
        return getattr(scope, cls.KIND)(**d)

    def _scope(self):
        """
        Return the scope this resource lives in, which is the KIND and id
        
        @return: "<KIND>/<id>"
        """
        return "%s/%s" % (self.KIND, str(self.id))

    @classmethod
    def _singleton(cls):
        """
        This method will take a resource name like "users" and
        return the single-case, in the example "user".

        Currently, it's not very sophisticated, only strips a trailing s.
        """
        name = cls.KIND
        if name[-1] == 's':
            return name[:-1]
        raise ValueError("Can't make %s to a singleton" % name)

    def __repr__(self):
        res = []
        res.append("\n\n******\n%s:" % self.__class__.__name__)
        res.append("")
        for key, v in self.__data.iteritems():
            if isinstance(v, unicode):
                v = v.encode('utf-8')
            else:
                v = str(v)
            res.append("%s=%s" % (key, v))
        return "\n".join(res)


    def __hash__(self):
        return hash("%s%i" % (self.KIND, self.id))

    def __eq__(self, other):
        """
        Test for equality. 

        Resources are considered equal if the have the same kind and id.
        """
        if not isinstance(other, RESTBase):
            return False        
        res = self.KIND == other.KIND and self.id == other.id
        return res

    def __ne__(self, other):
        return not self == other

class User(RESTBase):
    """
    A user domain object/resource. 
    """
    KIND = 'users'
    ALIASES = ['me', 'permissions', 'contacts']

class Track(RESTBase):
    """
    A track domain object/resource. 
    """
    KIND = 'tracks'
    ALIASES = ['favorites']

class Asset(RESTBase):
    """
    An asset domain object/resource. 
    """
    KIND = 'assets'

class Comment(RESTBase):
    """
    A comment domain object/resource. 
    """
    KIND = 'comments'
    

g = {}
g.update(globals())
for name, cls in [(k, v) for k, v in g.iteritems() if isclass(v) and issubclass(v, RESTBase) and not v == RESTBase]:
    RESTBase.REGISTRY[cls.KIND] = cls
    for alias in cls.ALIASES:
        RESTBase.REGISTRY[alias] = cls
    __all__.append(name)
