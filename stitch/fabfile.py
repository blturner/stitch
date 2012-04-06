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
    host = get_host_shortname(env.host)
    sites = []

    for site in env.conf['sites']:
        if site_on_host(site, host):
            sites.append(site)
    return sites


def get_site_packages(site):
    env.site = site
    return virtualenv('python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"')


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


def site_on_host(site, host):
    try:
        on_hosts = get_site_settings(site).get('on_hosts')
        if isinstance(on_hosts, str):
            on_hosts = [on_hosts]
        if host in on_hosts:
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
    host_dict = get_host_dict(env.host)
    apache_dir = os.path.join(host_dict.get('apache_dir'), host)
    staging_domain = host_dict.get('staging_domain')
    virtualenv_dir = host_dict.get('virtualenv_dir')
    wsgi_dir = host_dict.get('wsgi_dir')

    site = env.site
    context = {
        'admin_media': os.path.join(get_site_packages(site), 'django/contrib/admin/media'),
        'pypath': get_site_settings(site).get('pythonpath').get(host, []),
        'site': site,
        'sitepackages': get_site_packages(site),
        'staging_domain': staging_domain,
        'virtualenv_dir': os.path.join(virtualenv_dir, site),
        'wsgi_dir': wsgi_dir
    }
    generate_conf('apache/base.conf', apache_dir, '%s.conf' % site, context)
    generate_conf('wsgi/base.conf', wsgi_dir, '%s.conf' % site, context)
    generate_settings(site)


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


def generate_settings(site):
    host_dict = get_host_dict(env.host)
    pp = pprint.PrettyPrinter()
    settings_dir = host_dict.get('staging_settings')
    site_settings = os.path.join(settings_dir, site)
    if not exists(site_settings):
        run('mkdir -p %s' % site_settings)
    init_settings_dir(site_settings)
    settings = get_site_settings(site)
    overrides = [[k, pp.pformat(v)] for k, v in settings['settings_overrides'].iteritems()]
    context = {
        'original_settings': settings.get('original_settings'),
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
    host_dict = get_host_dict(env.host)
    code_dir = host_dict.get('code_dir')
    virtualenv_dir = host_dict.get('virtualenv_dir')

    prefix_command = 'export PIP_VIRTUALENV_BASE=%s; ' % host_dict.get('virtualenv_dir')
    prefix_command += 'export PIP_RESPECT_VIRTUALEVN=true'

    site = env.site
    site_dict = get_site_settings(site)
    proj_dir = "%s/%s/%s" % (
        virtualenv_dir,
        site,
        site_dict.get('project_name'))
    with prefix(prefix_command):
        if not exists(proj_dir):
            # clone git project
            virtualenv(git_clone(site_dict.get('clone_url')))
            # git checkout parent/branch (Should check if not using master)
            if not site_dict.get('git_branch_name') == 'master':
                virtualenv(git_checkout(proj_dir, site_dict.get('git_parent'),
                                        site_dict.get('git_branch_name')))

            virtualenv('add2virtualenv %s' % host_dict.get('staging_settings'))
            virtualenv('add2virtualenv %s/%s' % (virtualenv_dir, site))
            if code_dir:
                virtualenv('add2virtualenv %s' % code_dir)

def _get(key):
    return env.config.get(key, None)

def virtualenv(command):
    """
    Usage: `run(virtualenv(command)) or local(virtualenv(command))`
    """
    with prefix("source `which virtualenvwrapper.sh`"):
        try:
            run('workon %s' % env.site)
        except:
            run('mkvirtualenv %s' % env.site)
        cmd = 'workon %s; ' % env.site
        cmd += 'cdvirtualenv; '
        cmd += command
        out = run(cmd)
        return out


def pip_install():
    # TODO: Give feedback as to what's going on.
    host_dict = get_host_dict(env.host)
    settings_dict = get_site_settings(env.site)

    virtualenv('pip install -r %s/%s/%s' % (host_dict.get('virtualenv_dir'),
                                            env.site, settings_dict.get('project_name'))
                                            + '/requirements.txt')


def pip_update():
    host_dict = get_host_dict(env.host)
    for site in get_sites():
        env.site = site  # Needed for virtualenv()
        settings = get_site_settings(site)
        virtualenv('pip install -r %s/%s/%s' % (host_dict.get('virtualenv_dir'),
                                                site, settings.get('project_name'))
                                                + '/requirements.txt')


def process_sites(fn):
    def wrapped(*args, **kwargs):
        if not args:
            sites = get_sites()
        else:
            sites = args
        for site in sites:
            if not site_on_host(site, get_host_shortname(env.host)):
                print "Invalid site %s" % site
            else:
                env.site = site
                print "Valid site: %s" % env.site
                fn()
    return wrapped


@process_sites
@process_sites
def setup(*args, **kwargs):
    setup_virtualenv()
    pip_install()
    generate_confs()
    restart()


@process_sites
def stage(*args, **kwargs):
    """
    This should update all server settings.
    """
    generate_confs()
    restart()


def deploy():
    """
    This command should run git pull, update pip, and restart the server.
    """
    # require('hosts', provided_by=[staging])
    # stage()
    # get_pull()
    # pip_install()


