import collections, copy, os, pprint, shutil, urllib, yaml
import collections, copy, os, pprint, shutil, StringIO, urllib, yaml

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


def local_or_remote(command):
    if is_local(env.host):
        return local(command, capture=True)
    else:
        return run(command)


def local_or_remote_exists(path):
    if is_local(env.host):
        return os.path.exists(os.path.expanduser(path))
    else:
        return exists(path)


def put_local_or_remote(local_path, remote_path):
    if is_local(env.host):
        shutil.copy(local_path, remote_path)
    else:
        put(local_path, remote_path)


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


def restart():
    if is_local(env.host):
        local('sudo apachectl graceful')
    else:
        sudo('apache2ctl graceful')


def setup_roles():
    for role, hosts in env.conf['roles'].iteritems():
        if isinstance(hosts, str):
            hosts = [hosts]

        env.roledefs[role] = []
        for host in hosts:
            env.roledefs[role].append(env.conf['hosts'][host].get('hostname'))
    env.local = False
setup_roles()


def is_local(host):
    if host in env.roledefs['testing']:
        return True
    return False


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
    sp = virtualenv('cdsitepackages && pwd')
    return sp


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
    on_hosts = get_site_settings(site).get('on_hosts')
    if isinstance(on_hosts, str):
        on_hosts = [on_hosts]
    if host in on_hosts:
        return True
    return False


def generate_conf(template_name, dest, filename, context={}):
    output = StringIO.StringIO()
    t = jinja_env.get_template(template_name)
    t.stream(context).dump(output)

    if not local_or_remote_exists(dest):
        local_or_remote('mkdir -p %s' % dest)

    target = '/'.join((dest, filename))

    if is_local(env.host):
        f = open(target, 'w')
        f.write(output.getvalue())
        f.close()
    else:
        put(output, target)
    output.close()


def generate_confs():
    host = get_host_shortname(env.host)
    host_dict = get_host_dict(env.host)
    apache_dir = '/'.join((host_dict.get('apache_dir'), host))
    wsgi_dir = host_dict.get('wsgi_dir')

    for site in get_sites():
        context = {
            'admin_media': '/'.join((get_site_packages(site), 'django/contrib/admin/media')),
            'pypath': get_site_settings(site).get('pythonpath').get(host, []),
            'site': site,
            'sitepackages': get_site_packages(site),
            'staging_domain': host_dict.get('staging_domain'),
            'wsgi_dir': host_dict.get('wsgi_dir')
        }
        generate_conf('apache/base.conf', apache_dir, '%s.conf' % site, context)
        generate_conf('wsgi/base.conf', wsgi_dir, '%s.conf' % site, context)


def init_settings_dir(path):
    init_file = '/'.join((path, '__init__.py'))
    mgmt_file = '/'.join((path, 'manage.py'))

    if not local_or_remote_exists(init_file):
        f = open(init_file, 'w')
        if not is_local(env.host):
            put(f, path)
    if not local_or_remote_exists(mgmt_file):
        f = open(mgmt_file, 'w')
        f.write(urllib.urlopen('https://code.djangoproject.com/export/17145/django/branches/releases/1.3.X/django/conf/project_template/manage.py').read())
        if not is_local(env.host):
            put(f, path)


def generate_settings():
    host_dict = get_host_dict(env.host)
    pp = pprint.PrettyPrinter()
    settings_dir = host_dict.get('staging_settings')

    for site in get_sites():
        site_settings = '/'.join((settings_dir, site))
        if not local_or_remote_exists(site_settings):
            local_or_remote('mkdir -p %s' % site_settings)
        init_settings_dir(site_settings)
        settings = get_site_settings(site)
        overrides = [[k, pp.pformat(v)] for k, v in settings['settings_overrides'].iteritems()]
        context = {
            'original_settings': settings.get('original_settings'),
            'settings_overrides': overrides
        }
        generate_conf('settings/base.py', site_settings, 'settings.py', context)


def setup_virtualenv():
    """
    Setup virtual environments.
    """
    host_dict = get_host_dict(env.host)
    code_dir = host_dict.get('code_dir')
    virtualenv_dir = host_dict.get('virtualenv_dir')

    prefix_command = 'export PIP_VIRTUALENV_BASE=%s; ' % host_dict.get('virtualenv_dir')
    prefix_command += 'export PIP_RESPECT_VIRTUALEVN=true'

    for site in get_sites():
        env.site = site
        site_dict = get_site_settings(site)
        proj_dir = "%s/%s/%s" % (
            virtualenv_dir,
            site,
            site_dict.get('project_name'))
        with prefix(prefix_command):
            if not local_or_remote_exists(proj_dir):
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


def virtualenv(command):
    """
    Usage: `run(virtualenv(command)) or local(virtualenv(command))`
    """
    with prefix("source `which virtualenvwrapper.sh`"):
        try:
            local_or_remote('workon %s' % env.site)
        except:
            local_or_remote('mkvirtualenv %s' % env.site)
        cmd = 'workon %s; ' % env.site
        cmd += 'cdvirtualenv; '
        cmd += command
        out = local_or_remote(cmd)
        return out


def pip_install():
    host_dict = get_host_dict(env.host)
    for site in get_sites():
        env.site = site  # Needed for virtualenv()
        settings_dict = get_site_settings(site)

        virtualenv('pip install -r %s/%s/%s' % (host_dict.get('virtualenv_dir'),
                                                site, settings_dict.get('project_name'))
                                                + '/requirements.txt')


# @roles('staging')
def stage():
    """
    This should update all server settings.
    """
    # setup_virtualenv()
    set_apache_conf()
    set_wsgi_conf()
    set_settings_overrides()
    restart()


# @roles('production')
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
