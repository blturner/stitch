import os, pprint, urllib, yaml
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))

def main():
    f = open("staging.yml")
    conf = yaml.load(f.read())
    f.close()
    
    apache_dir = "/Users/bturner/Projects/staging/httpd"
    wsgi_dir = "/Users/bturner/Projects/staging/wsgi"
    
    for host, hostconfig in conf['hosts'].iteritems():
        print host
        print hostconfig
    
    # Generate Apache confs
    for site, sitedict in conf['sites'].iteritems():
        settings_dir = "staging_settings/%s" % site
        
        pythonpath = sitedict.get('pythonpath')
        settings_overrides = {}
        
        context = {
            'pythonpath': pythonpath,
            'site': site
        }
        
        # Generate an apache conf for each host in `staging.yml`
        for host in conf['hosts']:
            host_apache_dir = 'httpd/%s' % host
            template = env.get_template('apache/base.conf')
            
            if not os.path.exists(host_apache_dir):
                os.makedirs(host_apache_dir)
            
            filename = 'httpd/%s/%s.conf' % (host, site)
            with open(filename, 'w') as f:
                f.write(template.render(context))
        
        # Generate wsgi conf
        template = env.get_template('wsgi/base.conf')
        filename = 'wsgi/sites.%s.conf' % site
        with open(filename, 'w') as f:
            f.write(template.render(context))
        
        # Generate staging settings
        template = env.get_template('settings/base.py')
        
        pp = pprint.PrettyPrinter()
        settings_overrides.update(sitedict)
        settings_overrides.update(conf['defaults'])
        settings_overrides = [ [k, pp.pformat(v)] for k, v in settings_overrides.iteritems()]
        context = {
            'original_settings': sitedict.get('original_settings'),
            'settings_overrides': settings_overrides
        }
        
        if not os.path.exists(settings_dir):
            os.makedirs(settings_dir)
        if not os.path.exists(settings_dir + "__init__.py"):
            open(os.path.join(settings_dir, "__init__.py"), 'w')
        if not os.path.exists(settings_dir + "manage.py"):
            urllib.urlretrieve(
                "https://code.djangoproject.com/export/17145/django/branches/releases/1.3.X/django/conf/project_template/manage.py",
                settings_dir + "/manage.py"
            )
        
        filename = settings_dir + "/settings.py"
        with open(filename, 'w') as f:
            f.write(template.render(context))
            f.close()
        
        # Restart apache
        os.system("/usr/bin/sudo apachectl restart")

if __name__ == '__main__':
    main()
