# BuildSprint Round 2 Makefile
.PHONY: install test run smoke lint clean

PYTHON = python
VENV_BIN = .venv/Scripts
ifeq ($(OS),Windows_NT)
    VENV_PYTHON = $(VENV_BIN)/python.exe
    VENV_PYTEST = $(VENV_BIN)/pytest.exe
    VENV_RUFF = $(VENV_BIN)/ruff.exe
    VENV_MYPY = $(VENV_BIN)/mypy.exe
    VENV_UVICORN = $(VENV_BIN)/uvicorn.exe
else
    VENV_BIN = .venv/bin
    VENV_PYTHON = $(VENV_BIN)/python
    VENV_PYTEST = $(VENV_BIN)/pytest
    VENV_RUFF = $(VENV_BIN)/ruff
    VENV_MYPY = $(VENV_BIN)/mypy
    VENV_UVICORN = $(VENV_BIN)/uvicorn
endif

install:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r backend/requirements.txt
	$(VENV_PYTHON) -m pip install pydantic-settings types-psutil

test:
	cd backend && $(VENV_PYTEST) -v

run:
	cd backend && $(VENV_UVICORN) app.main:app --host 127.0.0.1 --port 8000 --reload

smoke:
	$(VENV_PYTHON) scripts/smoke_test.py

lint:
	$(VENV_RUFF) check backend/app cli
	$(VENV_MYPY) backend/app cli

clean:
	rm -rf backend/.pytest_cache
	rm -rf .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
