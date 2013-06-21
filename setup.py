from setuptools import setup, find_packages
import os

CLASSIFIERS = [
    'Development Status :: 3 - Alpha',
    'Environment :: Web Environment',
    'Framework :: Django',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
]

setup(
    author='Jacob Rief',
    author_email='jacob.rief@gmail.com',
    name='django-shop-viveum',
    version='0.3.0',
    description='A payment backend module for django-SHOP, using Viveum (https://viveum.v-psp.com) as PSP.',
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.rst')).read(),
    url='https://github.com/jrief/django-shop-viveum',
    license='BSD License',
    platforms=['OS Independent'],
    keywords='django, django-shop, viveum',
    classifiers=CLASSIFIERS,
    install_requires=[
        'Django>=1.4',
        'django-shop',
        'requests',
    ],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False
)
