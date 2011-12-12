#!/usr/bin/env python
import argparse, os, pprint, urllib, yaml
from jinja2 import Environment, FileSystemLoader

parser = argparse.ArgumentParser(description='Management of django staging environments.')
parser.add_argument(
    'hosts',
    metavar='host',
    nargs='+',
    help='List of hosts defined in staging.yml to update.')
parser.add_argument(
    '--sites',
    metavar='site',
    nargs='+',
    default='ALL', help='List of sites defined in staging.yml to update.')
parser.add_argument(
    '--reinstall',
    action='store_true',
    help='If set, all packages will be re-installed using pip.')
parser.add_argument(
    '--upgrade',
    metavar='pkg',
    nargs='+',
    help='List of packages to upgrade with pip.')

args = parser.parse_args()
env = Environment(loader=FileSystemLoader('templates'))

def render_jinja(template, context, filename):
    t = env.get_template(template)
    c = context
    with open(filename, 'w') as f:
        f.write(t.render(c))

def main(args):
    """
    usage: stage.py [-h] [--sites site [site ...]] [--reinstall] 
        [--upgrade pkg [pkg ...]]
        host [host ...]
    
    NOT IMPLEMENTED:
    --reinstall, --upgrade
    """
    f = open("staging.yml")
    conf = yaml.load(f.read())
    f.close()
    
    # TODO: Check for these paths if they are set in staging.yml
    # These vars should be setup by host, e.g.
    # rembrandt:
    #     hostname: rembrandt.local
    #     apache_dir: /Users/bturner/Projects/staging/httpd
    #     wsgi_dir: /Users/bturner/Projects/staging/wsgi
    #     settings_dir: /Users/bturner/Projects/staging/staging_settings
    
    apache_dir = '/Users/bturner/Projects/staging/httpd'
    wsgi_dir = '/Users/bturner/Projects/staging/wsgi'
    settings_dir = '/Users/bturner/Projects/staging/staging_settings'
    
    # Build up the list of sites to be staged, reading from staging.yml.
    if args['sites'] == 'ALL':
        sites = conf['sites']
    else:
        sites = {}
        for site in args['sites']:
            sites[site] = conf['sites'].get(site)
    
    for site, sitedict in sites.iteritems():
        print "Configuring staging settings for: %s" % site

        # Allows a site in staging.yml to inherit the settings of an existing site definition
        # and provide overrides for the existing definition.
        if sitedict.get('based_on'):
            parent = conf['sites'].get(site).get('based_on')
            parent_settings = conf['sites'].get(parent)
            parent_settings.update(sitedict)
            sitedict = parent_settings
        
        pythonpath = sitedict.get(
            'pythonpath',
            conf['sites_defaults']['pythonpath'])
        
        # if `pythonpath` is a string, return it as a list
        if isinstance(pythonpath, str):
            pythonpath = [pythonpath]
        
        # Create the virtualenv
        project_dir = conf['hosts']['rembrandt'].get('project_dir') + '/' + sitedict.get('project_name')
        git_branch_name = sitedict.get('git_branch_name')
        os.system('./mkvirtualenv.sh %s %s %s' % (site, project_dir, git_branch_name))
        
        # TODO: Whoa, this is crazy. Find out the virtualenv `site-packages`
        # dir so it can be added to the wsgi path
        cmd = 'source `which virtualenvwrapper.sh` && workon %s && \
            cdsitepackages && pwd' % site
        fin, fout = os.popen4(cmd)
        for result in fout.readlines():
            sitepackages = result.rstrip()
        
        context = {
            'pythonpath': pythonpath,
            'site': site,
            'sitepackages': sitepackages
        }
        
        
        # Render an apache conf
        apache_dir = 'httpd'
        
        if not os.path.exists(apache_dir):
            os.makedirs(apache_dir)
        
        filename = '%s/%s.conf' % (apache_dir, site)
        render_jinja('apache/base.conf', context, filename)
        
        
        # Render a WSGI conf
        wsgi_dir = 'wsgi'
        
        if not os.path.exists(wsgi_dir):
            os.makedirs(wsgi_dir)
        
        filename = '%s/sites.%s.conf' % (wsgi_dir, site)
        render_jinja('wsgi/base.conf', context, filename)
        
        
        # Generate staging settings
        pp = pprint.PrettyPrinter()
        site_settings_dir = settings_dir + '/' + site
        settings_overrides = {}
        settings_overrides.update(sitedict)
        settings_overrides.update(conf['sites_defaults'])
        settings_overrides = [ [k, pp.pformat(v)] for k, v in settings_overrides.iteritems()]
        
        context = {
            'original_settings': sitedict.get('original_settings'),
            'settings_overrides': settings_overrides
        }
        
        if not os.path.exists(settings_dir):
            os.makedirs(settings_dir)
            open(os.path.join(settings_dir, "__init__.py"), 'w')
        
        if not os.path.exists(site_settings_dir):
            os.makedirs(site_settings_dir)
        
        if not os.path.exists(site_settings_dir + "__init__.py"):
            open(os.path.join(site_settings_dir, "__init__.py"), 'w')
        
        if not os.path.exists(site_settings_dir + "manage.py"):
            urllib.urlretrieve(
                "https://code.djangoproject.com/export/17145/django/branches/releases/1.3.X/django/conf/project_template/manage.py",
                site_settings_dir + "/manage.py"
            )
        
        filename = site_settings_dir + "/settings.py"
        render_jinja('settings/base.py', context, filename)
    
    
    # Restart apache
    print "Restarting apache."
    os.system("/usr/bin/sudo apachectl restart")

if __name__ == '__main__':
    main(args.__dict__)
