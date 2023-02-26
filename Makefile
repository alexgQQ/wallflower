SHELL := /usr/bin/zsh
PYENV_VER := 3.9.14
NAME := wallflower
ENV_NAME := $(PYENV_VER)/envs/$(NAME)

.DEFAULT_GOAL := help

env: ## Install the development environment
	@pyenv install -s $(PYENV_VER)
	@pyenv virtualenv $(PYENV_VER) $(NAME)
	@ln -s $$(pyenv root)/versions/$(NAME) .venv
	@source $${PWD}/.venv/bin/activate
	@poetry install

rmenv: ## Remove the development environment
	@pyenv virtualenv-delete -f $(ENV_NAME)
	@rm -f .venv

clean: ## Remove build artifacts, temp images and any clutter
	@rm -rf **/*.pyc
	@rm -rf build
	@rm -rf dist
	@rm -f main.spec
	@rm -f images/downloads/*

fmt: ## Format code
	@isort -s gui app
	@black --extend-exclude gui app

pkg: ## Build executable package
	@pyinstaller --onefile main.py

run: ## Run local application
	@python main.py

help:
	@echo "Utilities for the $(NAME) application"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
 