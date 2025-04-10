from setuptools import setup, find_packages

setup(
    name="linux_performance_monitor",
    version="0.3.0",
    packages=find_packages(),
    install_requires=[
        'psutil>=5.8.0',
        'click>=8.0.0',
        'pyyaml>=5.4.0',
    ],
    entry_points={
        'console_scripts': [
            'lpm=lpm.cli:cli',
        ],
    },
    package_data={
        'platform': ['config/*.yaml'],
    },
)