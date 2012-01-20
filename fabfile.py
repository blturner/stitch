import copy, os, yaml

from fabric.api import env, local, prefix, require, roles, run, sudo
from fabric.context_managers import cd
from fabric.contrib.files import exists, first
from fabric.operations import put

"""
Usage:
    `fab stage`
    `fab deploy`
"""

f = open("staging.yml")
env.conf = yaml.load(f.read())
f.close()


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


def get_site_settings(site):
	settings = env.conf['sites_defaults'].copy()
	settings.update(env.conf['sites'][site])
	if settings.get('based_on'):
		settings.update(env.conf['sites'][settings.get('based_on')])
	# FIXME: Correct any settings that 'based_on' may have overwritten.
	# Probably could be cleaner.
	settings.update(env.conf['sites'][site])
	env.update(settings)
	return env


def site_on_host(site, host):
	on_hosts = env.conf['sites'][site].get('on_hosts')
	if isinstance(on_hosts, str):
		on_hosts = [on_hosts]
	if host in on_hosts:
		return True
	return False


@roles('staging')
def stage():
	"""
	Copy staging.yml to remote and run stage.py to generate
	Apache and WSGI settings files.
	"""
	code_dir = get_host_dict(env.host).get('code_dir')
	staging_dir = code_dir + '/staging'

	# Update staging.yml on the remote because we'll read from it
	# on the server when running stage.py
	with cd(staging_dir):
		put('staging.yml', staging_dir)
		print 'python stage.py %s --sites %s' %  \
			(get_host_shortname(env.host), ' '.join(get_sites()))
	
	prefix_command = 'export PIP_VIRTUALENV_BASE=%s; ' % get_host_dict(env.host).get('virtualenv_dir')
	prefix_command += 'export PIP_RESPECT_VIRTUALEVN=true'

	for site in get_sites():
		env.site = site
		proj_dir = "%s/%s/%s" % (
			get_host_dict(env.host).get('virtualenv_dir'),
			site,
			get_site_settings(site).get('project_name'))
		with prefix(prefix_command):
			if not exists(proj_dir):
				virtualenv(git_clone(env.get('clone_url')))
				virtualenv(git_checkout(proj_dir, env.get('git_parent'), \
					env.get('git_branch_name')))


def virtualenv(command):
	with prefix("source /usr/local/bin/virtualenvwrapper.sh"):
		try:
			run('workon %s' % env.site)
		except:
			run('mkvirtualenv %s' % env.site)
		cmd = 'workon %s; ' % env.site
		cmd += 'cdvirtualenv; '
		cmd += command
		run(cmd)


@roles('staging')
def pip_install():
	for site in get_sites():
		env.site = site # Needed for virtualenv()
		get_site_settings(site)

		virtualenv('pip install -r %s/%s/%s' % (
			get_host_dict(env.host).get('virtualenv_dir'),
			site,
			env.get('project_name')) + '/requirements.txt')


def deploy():
	"""
	This command should run git pull, update pip, and restart the server.
	"""
	require('hosts', provided_by=[staging])


def git_clone(url):
	return 'git clone %s' % url


def git_checkout(directory, parent, branch):
	return 'cd %s; git checkout -b %s %s/%s' % (directory, branch, parent, branch)


def git_pull(directory, parent, branch):
	return 'cd %s; git pull %s %s' % (directory, parent, branch)

