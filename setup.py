import setuptools

def readme():
    with open('README.md', 'r') as f:
        return f.read()

setuptools.setup(
    name='debian_crossgrader',
    version='0.0.1',
    author='Kevin Wu',
    author_email='kevin@kevinniuwu.com',
    description='Debian crossgrading tool',
    long_description=readme(),
    long_description_content_type='text/markdown',
    url='https://salsa.debian.org/crossgrading-team/debian-crossgrading',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux'
    ],
    python_requires='>=3.4',
    entry_points={
        'console_scripts': [
            'crossgrader=debian_crossgrader.crossgrade:main',
            'package-checker=debian_crossgrader.tools.package_check:main'
        ]
    }
)
