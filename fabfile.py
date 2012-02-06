import collections, copy, os, pprint, urllib, yaml

from fabric.api import env, local, prefix, require, roles, run, sudo
from fabric.context_managers import cd
from fabric.contrib.files import exists, first
from fabric.operations import put
from jinja2 import Environment, FileSystemLoader

"""
Usage:
    `fab stage`
    `fab deploy`
    Setting roles from the command line:
    `fab --roles=ROLE stage`
"""

f = open("staging.yml")
env.conf = yaml.load(f.read())
f.close()
jinja_env = Environment(loader=FileSystemLoader('templates'))


def render_jinja(template, context, filename):
    t = jinja_env.get_template(template)
    c = context
    with open(filename, 'w') as f:
        f.write(t.render(c))


def update(d, u):
    """
    Utility function that takes a dictionary and updates keys with values from a
    second dictionary.
    http://stackoverflow.com/a/3233356
    """
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def setup_roles():
    for role, hosts in env.conf['roles'].iteritems():
        if isinstance(hosts, str):
            hosts = [hosts]

        env.roledefs[role] = []
        for host in hosts:
            env.roledefs[role].append(env.conf['hosts'][host].get('hostname'))
setup_roles()


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
    sp = virtualenv('source `which virtualenvwrapper.sh` && workon %s && cdsitepackages && pwd' % site)
    return sp


def get_site_settings(site):
    host_dict = get_host_dict(env.host)
    settings = env.conf['sites_defaults'].copy()
    site_settings = env.conf['sites'][site]

    if host_dict.get('settings_overrides'):
        settings['settings_overrides'] = host_dict.get('settings_overrides')

    if site_settings.get('based_on'):
        update(settings, env.conf['sites'][site_settings.get('based_on')])

    update(settings, site_settings)
    return settings


def site_on_host(site, host):
    on_hosts = get_site_settings(site).get('on_hosts')
    if isinstance(on_hosts, str):
        on_hosts = [on_hosts]
    if host in on_hosts:
        return True
    return False


def set_apache_conf():
    host = get_host_shortname(env.host)
    host_dict = get_host_dict(env.host)
    apache_dir = '/'.join((host_dict.get('apache_dir'), host))
    local_dir = '/'.join(('/Users/bturner/Projects/staging/httpd', host))
    for site in get_sites():
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        filename = '%s.conf' % site
        context = {
            'site': site,
            'sitepackages': get_site_packages(site),
            'staging_domain': host_dict.get('staging_domain'),
            'wsgi_dir': host_dict.get('wsgi_dir')
        }
        local_file = '/'.join((local_dir, filename))
        render_jinja('apache/base.conf', context, local_file)
        if not exists(apache_dir):
            run('mkdir -p %s' % apache_dir)
        put(local_file, apache_dir)


def set_wsgi_conf():
    host = get_host_shortname(env.host)
    host_dict = get_host_dict(env.host)
    wsgi_dir = host_dict.get('wsgi_dir')
    local_dir = '/'.join(('/Users/bturner/Projects/staging/wsgi', host))
    for site in get_sites():
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        filename = 'sites.%s.conf' % site
        context = {
            'pythonpath': get_site_settings(site).get('pythonpath').get(host),
            'sitepackages': get_site_packages(site),
            'site': site
        }
        wsgi_conf = '/'.join((local_dir, filename))
        render_jinja('wsgi/base.conf', context, wsgi_conf)
        if not exists(wsgi_dir):
            run('mkdir -p %s' % wsgi_dir)
        put(wsgi_conf, wsgi_dir)


def setup_settings_dir(settings_dir, site_settings_dir):
    if not os.path.exists(settings_dir + '__init__.py'):
        open(os.path.join(settings_dir, '__init__.py'), 'w')

    if not os.path.exists(site_settings_dir + '__init__.py'):
        open(os.path.join(site_settings_dir, '__init__.py'), 'w')

    if not os.path.exists(site_settings_dir + 'manage.py'):
        urllib.urlretrieve(
            'https://code.djangoproject.com/export/17145/django/branches/releases/1.3.X/django/conf/project_template/manage.py',
            site_settings_dir + '/manage.py')


def set_settings_overrides():
    pp = pprint.PrettyPrinter()
    settings_dir = '/home/bturner/code/staging/staging_settings'
    local_dir = '/Users/bturner/Projects/staging/staging_settings'
    for site in get_sites():
        site_settings_dir = '/'.join((settings_dir, site))
        local_settings_dir = '/'.join((local_dir, site))

        if not os.path.exists(local_settings_dir):
            os.makedirs(local_settings_dir)
        setup_settings_dir(local_dir, local_settings_dir)

        put('/'.join((local_dir, '__init__.py')), settings_dir)
        put('/'.join((local_settings_dir, '__init__.py')), site_settings_dir)
        put('/'.join((local_settings_dir, 'manage.py')), site_settings_dir)

        settings = get_site_settings(site)
        s = [[k, pp.pformat(v)] for k, v in settings['settings_overrides'].iteritems()]
        context = {
            'original_settings': settings.get('original_settings'),
            'settings_overrides': s
        }
        filename = '/'.join((local_settings_dir, 'settings.py'))
        render_jinja('settings/base.py', context, filename)
        if not exists(site_settings_dir):
            run('mkdir -p %s' % site_settings_dir)
        put(filename, site_settings_dir)


@roles('staging')
def setup_virtualenv():
    """
    Setup virtual environments.
    """
    code_dir = get_host_dict(env.host).get('code_dir')
    staging_dir = code_dir + '/staging'

    prefix_command = 'export PIP_VIRTUALENV_BASE=%s; ' % get_host_dict(env.host).get('virtualenv_dir')
    prefix_command += 'export PIP_RESPECT_VIRTUALEVN=true'

    host_dict = get_host_dict(env.host)

    for site in get_sites():
        env.site = site
        site_dict = get_site_settings(site)
        virtualenv_dir = host_dict.get('virtualenv_dir')
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
                    virtualenv(git_checkout(proj_dir, site_dict.get('git_parent'), \
                        site_dict.get('git_branch_name')))

                virtualenv('add2virtualenv %s' % staging_dir)
                virtualenv('add2virtualenv %s/%s' % (virtualenv_dir, site))


def virtualenv(command):
    with prefix("source /usr/local/bin/virtualenvwrapper.sh"):
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
    host_dict = get_host_dict(env.host)
    for site in get_sites():
        env.site = site  # Needed for virtualenv()
        settings_dict = get_site_settings(site)

        virtualenv('pip install -r %s/%s/%s' % (
            host_dict.get('virtualenv_dir'),
            site,
            settings_dict.get('project_name')) + '/requirements.txt')


@roles('staging')
def stage():
    setup_virtualenv()
    pip_install()


@roles('production')
def deploy():
    """
    This command should run git pull, update pip, and restart the server.
    """
    # require('hosts', provided_by=[staging])
    # stage()
    # get_pull()
    # pip_install()


def git_clone(url):
    return 'git clone %s' % url


def git_checkout(directory, parent, branch):
    return 'cd %s; git checkout -b %s %s/%s' % (directory, branch, parent, branch)


def git_pull(directory, parent, branch):
    return 'cd %s; git pull %s %s' % (directory, parent, branch)
