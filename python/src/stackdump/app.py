import sys
import os
import threading
import functools

from bottle import route, run, static_file, debug, abort, request, redirect
from jinja2 import Environment, PackageLoader
from sqlobject import sqlhub, connectionForURI, AND, OR, SQLObjectNotFound 
from pysolr import Solr

from stackdump.models import Site, Badge, Comment, User

# STATIC VARIABLES
BOTTLE_ROOT = os.path.abspath(os.path.dirname(sys.argv[0]))
MEDIA_ROOT = os.path.abspath(BOTTLE_ROOT + '/../../media')


# THREAD LOCAL VARIABLES
thread_locals = threading.local()


# RESOURCE DECORATORS

def uses_templates(fn):
    '''\
    If called without a function, the template environment is initialised and
    returned.
    
    Otherwise, the function is wrapped to ensure the template environment is
    created before the function is executed.\
    '''
    def init_templates():
        if not hasattr(thread_locals, 'template_env'):
            thread_locals.template_env = Environment(loader=PackageLoader('stackdump', 'templates'))
    
    if not fn:
        init_templates()
        return None
    
    else:
        def wrapped(*args, **kwargs):
            init_templates()
            return fn(*args, **kwargs)
    
        return functools.wraps(fn)(wrapped)

def uses_solr(fn):
    '''\
    If called without a function, the Solr connection is initialised and
    returned.
    
    Otherwise, the function is wrapped to ensure the Solr connection is
    created before the function is executed.\
    '''
    def init_solr():
        if not hasattr(thread_locals, 'solr_conn'):
            thread_locals.solr_conn = Solr("http://localhost:8983/solr/")
    
    if not fn:
        init_solr()
        return None
    
    else:
        def wrapped(*args, **kwargs):
            init_solr()
            return fn(*args, **kwargs)
    
        return functools.wraps(fn)(wrapped)

def uses_db(fn):
    '''\
    If called without a function, the database connection is initialised and
    returned.
    
    Otherwise, the function is wrapped to ensure the database connection is
    created before the function is executed.\
    '''
    def init_db():
        if not hasattr(thread_locals, 'db_conn'):
            db_path = os.path.abspath(os.path.join(BOTTLE_ROOT, '../../../data/stackdump.sqlite'))
            conn_str = 'sqlite://' + db_path
            thread_locals.db_conn = sqlhub.threadConnection = connectionForURI(conn_str)
    
    if not fn:
        init_db()
        return None
    
    else:
        def wrapped(*args, **kwargs):
            init_db()
            return fn(*args, **kwargs)

        return functools.wraps(fn)(wrapped)

# END RESOURCE DECORATORS


# WEB REQUEST METHODS

# all decorators must appear AFTER the route decorators. Any decorators that
# appear above the route decorators will be silently ignored, presumably because
# Bottle caches view functions when the route decorator is called.

# this method MUST sit above the generic static media server, otherwise it won't
# be hit and you will get 'file not found' errors when looking for a
# non-existent logo.
@route('/media/logos/:site_key#[\w\.]+#.png')
def site_logos(site_key):
    root = os.path.join(MEDIA_ROOT, 'images/logos')
    filename = '%s.png' % site_key
    path = os.path.join(root, filename)
    if os.path.exists(path):
        return static_file(filename, root=root)
    else:
        return static_file('images/unknown_site_logo.png', root=MEDIA_ROOT)

# Bottle will protect us against nefarious peeps using ../ hacks.
@route('/media/:filename#.*#')
def serve_static(filename):
    return static_file(filename, root=MEDIA_ROOT)

@route('/')
@uses_templates
@uses_db
def index():
    context = { }
    context['site_root_path'] = ''
    context['sites'] = Site.select()
    return render_template('index.html', context)

@route('/:site_key#[\w\.]+#')
@route('/:site_key#[\w\.]+#/')
@uses_templates
@uses_db
def site_index(site_key):
    context = { }
    context['site_root_path'] = '%s/' % site_key
    
    try:
        context['site'] = Site.selectBy(key=site_key).getOne()
    except SQLObjectNotFound:
        abort(code=404, output='No site exists with the key %s.' % site_key)
    
    return render_template('site_index.html', context)

@route('/search')
@uses_templates
@uses_solr
def search():
    query = request.GET.get('q')
    if not query:
        redirect(settings.APP_URL_ROOT)
    
    page = request.GET.get('p', 0)
    rows_per_page = request.GET.get('r', 10)
    
    # perform search
    results = solr_conn().search(query, start=page*rows_per_page, rows=rows_per_page)
    
    context = { }
    # TODO: scrub this first to avoid injection attacks?
    context['query'] = query
    context['results'] = results
    
    return render_template('results.html', context)

@route('/:site_key#[\w\.]+#/search')
@uses_templates
@uses_solr
def site_search(site_key):
    context = { }
    context['site_root_path'] = '%s/' % site_key
    
    try:
        context['site'] = Site.selectBy(key=site_key).getOne()
    except SQLObjectNotFound:
        raise HTTPError(code=404, output='No site exists with the key %s.' % site_key)
    
    query = request.GET.get('q')
    if not query:
        redirect(settings.APP_URL_ROOT)
    
    page = request.GET.get('p', 0)
    rows_per_page = request.GET.get('r', 10)
    
    # perform search
    results = solr_conn().search(query, start=page*rows_per_page, rows=rows_per_page)
    
    # TODO: scrub this first to avoid injection attacks?
    context['query'] = query
    context['results'] = results
    
    return render_template('site_results.html', context)

# END WEB REQUEST METHODS


# VIEW HELPERS

def template_env():
    # check that the template environment was initialised
    uses_templates(None)
    return thread_locals.template_env

def solr_conn():
    # check that the Solr connection was initialised
    uses_solr(None)
    return thread_locals.solr_conn

# This method is a bit useless, because the objects aren't accessed directly
# from the connection.
def db_conn():
    # check that the database connection was initialised
    uses_db(None)
    return thread_locals.db_conn

def render_template(template_path, context=None):
    if not context:
        context = { }
    
    context['SETTINGS'] = get_template_settings()
    
    return template_env().get_template(template_path).render(**context)

def get_template_settings():
    template_settings = { }
    keys = settings.get('TEMPLATE_SETTINGS', [ ])
    for k in keys:
        template_settings[k] = settings.get(k, None)
    
    return template_settings

# END VIEW HELPERS

# INITIALISATION

if __name__ == '__main__':
    # only do these things in the child processes, not the parents. Applies when
    # the auto-reload option is on (reloader=True). When it is on, the
    # BOTTLE_CHILD env var is True if this is the child process.
    if os.environ.get('BOTTLE_CHILD', True):
        print('Serving media from: %s' % MEDIA_ROOT)
    
    # load the settings file
    __import__('settings')
    if 'settings' in sys.modules.keys():
        settings = sys.modules.get('settings')
        settings = dict([ (k, getattr(settings, k)) for k in dir(settings) if not k.startswith('__') ])
    else:
        settings = { }
    
    if settings.get('DEBUG', False):
        debug(True)
    
    # run the server!
    server = settings.get('SERVER_ADAPTER', 'wsgiref')
    
    run(
        server=server,
        host=settings.get('SERVER_HOST', '0.0.0.0'),
        port=settings.get('SERVER_PORT', 8080),
        reloader=True
    )

# END INITIALISATION
