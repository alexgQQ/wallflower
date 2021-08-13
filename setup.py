from setuptools import setup

setup(
    name='wallflower-cli',
    version='0.1',
    py_modules=['wallflower-cli'],
    install_requires=[
        'Click',
    ],
    entry_points='''
        [console_scripts]
        wallflower=wallflower:cli
    ''',
)
