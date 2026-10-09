VERSION ?= dev
REPEATS ?= 3

eval:
	python -m evals.run --version $(VERSION) --repeats $(REPEATS)

test:
	pytest -q
