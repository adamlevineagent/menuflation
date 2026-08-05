.PHONY: test verify

test:
	python -m pytest

verify:
	python scripts/verify_aggregate.py
