import setuptools

def readme():
    with open('README.md', 'r') as f:
        return f.read()

setuptools.setup(
    name='debian_crossgrader',
    version='0.0.3',
    author='Kevin Wu',
    author_email='kevin@kevinniuwu.com',
    description='Debian crossgrading tool',
    long_description=readme(),
    long_description_content_type='text/markdown',
    url='https://salsa.debian.org/crossgrading-team/debian-crossgrading',
    packages=setuptools.find_packages(),
    include_package_data=True,
    license='GPL-2+',
    platforms=['Debian'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)'
    ],
    python_requires='>=3.4',
    install_requires=[
        'appdirs',
        'python-apt>=1.0.0'
    ],
    entry_points={
        'console_scripts': [
            'crossgrader=debian_crossgrader.__main__:main',
            'crossgrade-package-check=debian_crossgrader.tools.package_check:main'
        ]
    }
)
