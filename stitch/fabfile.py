import os
import pprint
import StringIO
import urllib
import yaml

from fabric.api import env, prefix
from jinja2 import Environment, FileSystemLoader

from stitch.helpers import *

"""
Usage:
    `fab stage`
    `fab stage:sitename`
    `fab deploy`
    Setting roles from the command line:
    `fab --roles=ROLE stage`
"""

jinja_env = Environment(loader=FileSystemLoader('templates'))

# global
f = open("staging.yml")
env.conf = yaml.load(f.read())
f.close()


for role, hosts in env.conf['roles'].iteritems():
    if isinstance(hosts, str):
        hosts = [hosts]

    env.roledefs[role] = []
    for host in hosts:
        env.roledefs[role].append(env.conf['hosts'][host].get('hostname'))
env.local = False


def get_host_dict(hostname):
    shortname = get_host_shortname(hostname)
    host_dict = env.conf['hosts_defaults'].copy()
    host_dict.update(env.conf['hosts'][shortname])
    return host_dict


def get_host_shortname(hostname):
    """
    Returns a shortname from a hostname as defined in a yaml file, e.g.:
    YAML:
    hockney:
        hostname: hockney.servers.ben-turner.com

    >>> get_host_shortname('hockney.servers.ben-turner.com')
    >>> 'hockney'
    """
    reverse_host_dict = {}
    for k, v in env.conf['hosts'].iteritems():
        reverse_host_dict[v.get('hostname')] = k
    shortname = reverse_host_dict.get(hostname)
    return shortname


def get_sites():
    sites = []

    for site in env.conf['sites']:
        sites.append(site)
    return sites


def get_site_packages():
    return _virtualenv('python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"', capture=True)


def get_site_settings(site):
    host_dict = get_host_dict(env.host)
    settings = env.conf['sites_defaults'].copy()
    site_settings = env.conf['sites'][site]

    if host_dict.get('settings_overrides'):
        update(settings['settings_overrides'], host_dict.get('settings_overrides'))

    if site_settings.get('based_on'):
        update(settings, env.conf['sites'][site_settings.get('based_on')])

    update(settings, site_settings)
    return settings


def site_on_host():
    try:
        on_hosts = _get('on_hosts')
        if isinstance(on_hosts, str):
            on_hosts = [on_hosts]
        if get_host_shortname(env.host) in on_hosts:
            return True
    except KeyError:
        pass


def generate_conf(template_name, dest, filename, context={}):
    output = StringIO.StringIO()
    t = jinja_env.get_template(template_name)
    t.stream(context).dump(output)

    if not exists(dest):
        run('mkdir -p %s' % dest)

    target = os.path.join(dest, filename)
    put(output, target)
    output.close()


def generate_confs():
    host = get_host_shortname(env.host)
    apache_dir = os.path.join(_get('apache_dir'), host)
    site = env.site
    sitepackages = get_site_packages()
    wsgi_dir = _get('wsgi_dir')

    context = {
        'admin_media': os.path.join(sitepackages, 'django/contrib/admin/media'),
        'pypath': _get('pythonpath').get(host, []),
        'site': site,
        'sitepackages': sitepackages,
        'staging_domain': _get('staging_domain'),
        'virtualenv_dir': os.path.join(_get('virtualenv_dir'), site),
        'wsgi_dir': wsgi_dir
    }
    generate_conf('apache/base.conf', apache_dir, '%s.conf' % site, context)
    generate_conf('wsgi/base.conf', wsgi_dir, '%s.conf' % site, context)
    generate_settings()


def init_settings_dir(path):
    init_file = os.path.join(path, '__init__.py')
    mgmt_file = os.path.join(path, 'manage.py')

    if not exists(init_file):
        output = StringIO.StringIO()
        output.write('')
        put(output, init_file)
        output.close()

    if not exists(mgmt_file):
        output = StringIO.StringIO()
        w = urllib.urlopen('https://code.djangoproject.com/export/17145/django/branches/releases/1.3.X/django/conf/project_template/manage.py').read()
        output.write(w)
        put(output, mgmt_file)
        output.close()


def generate_settings():
    pp = pprint.PrettyPrinter()
    settings_dir = _get('staging_settings')
    site_settings = os.path.join(settings_dir, env.site)
    if not exists(site_settings):
        run('mkdir -p %s' % site_settings)
    init_settings_dir(site_settings)
    overrides = [[k, pp.pformat(v)] for k, v in _get('settings_overrides').iteritems()]
    context = {
        'original_settings': _get('original_settings'),
        'settings_overrides': overrides
    }
    generate_conf('settings/base.py', site_settings, 'settings.py', context)


def git_clone():
    if not exists(env.repo_path):
        with cd(env.project_path):
            run('git clone %s' % _get('clone_url'))


def git_checkout():
    with cd(env.repo_path):
        parent = _get('git_parent')
        branch = _get('git_branch_name')
        try:
            run('git checkout -b %s %s/%s' % (branch, parent, branch))
        except:
            pass
        run('git pull %s %s' % (parent, branch))


def setup_virtualenv():
    """
    Setup virtual environments.
    """
    virtualenv_dir = _get('virtualenv_dir')
    prefix_command = 'export PIP_VIRTUALENV_BASE=%s; ' % virtualenv_dir
    prefix_command += 'export PIP_RESPECT_VIRTUALEVN=true'

    with prefix(prefix_command):
        if not exists(env.project_path):
            with prefix('source `which virtualenvwrapper.sh`'):
                run('mkvirtualenv %(site)s')
        if not exists(env.repo_path):
            git_clone()
            git_checkout()
            add2virtualenv(_get('staging_settings'))
            add2virtualenv(env.project_path)


def _get(key):
    return env.config.get(key, None)


def _virtualenv(command, **kwargs):
    with prefix("source `which virtualenvwrapper.sh`"):
        with cd(_get('virtualenv_dir')):
            activate = 'workon %s' % env.site
            return run(activate + ' && ' + command, **kwargs)


def add2virtualenv(path):
    _virtualenv('add2virtualenv %(path)s' % ({'path': path}))


def pip_install():
    _virtualenv('pip install -r %(repo_path)s/requirements.txt')


def _load_config():
    env.config = {}
    update(env.config, get_host_dict(env.host))
    update(env.config, get_site_settings(env.site))


def process_sites(fn):
    def wrapped(*args, **kwargs):
        if not args:
            sites = get_sites()
        else:
            sites = args
        for site in sites:
            env.host_dict = get_host_dict(env.host)
            env.site = site
            _load_config()
            if site_on_host():
                env.project_path = os.path.join(_get('virtualenv_dir'), env.site)
                env.repo_path = os.path.join(env.project_path, _get('project_name'))
                fn()
            else:
                print env.site + ' is not on this host.'
        restart()
    return wrapped


@process_sites
def debug(*args, **kwargs):
    setup_virtualenv()
    pip_install()
    generate_confs()


@process_sites
def setup(*args, **kwargs):
    setup_virtualenv()
    generate_confs()
    pip_install()


@process_sites
def deploy():
    """
    This command should run git pull, update pip, and restart the server.
    """
    git_checkout()
    generate_confs()
    pip_install()
