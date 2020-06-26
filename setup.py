from setuptools import setup

setup(
    name='wallflower',
    version='0.1',
    py_modules=['wallflower'],
    install_requires=[
        'Click',
    ],
    entry_points='''
        [console_scripts]
        wallflower=wallflower:cli
    ''',
)
