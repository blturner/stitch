# -*- coding: utf-8 -*-
from distutils.core import setup

setup(
    name='stitch',
    version='0.1',
    author=u'Benjamin Turner',
    author_email='benturn@gmail.com',
    packages=['stitch'],
    url='https://github.com/blturner/stitch',
    license='BSD licence, see LICENCE.txt',
    description='A tool for managing django settings.',
    long_description=open('README').read(),
    zip_safe=False,
)
