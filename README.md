# Wallflower

It's a desktop wallpaper search system I guess. This is meant to search various sources for desktop wallpapers and download them as needed. It can search by color, aspect ratio or image similarity. It can also find duplicate images across sources. Currently it can scan local directories, saved Reddit wallpaper posts, favorite Imgur galleries and favorite images from Wallhaven. Originally this was a collection of hacky scripts that I thought would be more useful as a single application.

### Development

Requires unix build-essentials, [poetry](https://python-poetry.org/docs/#installation) and [pyenv](https://github.com/pyenv/pyenv#simple-python-version-management-pyenv) with the [virtualenv](https://github.com/pyenv/pyenv-virtualenv#pyenv-virtualenv) plugin.

OR a compatible python venv (>=3.7,<3.10) with poetry works too. The above is just a part of my regular python env recipe.

Clone the repo and build the env. It is important to set `WALLFLOWER_DEBUG=1` in your env so the app runs in a debug context. If you use vscode with the integrated terminal and debugger, the related project options should handle this automatically.

```bash
git clone https://github.com/alexgQQ/wallflower.git
cd wallflower
export WALLFLOWER_DEBUG=1
# activate source env and poetry install
make env
# python main.py
make run
```

### Building

This app uses [pyinstaller](https://pyinstaller.org/en/stable/index.html) for packaging.
```bash
# pyinstaller --onefile main.py
make pkg
```