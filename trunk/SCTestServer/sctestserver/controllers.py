from turbogears import controllers, expose, flash
from model import *
from turbogears import identity, redirect
from cherrypy import request, response
from datetime import datetime
from time import gmtime, strptime
# from sctestserver import json
# import logging
# log = logging.getLogger("sctestserver.controllers")

import cherrypy
from cherrypy.filters.basefilter import BaseFilter

class SuffixFilter(BaseFilter):
    def on_start_resource(self):
        # strip the json-suffix - we don't want that
        req = cherrypy.request
        if req.path.endswith('.json'):
            req.path = req.path[:-5]
            req.object_path = req.object_path[:-5]

def parse_http_date(timestamp_string):
    if timestamp_string is None: return None
    test = timestamp_string[3]
    if test == ',':
        format = "%a, %d %b %Y %H:%M:%S GMT"
    elif test == ' ':
        format = "%a %d %b %H:%M:%S %Y"
    else:
        format = "%A, %d-%b-%y %H:%M:%S GMT"
    return datetime(*strptime(timestamp_string, format)[:6])



class RESTController(object):
    children = {}

    def __init__(self):
        error_function = getattr(self.__class__, 'error', None)
        if error_function is not None:
            #If this class defines an error handling method (self.error),
            #then we should decorate our methods with the TG error_handler.
            self.get = error_handler(error_function)(self.get)
            self.modify = error_handler(error_function)(self.modify)
            self.new = error_handler(error_function)(self.new)

    @classmethod
    def get_child(cls, token):
        return cls.children.get(token, None)

    @expose(content_type="application/json")
    def default(self, *path, **kw):
        request = cherrypy.request
        path = list(path)
        resource = None
        http_method = request.method.lower()
        #import pdb; pdb.set_trace()

        #check the http method is supported.
        try:
            method_name = dict(get='get',post='modify')[http_method]
        except KeyError:
            raise cherrypy.HTTPError(501)

        if not path: #If the request path is to a collection.
            if http_method == 'post':
                #If the method is a post, we call self.create which returns
                #a class which is passed into the self.new method.
                resource = self.create(**kw)
                assert resource is not None
                method_name = 'new'
            elif http_method == 'get':
                #If the method is a get, call the self.index method, which
                #should list the contents of the collection.
                return self.index(**kw)
            else:
                #Any other methods get rejected.
                raise cherrypy.HTTPError(501)

        if resource is None:
            #if we don't have a resource by now, (it wasn't created)
            #then try and load one.
            token = path.pop(0)
            resource = self.load(token)
            if resource is None:
                #No resource found?
                raise cherrypy.HTTPError(404)

        #if we have a path, check if the first token matches this 
        #classes children.
        if path:
            token = path.pop(0)
            child = self.get_child(token)
            if child is not None:
                child.parent = resource
                #call down into the child resource.
                return child.default(*path, **kw)
            else:
                raise cherrypy.HTTPError(404)

        if http_method == 'get':
            #if this resource has children, make sure it has a '/'
            #on the end of the URL
            if getattr(self, 'children', None) is not None:
                if request.path[-1:] != '/':
                    redirect(request.path + "/")
            #if the client already has the request in cache, check 
            #if we have a new version else tell the client not 
            #to bother.
            modified_check = request.headers.get('If-Modified-Since', None)
            modified_check = parse_http_date(modified_check)
            if modified_check is not None:
                last_modified = self.get_last_modified_date(resource)
                if last_modified is not None:
                    if last_modified <= modified_check:
                        raise cherrypy.HTTPRedirect("", 304)

        #run the requested method, passing it the resource 
        method = getattr(self, method_name)
        response = method(resource, **kw)
        #set the last modified date header for the response
        last_modified = self.get_last_modified_date(resource)
        if last_modified is None:
            last_modified = datetime(*gmtime()[:6])

        cherrypy.response.headers['Last-Modified'] = (
                datetime.strftime(last_modified, "%a, %d %b %Y %H:%M:%S GMT")
        )

        return response

    def get_last_modified_date(self, resource):
        """
        returns the last modified date of the resource.
        """
        return None

    def index(self, **kw):
        """
        returns the representation of a collection of resources.
        """
        raise cherrypy.HTTPError(403)

    def load(self, token):
        """
        loads and returns a resource identified by the token.
        """
        return None

    def create(self, **kw):
        """
        returns a class or function which will be passed into the self.new 
        method. 
        """
        raise cherrypy.HTTPError(501)

    def new(self, resource_factory, **kw):
        """
        uses resources factory to create a resource, commit it to the 
        database.
        """
        raise cherrypy.HTTPError(501)

    def modify(self, resource, **kw):
        """
        uses kw to modifiy the resource.
        """
        raise cherrypy.HTTPError(501)

    def get(self, resource, **kw):
        """
        fetches the resource, and returns a representation of the resource.
        """
        raise cherrypy.HTTPError(501)


class UserController(controllers.Controller, RESTController):

    def create(self, **kw):
        return User

    def new(self, factory, **kw):
        params = dict((key, value) for key, value in kw.iteritems() if key in ('user_name', 'email_address', 'display_name', 'password'))
        return dict(user=factory(**params))

    def load(self, token, **kw):
        user = User.get(int(token))
        return user

    def get(self, user):
        return dict(user=user)

    def index(self):
        return dict(users=User.select())

class Root(controllers.RootController):
    _cp_filters = [SuffixFilter(),]

    users = UserController()

    @expose(template="sctestserver.templates.welcome")
    # @identity.require(identity.in_group("admin"))
    def index(self):
        import time
        # log.debug("Happy TurboGears Controller Responding For Duty")
        flash("Your application is now running")
        return dict(now=time.ctime())

    @expose(template="sctestserver.templates.login")
    def login(self, forward_url=None, previous_url=None, *args, **kw):

        if not identity.current.anonymous \
            and identity.was_login_attempted() \
            and not identity.get_identity_errors():
            raise redirect(forward_url)

        forward_url=None
        previous_url= request.path

        if identity.was_login_attempted():
            msg=_("The credentials you supplied were not correct or "
                   "did not grant access to this resource.")
        elif identity.get_identity_errors():
            msg=_("You must provide your credentials before accessing "
                   "this resource.")
        else:
            msg=_("Please log in.")
            forward_url= request.headers.get("Referer", "/")
            
        response.status=403
        return dict(message=msg, previous_url=previous_url, logging_in=True,
                    original_parameters=request.params,
                    forward_url=forward_url)

    @expose()
    def logout(self):
        identity.current.logout()
        raise redirect("/")


